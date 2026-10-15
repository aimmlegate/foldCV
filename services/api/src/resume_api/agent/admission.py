"""Async callers use the shared cancellable permit without blocking the event loop."""

import asyncio
from contextlib import asynccontextmanager
import time

from resume_api.inference_admission import AdmissionCancelled, AdmissionTimeout, INFERENCE


@asynccontextmanager
async def turn_slot(cancel, *, admission=INFERENCE, deadline=None):
    slot = admission.hold(cancel, deadline=deadline if deadline is not None else time.monotonic() + 30)
    acquiring = asyncio.create_task(asyncio.to_thread(slot.__enter__))
    try:
        await asyncio.shield(acquiring)
    except asyncio.CancelledError:
        cancel.set()
        try:
            await asyncio.shield(acquiring)
        except AdmissionCancelled:
            pass
        else:
            slot.__exit__(None, None, None)
        raise
    try:
        yield
    finally:
        slot.__exit__(None, None, None)


@asynccontextmanager
async def worker_slot(projects, cancel, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AdmissionTimeout()
    slot = projects.worker_slot(cancel)
    try:
        await asyncio.wait_for(slot.__aenter__(), remaining)
    except asyncio.TimeoutError:
        raise AdmissionTimeout() from None
    try:
        yield
    finally:
        await slot.__aexit__(None, None, None)
