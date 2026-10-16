"""Durable capacity-one execution; publication authority has a separate lifetime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import threading
import math

from .background_clock import Deadlines
from .background_events import JobEvents
from .background_limits import LIMITS
from .background_scheduler import SerialOrder
from .background_store import BackgroundFailure, JobStore, TERMINAL_EXECUTION, expiration, identity
from .models.background import JobAttemptV1, JobFailure, JobSnapshotV1


async def observe_nothing(_name, _job_id):
    pass


@dataclass
class ExecutionOutcome:
    state: str = "completed"
    error: str | None = None
    finished_at: float | None = None


@dataclass
class JobControl:
    supervisor: object
    job: JobSnapshotV1
    cancel: threading.Event = field(default_factory=threading.Event)
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    revoked: bool = False
    owned: object = None
    stage: int = 0
    attempt_id: str | None = None
    active_deadline: float | None = None
    startup_deadline: float | None = None
    task: asyncio.Task | None = None
    run_task: asyncio.Task | None = None
    cleanup_task: asyncio.Task | None = None
    slot_granted: bool = False
    publication_revoked: bool = False
    stop_reason: str | None = None
    permit: object = None

    @property
    def project_id(self):
        return self.job.submission.identity.project_id

    @property
    def run_id(self):
        return self.job.id

    @property
    def owner_epoch(self):
        return self.job.execution_generation

    def stop(self, reason="INTERRUPTED", *, revoke_publication=False):
        self.revoked = True
        self.stop_reason = self.stop_reason or reason
        self.publication_revoked = self.publication_revoked or revoke_publication
        self.cancel.set()
        self.cancelled.set()

    async def child_started(self):
        def started(_state, job):
            attempt = next(a for a in job.attempts if a.id == self.attempt_id)
            attempt.native_started = True
            attempt.child_started_at = self.supervisor.store.clock()
        self.job = self.supervisor.store.update(self.job.submission.identity.project_id, self.job.id, started)
        await self.supervisor._emit(self.job)
        await self.supervisor.observer("child_started", self.job.id)

    async def execution_ready(self):
        if self.cancel.is_set() or self.revoked:
            raise BackgroundFailure("CANCELLED")
        if self.job.submission.account_generation != self.supervisor.store.dispatch_state().account_generation:
            raise BackgroundFailure("ACCOUNT_CHANGED")
        if self.supervisor.clock.now() >= self.startup_deadline:
            raise BackgroundFailure("STARTUP_TIMEOUT")
        self.active_deadline = self.supervisor.clock.now() + LIMITS.active_seconds
        def running(_state, job):
            if job.execution != "starting":
                raise BackgroundFailure("CANCELLED")
            job.execution = "running"
            attempt = next(a for a in job.attempts if a.id == self.attempt_id)
            attempt.state = "running"
            attempt.active_deadline = expiration(self.supervisor.store.clock(), LIMITS.active_seconds)
        self.job = self.supervisor.store.update(self.job.submission.identity.project_id, self.job.id, running)
        self.ready.set()
        await self.supervisor._emit(self.job)


class JobSupervisor:
    def __init__(self, store: JobStore, factory, *, clock=None, observer=observe_nothing,
                 preflight=lambda _job: None, admit=None, eligible=lambda _job: True):
        self.store, self.factory = store, factory
        self.clock = clock or Deadlines()
        self.observer, self.preflight = observer, preflight
        self.admit = admit
        self.eligible = eligible
        self.events = JobEvents(store)
        self.order = SerialOrder()
        self.controls = {}
        self.active = None
        self.fenced = None
        self.paused = None
        self.changed = asyncio.Event()
        self.closed = False
        self.dispatcher = None
        self.listeners = set()

    async def start(self):
        if self.closed:
            raise BackgroundFailure("JOB_DISABLED")
        if self.dispatcher is not None:
            return
        for project in self.store.snapshots():
            self.store.recover(project)
        if self.store.fences:
            self.fenced = "CLEANUP_FAILED"
        self.paused = self.store.dispatch_state().paused
        self.dispatcher = asyncio.create_task(self._dispatch())

    async def submit(self, submission):
        if self.closed or self.dispatcher is None:
            raise BackgroundFailure("JOB_DISABLED")
        job, created = self.store.submit(submission)
        try:
            if created:
                await self.observer("accepted_durable", job.id)
        finally:
            self.changed.set()
        return job, created

    async def cancel(self, project_id, job_id):
        control = self.controls.get(job_id)
        if control is not None:
            if control.job.submission.identity.project_id != project_id:
                raise BackgroundFailure("JOB_NOT_FOUND")
            control.stop("CANCELLED", revoke_publication=True)
        result = self.store.cancel(project_id, job_id)
        await self._emit(result)
        self.changed.set()
        return result

    def pause(self, reason):
        if reason not in {"RATE_LIMITED", "AUTH_REQUIRED"}:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        self.paused = reason
        self.store.pause_dispatch(reason)
        self.changed.set()

    def resume(self, account_generation):
        if self.active is not None or self.fenced:
            raise BackgroundFailure("BUSY")
        self.store.resume_dispatch(account_generation)
        self.paused = None
        self.changed.set()

    def confirmed_account_change(self, account_generation):
        current = self.store.dispatch_state().account_generation
        if type(account_generation) is not int or account_generation < current:
            raise BackgroundFailure("ACCOUNT_CHANGED")
        for control in self.controls.values():
            if control.job.submission.account_generation != account_generation:
                control.stop("ACCOUNT_CHANGED", revoke_publication=True)
        self.store.replace_account(account_generation)
        self.paused = self.store.dispatch_state().paused
        self.changed.set()

    def login_allowed(self):
        return self.active is None and not self.fenced

    async def _dispatch(self):
        while not self.closed:
            await self.changed.wait()
            self.changed.clear()
            if self.active is not None or self.fenced or self.paused:
                continue
            try:
                job = self.order.choose(self.store.snapshots(), self.eligible)
            except BackgroundFailure as error:
                self.fenced = error.code
                continue
            if job is None:
                continue
            control = JobControl(self, job)
            self.controls[job.id] = control
            self.active = control
            self.order.dispatched(job)
            control.task = asyncio.create_task(self._drive(control))

    async def _emit(self, job):
        try:
            self.events.append(job)
        except BackgroundFailure:
            pass
        for changed in tuple(self.listeners):
            changed.set()

    async def _wait_run(self, control, owned):
        run = asyncio.create_task(owned.run(control))
        control.run_task = run
        ready = asyncio.create_task(control.ready.wait())
        stop = asyncio.create_task(control.cancelled.wait())
        startup = asyncio.create_task(self.clock.wait(control.startup_deadline))
        active = None
        try:
            done, _ = await asyncio.wait([run, ready, stop, startup], return_when=asyncio.FIRST_COMPLETED)
            if stop in done:
                return self._stopped(control), run
            if self.clock.now() >= control.startup_deadline and not control.ready.is_set():
                control.stop("STARTUP_TIMEOUT")
                return ExecutionOutcome("failed", "STARTUP_TIMEOUT"), run
            if run in done:
                result = self._outcome(await run)
                if result.error is None and not control.ready.is_set():
                    return ExecutionOutcome("failed", "PROTOCOL"), run
                if (control.active_deadline is not None and
                        (result.finished_at if result.finished_at is not None else self.clock.now()) >= control.active_deadline):
                    control.stop("DEADLINE")
                    return ExecutionOutcome("failed", "DEADLINE"), run
                return result, run
            active = asyncio.create_task(self.clock.wait(control.active_deadline))
            done, _ = await asyncio.wait([run, stop, active], return_when=asyncio.FIRST_COMPLETED)
            if stop in done:
                return self._stopped(control), run
            if self.clock.now() >= control.active_deadline:
                control.stop("DEADLINE")
                return ExecutionOutcome("failed", "DEADLINE"), run
            return self._outcome(await run), run
        finally:
            for waiter in (ready, stop, startup, active):
                if waiter is not None:
                    waiter.cancel()
            await asyncio.gather(*(w for w in (ready, stop, startup, active) if w is not None), return_exceptions=True)

    @staticmethod
    def _stopped(control):
        reason = control.stop_reason or "CANCELLED"
        state = "cancelled" if reason == "CANCELLED" else "interrupted" if reason in {"INTERRUPTED", "ACCOUNT_CHANGED", "PROJECT_DELETED"} else "failed"
        return ExecutionOutcome(state, reason)

    def _outcome(self, value):
        if (not isinstance(value, ExecutionOutcome) or value.state not in TERMINAL_EXECUTION
                or value.state == "completed" and value.error is not None):
            return ExecutionOutcome("failed", "PROTOCOL")
        if value.finished_at is not None and (type(value.finished_at) not in {int, float}
                or not math.isfinite(value.finished_at) or value.finished_at > self.clock.now()):
            return ExecutionOutcome("failed", "PROTOCOL")
        try:
            if value.error is not None:
                JobFailure(code=value.error)
        except ValueError:
            return ExecutionOutcome("failed", "PROTOCOL")
        if value.error in {"RATE_LIMITED", "AUTH_REQUIRED"}:
            self.pause(value.error)
        return value

    async def _close_owned(self, control):
        control.revoked = True
        close = asyncio.create_task(control.owned.close())
        control.cleanup_task = close
        timer = asyncio.create_task(self.clock.wait(self.clock.now() + LIMITS.cleanup_seconds))
        try:
            done, _ = await asyncio.wait([close, timer], return_when=asyncio.FIRST_COMPLETED)
            if close not in done:
                self.fenced = "CLEANUP_FAILED"
                return False
            await close
            return bool(control.owned.verified_dead())
        except Exception:
            return False
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    async def _drive(self, control):
        outcome = ExecutionOutcome("failed", "PROCESS_FAILED")
        verified = True
        project = control.job.submission.identity.project_id
        try:
            await self.observer("queue_eligible", control.job.id)
            if control.job.submission.account_generation != self.store.dispatch_state().account_generation:
                raise BackgroundFailure("ACCOUNT_CHANGED")
            reason = self.preflight(control.job)
            if reason:
                if reason in {"RATE_LIMITED", "AUTH_REQUIRED"}:
                    outcome = ExecutionOutcome("queued", reason)
                    return
                raise BackgroundFailure(reason)
            if self.admit is not None:
                control.permit = await self.admit(control)
                if control.cancel.is_set():
                    raise BackgroundFailure("CANCELLED")
                reason = self.preflight(control.job)
                if reason:
                    if reason in {"RATE_LIMITED", "AUTH_REQUIRED"}:
                        outcome = ExecutionOutcome("queued", reason)
                        return
                    raise BackgroundFailure(reason)
            control.slot_granted = True
            await self.observer("slot_granted", control.job.id)
            for stage, model in enumerate(control.job.submission.models):
                if control.cancel.is_set():
                    raise BackgroundFailure("CANCELLED")
                control.stage, control.ready, control.revoked = stage, asyncio.Event(), False
                control.attempt_id = identity("attempt")
                control.startup_deadline = self.clock.now() + LIMITS.startup_seconds
                now = self.store.clock()
                def reserve(_state, job):
                    if job.execution not in {"queued", "running"}:
                        raise BackgroundFailure("CANCELLED")
                    job.execution = "starting"
                    job.error = None
                    job.attempts.append(JobAttemptV1(schemaVersion=1, id=control.attempt_id, stage=model.stage,
                        executionGeneration=job.execution_generation, state="starting", dispatchedAt=now,
                        startupDeadline=expiration(now, LIMITS.startup_seconds), activeDeadline=expiration(now, LIMITS.active_seconds),
                        nativeStarted=False, childStartedAt=None, cleanupVerified=False, error=None))
                control.job = self.store.update(project, control.job.id, reserve)
                await self._emit(control.job)
                await self.observer("before_spawn", control.job.id)
                if control.cancel.is_set():
                    raise BackgroundFailure("CANCELLED")
                control.owned = self.factory(control.job, model)
                verified = False
                run = None
                try:
                    outcome, run = await self._wait_run(control, control.owned)
                finally:
                    cleanup_error = None
                    try:
                        await self.observer("cleanup_started", control.job.id)
                    except BaseException as error:
                        cleanup_error = error
                    finally:
                        verified = await self._close_owned(control)
                    if verified and control.run_task is not None and not control.run_task.done():
                        control.run_task.cancel()
                        await asyncio.gather(control.run_task, return_exceptions=True)
                    if cleanup_error is not None:
                        raise cleanup_error
                if not verified:
                    raise BackgroundFailure("CLEANUP_FAILED")
                if control.stop_reason is not None:
                    outcome = self._stopped(control)
                await self.observer("children_verified_dead", control.job.id)
                def completed_attempt(_state, job):
                    attempt = next(a for a in job.attempts if a.id == control.attempt_id)
                    attempt.state = outcome.state
                    attempt.cleanup_verified = True
                    attempt.error = JobFailure(code=outcome.error) if outcome.error else None
                control.job = self.store.update(project, control.job.id, completed_attempt)
                control.owned = None
                if outcome.error:
                    break
        except BackgroundFailure as error:
            outcome = ExecutionOutcome("cancelled" if error.code == "CANCELLED" else "failed", error.code)
        except Exception:
            outcome = ExecutionOutcome("failed", "PROCESS_FAILED")
        finally:
            control.revoked = True
            if control.run_task is not None and control.run_task.done() and not control.run_task.cancelled():
                try:
                    # Account failures observed while a deadline wins still pause new work.
                    self._outcome(control.run_task.result())
                except BackgroundFailure:
                    self.fenced = "JOB_STORE_UNAVAILABLE"
                except Exception:
                    pass
            if not verified:
                self.fenced = "CLEANUP_FAILED"
                outcome = ExecutionOutcome("failed", "CLEANUP_FAILED")
            if outcome.error in {"RATE_LIMITED", "AUTH_REQUIRED"}:
                try:
                    self.pause(outcome.error)
                except BackgroundFailure:
                    self.fenced = "JOB_STORE_UNAVAILABLE"
            try:
                def finish(_state, job):
                    if job.execution not in TERMINAL_EXECUTION:
                        job.execution = ("interrupted" if job.error and job.error.code in {"ACCOUNT_CHANGED", "PROJECT_DELETED"}
                            else "cancelled") if job.execution == "cancelling" else outcome.state
                        if job.error is None or job.error.code not in {"ACCOUNT_CHANGED", "PROJECT_DELETED"}:
                            job.error = JobFailure(code=outcome.error) if outcome.error else None
                    for attempt in job.attempts:
                        if attempt.id == control.attempt_id and not attempt.cleanup_verified:
                            attempt.state = outcome.state if verified else "cleanup_failed"
                            attempt.cleanup_verified = verified
                control.job = self.store.update(project, control.job.id, finish)
                await self._emit(control.job)
            except BackgroundFailure:
                self.fenced = "JOB_STORE_UNAVAILABLE"
            if verified:
                if control.permit is not None:
                    control.permit.release()
                    control.permit = None
                self.active = None
                try:
                    if control.slot_granted:
                        await self.observer("slot_released", control.job.id)
                except Exception:
                    self.fenced = "CLEANUP_FAILED"
                self.changed.set()

    async def verify_cleanup(self, job_id):
        control = self.controls.get(job_id)
        if control is None or control.owned is None:
            raise BackgroundFailure("JOB_NOT_FOUND")
        control.stop()
        if control.cleanup_task is not None and not control.cleanup_task.done():
            raise BackgroundFailure("CLEANUP_FAILED")
        if not await self._close_owned(control):
            raise BackgroundFailure("CLEANUP_FAILED")
        if control.run_task is not None and not control.run_task.done():
            control.run_task.cancel()
            await asyncio.gather(control.run_task, return_exceptions=True)
        def verified(_state, job):
            for attempt in job.attempts:
                if attempt.id == control.attempt_id:
                    attempt.cleanup_verified = True
                    attempt.state = "failed"
        control.job = self.store.update(control.job.submission.identity.project_id, job_id, verified)
        if self.active is control:
            self.active = None
        control.owned = None
        if control.permit is not None:
            control.permit.release()
            control.permit = None
        if self.fenced == "CLEANUP_FAILED" and not self.store.fences:
            self.fenced = None
        self.changed.set()

    async def shutdown(self):
        self.closed = True
        for control in self.controls.values():
            if control.task is not None and (not control.task.done() or control.owned is not None):
                control.stop()
        self.changed.set()
        if self.dispatcher is not None:
            await self.dispatcher
        tasks = [control.task for control in self.controls.values() if control.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self.active is not None:
            raise BackgroundFailure("CLEANUP_FAILED")
