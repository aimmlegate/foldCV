"""One cancellable FIFO permit shared by structured generation and assistant turns."""

from collections import deque
from contextlib import contextmanager
import asyncio
import threading
import time


class AdmissionCancelled(Exception):
    pass


class AdmissionTimeout(Exception):
    pass


class AdmissionBlocked(Exception):
    pass


class InferenceAdmission:
    def __init__(self):
        self.condition = threading.Condition()
        self.waiting = deque()
        self.owned = False
        self.blocked = False
        self.async_waiters = {}
        self.reservation = None

    def _notify(self):
        self.condition.notify_all()
        for loop, future in self.async_waiters.values():
            def wake(target=future):
                if not target.done():
                    target.set_result(None)
            if not loop.is_closed():
                loop.call_soon_threadsafe(wake)

    async def reserve(self, cancelled):
        """Wait in the same FIFO without occupying a worker or an active deadline."""
        loop, ticket = asyncio.get_running_loop(), object()
        claimed = None
        stop = asyncio.create_task(cancelled.wait())
        with self.condition:
            self.waiting.append(ticket)
        try:
            while True:
                with self.condition:
                    if self.blocked:
                        raise AdmissionBlocked()
                    if cancelled.is_set():
                        raise AdmissionCancelled()
                    if not self.owned and self.waiting[0] is ticket:
                        self.owned = True
                        self.reservation = OwnedPermit(self)
                        claimed = self.reservation
                        return claimed
                    wake = loop.create_future()
                    self.async_waiters[ticket] = (loop, wake)
                await asyncio.wait([wake, stop], return_when=asyncio.FIRST_COMPLETED)
        finally:
            with self.condition:
                self.async_waiters.pop(ticket, None)
                self.waiting.remove(ticket)
                self._notify()
            stop.cancel()
            try:
                await asyncio.gather(stop, return_exceptions=True)
            except BaseException:
                if claimed is not None and claimed.active:
                    claimed.release()
                raise

    def block(self):
        with self.condition:
            self.blocked = True
            self._notify()

    def locked(self):
        with self.condition:
            return self.owned

    def acquire(self, blocking=True, timeout=-1):
        deadline = None if timeout == -1 else time.monotonic() + timeout
        with self.condition:
            if self.blocked:
                return False
            if not blocking:
                if self.owned or self.waiting:
                    return False
                self.owned = True
                return True
            ticket = object()
            self.waiting.append(ticket)
            try:
                while self.owned or self.waiting[0] is not ticket:
                    if self.blocked:
                        return False
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        return False
                    self.condition.wait(remaining)
                if self.blocked:
                    return False
                self.owned = True
                return True
            finally:
                self.waiting.remove(ticket)
                self._notify()

    def release(self):
        with self.condition:
            if not self.owned:
                raise RuntimeError("Inference permit is not held")
            self.owned = False
            if self.reservation is not None:
                self.reservation.active = False
                self.reservation = None
            self._notify()

    @contextmanager
    def hold(self, cancel, *, deadline=None):
        ticket = object()
        acquired = False
        with self.condition:
            self.waiting.append(ticket)
            try:
                while True:
                    if self.blocked:
                        raise AdmissionBlocked()
                    if cancel.is_set():
                        raise AdmissionCancelled()
                    if deadline is not None and time.monotonic() >= deadline:
                        raise AdmissionTimeout()
                    if not self.owned and self.waiting[0] is ticket:
                        self.owned = acquired = True
                        break
                    self.condition.wait(0.025)
            finally:
                self.waiting.remove(ticket)
                self._notify()
        try:
            yield
        finally:
            if acquired:
                self.release()


class OwnedPermit:
    def __init__(self, admission):
        self.admission, self.active = admission, True

    @contextmanager
    def hold(self, cancel, *, deadline=None):
        with self.admission.condition:
            if not self.active or self.admission.reservation is not self or not self.admission.owned:
                raise AdmissionBlocked()
            if self.admission.blocked:
                raise AdmissionBlocked()
            if cancel.is_set():
                raise AdmissionCancelled()
        yield

    def block(self):
        self.admission.block()

    def release(self):
        with self.admission.condition:
            if not self.active or self.admission.reservation is not self:
                raise RuntimeError("Inference reservation is not held")
            self.admission.release()


INFERENCE = InferenceAdmission()
