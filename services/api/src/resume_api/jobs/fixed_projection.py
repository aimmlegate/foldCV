"""Run existing sync compilers against captured data without a canonical writer."""

import threading

from packages.resume_core.models.rich_workspace import RichSyncRecord
from packages.resume_core.rich_dependencies import dependencies_current
from packages.resume_core.rich_sync import scoped_dependencies
from ..rich_synchronization import RichSynchronization
from ..gui_projects import ProjectFailure


class CaptureReady(Exception):
    pass


class FixedProjection(RichSynchronization):
    def __init__(self, project, workspace, sync_id, *, invoke=None, original=None):
        self.project, self.workspace, self.sync_id = project, workspace.model_copy(deep=True), sync_id
        self.workspaces = {project: self.workspace}
        if original is not None:
            self.workspace.sync_records.append(original.model_copy(deep=True))
        self.invoke, self.result = invoke, None
        self.state_lock, self.deleted_ids = threading.RLock(), set()

    def read(self, project):
        if project != self.project:
            raise ProjectFailure("PROJECT_NOT_FOUND", 404)
        return self.workspace

    def require_agent_writable(self, _project):
        return None

    def add_sync(self, identifier, capture, block_ids, kind, records=()):
        if not dependencies_current(self.workspace, capture.dependencies):
            raise ProjectFailure("STALE_SELECTION", 409)
        self.result = RichSyncRecord(id=self.sync_id, status="pending", actionId=capture.action_id,
            blockIds=list(block_ids), fieldKeys=[], factIds=list(records),
            dependencies=scoped_dependencies(self.workspace, block_ids, records), errorCode=None,
            kind=kind, ready=False, proposedSteps=[], selection=None, instruction=None)
        return self.result

    async def sync_content(self, _identifier, sync, payload, result_type):
        if self.invoke is None:
            raise CaptureReady()
        return await self.invoke(sync, payload, result_type)

    def publish_sync(self, _identifier, sync):
        self.result = sync

    def response(self, _identifier):
        return self.result

    async def run(self, command):
        if command.kind == "completion":
            return await self.complete_rich(self.project, command.request)
        if command.kind == "rewrite":
            return await self.rewrite_rich(self.project, command.request)
        if command.kind == "panel":
            return await self.panel_rich(self.project, command.request)
        if command.kind == "retry":
            return await self.retry_rewrite(self.project, command.sync_id, command.capture)
        if command.kind == "resolve":
            return self.resolve_conflict(self.project, command.sync_id, command.capture)
        raise ProjectFailure("JOB_SCOPE_INVALID", 409)

    async def capture(self, command):
        try:
            await self.run(command)
        except CaptureReady:
            pass
        if self.result is None:
            raise ProjectFailure("JOB_SCOPE_INVALID", 409)
        return self.result
