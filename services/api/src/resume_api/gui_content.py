"""One counted GUI content attempt after service queue admission."""

from dataclasses import replace
import threading

from .lifecycle import OperationFiles
from .providers.content import ContentFailure, ContentInput, ContentProvider, ContentResult, ResultT


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
                             usage=error.usage) from None
    return replace(result, logical_attempts=max(1, result.logical_attempts))
