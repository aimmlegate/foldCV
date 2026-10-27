"""Content generation under the service's one inference permit, counted as one attempt."""

from dataclasses import replace
import threading

from ..inference_admission import AdmissionCancelled, AdmissionBlocked, INFERENCE
from ..lifecycle import OperationFiles
from .content import ContentFailure, ContentInput, ContentProvider, ContentResult, ResultT


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


def generate_admitted(provider: ContentProvider, request: ContentInput[ResultT],
                      files: OperationFiles, cancel: threading.Event) -> ContentResult[ResultT]:
    if cancel.is_set():
        raise ContentFailure("CANCELLED")
    captured = replace(request, policy=replace(request.policy, allow_repair=False))
    try:
        result = provider.generate(captured, files, cancel)
    except ContentFailure as error:
        # BUSY is a lock-admission signal; task A06's queue waits without an attempt.
        if error.code == "BUSY":
            raise
        raise ContentFailure(error.code, logical_attempts=max(1, error.logical_attempts),
                             usage=error.usage, cleanup_verified=error.cleanup_verified,
                             dispatch_witness=error.dispatch_witness, raw_return=error.raw_return) from None
    return replace(result, logical_attempts=max(1, result.logical_attempts))
