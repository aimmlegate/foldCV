"""Cancellable FIFO admission for model work: shared permits run side by side, an exclusive one runs alone."""

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


class _Ticket:
    __slots__ = ("exclusive",)

    def __init__(self, exclusive):
        self.exclusive = exclusive


class InferenceAdmission:
    """Imports, rewrites and assistant turns hold shared permits and run at once, on any provider. Sign-in, CLI install
    and connection checks hold the exclusive permit: they wait for every model call to end, and new model work waits
    behind them."""

    def __init__(self):
        self.condition = threading.Condition()
        self.waiting = deque()
        self.shared = 0
        self.exclusive = False
        self.blocked = False
        self.async_waiters = {}
        self.reservations = set()

    def _notify(self):
        self.condition.notify_all()
        for loop, future in self.async_waiters.values():
            def wake(target=future):
                if not target.done():
                    target.set_result(None)
            if not loop.is_closed():
                loop.call_soon_threadsafe(wake)

    def _may_enter(self, ticket):
        if self.exclusive:
            return False
        if ticket.exclusive:
            return self.shared == 0 and self.waiting[0] is ticket
        # Shared work passes other queued shared work, never an exclusive ticket ahead of it.
        for other in self.waiting:
            if other is ticket:
                return True
            if other.exclusive:
                return False
        return False

    def _enter(self, ticket):
        if ticket.exclusive:
            self.exclusive = True
        else:
            self.shared += 1

    async def reserve(self, cancelled):
        """Wait for a shared permit in the same FIFO without occupying a worker or an active deadline."""
        loop, ticket = asyncio.get_running_loop(), _Ticket(False)
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
                    if self._may_enter(ticket):
                        self._enter(ticket)
                        claimed = OwnedPermit(self)
                        self.reservations.add(claimed)
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
        """Any permit is held."""
        with self.condition:
            return self.exclusive or self.shared > 0

    def busy(self):
        """A new shared reservation would wait: the exclusive permit is held or queued."""
        with self.condition:
            return self.exclusive or any(ticket.exclusive for ticket in self.waiting)

    def acquire(self, blocking=True, timeout=-1, *, exclusive=False):
        deadline = None if timeout == -1 else time.monotonic() + timeout
        with self.condition:
            if self.blocked:
                return False
            ticket = _Ticket(exclusive)
            self.waiting.append(ticket)
            try:
                while not self._may_enter(ticket):
                    if self.blocked or not blocking:
                        return False
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        return False
                    self.condition.wait(remaining)
                if self.blocked:
                    return False
                self._enter(ticket)
                return True
            finally:
                self.waiting.remove(ticket)
                self._notify()

    def release(self):
        """Release the exclusive permit, or one shared permit (the two are never held at once)."""
        with self.condition:
            if self.exclusive:
                self.exclusive = False
            elif self.shared > 0:
                self.shared -= 1
            else:
                raise RuntimeError("Inference permit is not held")
            self._notify()

    @contextmanager
    def hold(self, cancel, *, deadline=None, exclusive=False):
        ticket = _Ticket(exclusive)
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
                    if self._may_enter(ticket):
                        self._enter(ticket)
                        acquired = True
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
    """A shared permit an import keeps for its whole run; its model calls borrow it."""

    def __init__(self, admission):
        self.admission, self.active = admission, True

    @contextmanager
    def hold(self, cancel, *, deadline=None):
        with self.admission.condition:
            if not self.active or self not in self.admission.reservations or self.admission.blocked:
                raise AdmissionBlocked()
            if cancel.is_set():
                raise AdmissionCancelled()
        yield

    def block(self):
        self.admission.block()

    def release(self):
        with self.admission.condition:
            if not self.active or self not in self.admission.reservations:
                raise RuntimeError("Inference reservation is not held")
            self.active = False
            self.admission.reservations.discard(self)
            self.admission.release()


INFERENCE = InferenceAdmission()
