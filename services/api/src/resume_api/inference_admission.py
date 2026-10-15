"""One cancellable FIFO permit shared by structured generation and assistant turns."""

from collections import deque
from contextlib import contextmanager
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

    def block(self):
        with self.condition:
            self.blocked = True
            self.condition.notify_all()

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
                self.condition.notify_all()

    def release(self):
        with self.condition:
            if not self.owned:
                raise RuntimeError("Inference permit is not held")
            self.owned = False
            self.condition.notify_all()

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
                self.condition.notify_all()
        try:
            yield
        finally:
            if acquired:
                self.release()


INFERENCE = InferenceAdmission()
