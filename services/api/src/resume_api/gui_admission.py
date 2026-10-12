"""One FIFO GUI queue in front of the provider's shared generation lock."""

from collections import deque
import threading

from .providers.content import ContentFailure

_CONDITION = threading.Condition()
_WAITING = deque()


class AdmissionCancelled(Exception):
    pass


class QueuedProvider:
    def __init__(self, provider, admitted):
        self.provider = provider
        self.admitted = admitted

    def generate(self, request, files, cancel):
        ticket = object()
        with _CONDITION:
            _WAITING.append(ticket)
            while _WAITING[0] is not ticket:
                if cancel.is_set():
                    _WAITING.remove(ticket)
                    _CONDITION.notify_all()
                    raise AdmissionCancelled()
                _CONDITION.wait(0.025)
        try:
            if cancel.is_set():
                raise AdmissionCancelled()
            queued = getattr(self.provider, "generate_queued", None)
            if queued is not None:
                return queued(request, files, cancel, self.admitted)
            while True:
                if cancel.is_set():
                    raise AdmissionCancelled()
                try:
                    result = self.provider.generate(request, files, cancel)
                except ContentFailure as error:
                    if error.code == "BUSY":
                        cancel.wait(0.025)
                        continue
                    self.admitted()
                    raise
                self.admitted()
                return result
        finally:
            with _CONDITION:
                _WAITING.remove(ticket)
                _CONDITION.notify_all()
