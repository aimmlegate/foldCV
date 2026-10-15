"""Structured providers enter the same permit as assistant turns, exactly once."""

from .providers.content import ContentFailure
from .inference_admission import AdmissionCancelled, AdmissionBlocked, INFERENCE


class QueuedProvider:
    def __init__(self, provider, admitted):
        self.provider = provider
        self.admitted = admitted

    def generate(self, request, files, cancel):
        queued = getattr(self.provider, "generate_queued", None)
        if queued is not None:
            return queued(request, files, cancel, self.admitted)
        try:
            with INFERENCE.hold(cancel):
                return self._generate(request, files, cancel)
        except AdmissionBlocked:
            raise ContentFailure("PROCESS_CLEANUP_FAILED") from None

    def _generate(self, request, files, cancel):
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
