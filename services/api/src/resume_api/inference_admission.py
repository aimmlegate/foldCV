"""Cancellable FIFO admission for model work: shared permits run side by side, an exclusive one runs alone; a
provider's model calls in flight are capped across the service."""

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

    def importing(self):
        """An import holds the permit it keeps for its whole run (reserve)."""
        with self.condition:
            return bool(self.reservations)

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
# Claude calls in flight in the service (R3 of D158): width 8 ran nine at once on Max without a rate-limit reply, and
# two imports at width 8 ran sixteen. Codex has no cap.
CLAUDE_CALLS = 8
# A waiting call reads its cancel, a thread's event, at least this often.
CALL_POLL_SECONDS = 0.1


class CallPlace:
    """One model call's place among its provider's calls in flight; it goes back once. A provider without a cap gives
    an empty one."""

    def __init__(self, places=None, key=None):
        self.places, self.key, self.held, self.future = places, key, places is not None, None

    def release(self):
        if self.places is None:
            return
        with self.places.condition:
            if self.held:
                self.held = False
                self.places.busy[self.key] -= 1
                self.places._notify()

    def follow(self, future):
        """The place goes back when `future`, the call's thread, ends, or when the call is cancelled before it ran."""
        self.future = future
        future.add_done_callback(lambda _future: self.release())


class CallPlaces:
    """Model calls in flight in the service, per provider (R3 of D158). An import's call takes a place before its
    attempt is reserved and a rewrite preview before it starts; the assistant takes none (one long run of its own).
    Waiting calls are served in order."""

    def __init__(self, caps):
        self.caps = dict(caps)
        self.condition = threading.Condition()
        self.busy = dict.fromkeys(self.caps, 0)
        self.waiting = {key: deque() for key in self.caps}
        self.async_waiters = {}

    def _notify(self):
        self.condition.notify_all()
        for loop, future in self.async_waiters.values():
            def wake(target=future):
                if not target.done():
                    target.set_result(None)
            if not loop.is_closed():
                loop.call_soon_threadsafe(wake)

    def _first(self, key, ticket):
        return self.waiting[key][0] is ticket and self.busy[key] < self.caps[key]

    def _take(self, key):
        self.busy[key] += 1
        return CallPlace(self, key)

    async def take(self, key, cancel, seconds):
        """A place for one call of the provider `key`, or None when `seconds` passed or `cancel` was set first."""
        if key not in self.caps:
            return CallPlace()
        loop, ticket, end = asyncio.get_running_loop(), object(), time.monotonic() + seconds
        with self.condition:
            self.waiting[key].append(ticket)
        try:
            while True:
                with self.condition:
                    if cancel.is_set() or time.monotonic() >= end:
                        return None
                    if self._first(key, ticket):
                        return self._take(key)
                    wake = loop.create_future()
                    self.async_waiters[ticket] = (loop, wake)
                await asyncio.wait([wake], timeout=max(0.0, min(CALL_POLL_SECONDS, end - time.monotonic())))
        finally:
            with self.condition:
                self.async_waiters.pop(ticket, None)
                self.waiting[key].remove(ticket)
                self._notify()

    @contextmanager
    def hold(self, key, cancel):
        """A place for one call of the provider `key` while the block runs, waited for in this thread; a cancel raises
        AdmissionCancelled."""
        if key not in self.caps:
            yield
            return
        ticket = object()
        with self.condition:
            self.waiting[key].append(ticket)
            try:
                while not self._first(key, ticket):
                    if cancel.is_set():
                        raise AdmissionCancelled()
                    self.condition.wait(0.025)
                place = self._take(key)
            finally:
                self.waiting[key].remove(ticket)
                self._notify()
        try:
            yield
        finally:
            place.release()


# Keyed by the providers' adapter names (`template_adapter`, the captured model's `adapter`).
CALLS = CallPlaces({"claude_cli": CLAUDE_CALLS})
