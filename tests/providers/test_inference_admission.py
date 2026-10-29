"""The inference admission: model work runs side by side, an exclusive holder runs alone, reservations hand off FIFO."""

import asyncio
import threading
import time

import pytest


@pytest.mark.asyncio
async def test_cancel_during_a_granted_reservation_handoff_releases_only_its_owner():
    from resume_api.inference_admission import InferenceAdmission
    admission = InferenceAdmission()
    assert admission.acquire(blocking=False, exclusive=True)
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
        assert len(admission.reservations) == 1 and admission.locked()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 10)
        assert not admission.locked() and not admission.reservations
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


@pytest.mark.asyncio
async def test_model_work_runs_side_by_side_and_an_exclusive_holder_waits_for_all_of_it():
    # D120: an import on one provider no longer stops another import, a rewrite or an assistant turn.
    from resume_api.inference_admission import AdmissionTimeout, InferenceAdmission
    admission = InferenceAdmission()
    first, second = await admission.reserve(asyncio.Event()), await admission.reserve(asyncio.Event())
    with admission.hold(threading.Event()):
        assert admission.shared == 3 and not admission.busy()
    with pytest.raises(AdmissionTimeout):
        with admission.hold(threading.Event(), deadline=time.monotonic() + 0.1, exclusive=True):
            pytest.fail("a sign-in ran beside model work")
    first.release()
    assert not admission.acquire(blocking=False, exclusive=True)
    second.release()
    assert not admission.locked()
    with admission.hold(threading.Event(), exclusive=True):
        assert admission.locked() and admission.busy()
        assert not admission.acquire(blocking=False)


@pytest.mark.asyncio
async def test_model_work_queues_behind_a_waiting_exclusive_holder_instead_of_starving_it():
    from resume_api.inference_admission import InferenceAdmission
    admission = InferenceAdmission()
    running = await admission.reserve(asyncio.Event())
    entered, release = threading.Event(), threading.Event()

    def sign_in():
        with admission.hold(threading.Event(), exclusive=True):
            entered.set()
            release.wait(5)
    thread = threading.Thread(target=sign_in)
    thread.start()
    try:
        for _ in range(500):
            if admission.busy():
                break
            await asyncio.sleep(0.01)
        assert admission.busy() and not entered.is_set()
        later = asyncio.create_task(admission.reserve(asyncio.Event()))
        await asyncio.sleep(0.05)
        assert not later.done()
        running.release()
        assert await asyncio.to_thread(entered.wait, 5)
        assert not later.done()
        release.set()
        permit = await asyncio.wait_for(later, 5)
        assert admission.shared == 1
        permit.release()
    finally:
        release.set()
        thread.join(5)
    assert not admission.locked()
