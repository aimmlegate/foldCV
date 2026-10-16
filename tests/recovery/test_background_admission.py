"""Async admission borrows a real FIFO owner and survives cancelled handoff."""

import asyncio
import threading

import pytest


@pytest.mark.asyncio
async def test_cancel_during_a_granted_reservation_handoff_releases_only_its_owner():
    from resume_api.inference_admission import InferenceAdmission
    admission = InferenceAdmission()
    assert admission.acquire(blocking=False)
    waiting, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    class Cancellation:
        def is_set(self):
            return False
        async def wait(self):
            waiting.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cleanup.set()
                await release.wait()
    task = asyncio.create_task(admission.reserve(Cancellation()))
    try:
        await asyncio.wait_for(waiting.wait(), 10)
        admission.release()
        await asyncio.wait_for(cleanup.wait(), 10)
        assert admission.reservation is not None and admission.locked()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 10)
        assert not admission.locked() and admission.reservation is None
        assert not admission.waiting and not admission.async_waiters
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_borrowed_native_admission_requires_the_exact_live_reservation():
    from resume_api.inference_admission import AdmissionBlocked, InferenceAdmission, OwnedPermit
    admission = InferenceAdmission()
    permit = await admission.reserve(asyncio.Event())
    try:
        with permit.hold(threading.Event()):
            assert admission.locked()
        assert admission.locked()
        with pytest.raises(AdmissionBlocked):
            with OwnedPermit(admission).hold(threading.Event()):
                raise AssertionError("forged permit ran")
    finally:
        permit.release()
    with pytest.raises(AdmissionBlocked):
        with permit.hold(threading.Event()):
            raise AssertionError("expired permit ran")
    with pytest.raises(RuntimeError, match="not held"):
        permit.release()
    assert not admission.locked()
