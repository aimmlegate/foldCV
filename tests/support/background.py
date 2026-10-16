"""Owned pipe executions and event controls for real background components."""

import asyncio

from packages.resume_core.background_supervisor import ExecutionOutcome
from spikes.background.harness import OfflineGuard


def save_input(service, request, proof):
    from packages.resume_core.models.background import WriterMutationV1
    project = request.project_id
    view = service.writers.read_snapshot(project, proof)
    command = request.model_copy(deep=True)
    command.capture.session_id = proof.session_id
    replayed = any(item.client_mutation_id == command.client_mutation_id for item in view.workspace.mutation_replay)
    cursor = view.writer.acknowledged_cursor + int(not replayed)
    saved = service.writers.save(project, WriterMutationV1(schemaVersion=1, proof=proof,
        canonicalRevision=view.writer.acknowledged_revision, canonicalSha256=view.writer.acknowledged_sha256,
        actionCursor=cursor, touches=[] if replayed else [{"cursor": cursor, "mutation": command}], mutation=command),
        originals=service.projects.originals, artifacts=service.projects.artifacts, images=service.projects.images)
    service.publication.adopt(project, saved.workspace, saved.workspace_sha256)
    return saved.response


class PipeExecution:
    def __init__(self, factory, job, model):
        self.factory, self.job, self.model = factory, job, model
        key = job.submission.identity.request_id
        self.guard = OfflineGuard(factory.root / (job.id + "-" + model.stage))
        self.result = asyncio.Event()
        self.ready_permission = asyncio.Event()
        self.cleanup_permission = asyncio.Event()
        self.started = asyncio.Event()
        self.child_ready = asyncio.Event()
        self.cleanup_started = asyncio.Event()
        self.closed = asyncio.Event()
        self.child = None
        self.close_error = key in factory.cleanup_errors
        if key not in factory.hold_results:
            self.result.set()
        if key not in factory.hold_startup:
            self.ready_permission.set()
        if key not in factory.hold_cleanup:
            self.cleanup_permission.set()

    async def run(self, control):
        if control.cancel.is_set():
            return ExecutionOutcome("cancelled", "CANCELLED", self.factory.clock.now())
        self.child = self.guard.spawn(self.guard.child)
        await control.child_started()
        self.child_ready.set()
        await self.ready_permission.wait()
        await control.execution_ready()
        self.started.set()
        callback = self.factory.callbacks.get(self.job.submission.identity.request_id)
        if callback is not None:
            return await callback(control, self)
        result = asyncio.create_task(self.result.wait())
        stop = asyncio.create_task(control.cancelled.wait())
        try:
            await asyncio.wait([result, stop], return_when=asyncio.FIRST_COMPLETED)
            if control.cancel.is_set():
                return ExecutionOutcome("cancelled", "CANCELLED", self.factory.clock.now())
            error = self.factory.errors.get(self.job.submission.identity.request_id)
            return ExecutionOutcome("failed" if error else "completed", error, self.factory.clock.now())
        finally:
            result.cancel(); stop.cancel()
            await asyncio.gather(result, stop, return_exceptions=True)

    async def close(self):
        self.cleanup_started.set()
        await self.cleanup_permission.wait()
        if self.close_error:
            raise OSError("synthetic cleanup failure")
        self.guard.close()
        self.closed.set()

    def verified_dead(self):
        return self.closed.is_set() and all(child.process.poll() is not None for child in self.guard.children)


class PipeExecutions:
    def __init__(self, root, clock):
        self.root, self.clock = root, clock
        self.actors = {}
        self.created = {}
        self.calls = []
        self.errors = {}
        self.hold_results = set()
        self.hold_startup = set()
        self.hold_cleanup = set()
        self.cleanup_errors = set()
        self.callbacks = {}

    def __call__(self, job, model):
        actor = PipeExecution(self, job, model)
        self.actors[(job.id, model.stage)] = actor
        self.calls.append((job.id, model.stage))
        self.created.setdefault(job.id, asyncio.Event()).set()
        return actor

    async def actor(self, job):
        event = self.created.setdefault(job.id, asyncio.Event())
        await asyncio.wait_for(event.wait(), 10)
        return self.actors[(job.id, job.submission.models[0].stage)]

    def verify(self):
        if any(not actor.verified_dead() for actor in self.actors.values()):
            raise AssertionError("owned pipe execution leaked")
