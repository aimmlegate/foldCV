"""Use the queued processing owner for an import tool turn and final publication."""

from packages.resume_core.import_agent import ImportFailure
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rules import RulesFailure
from ..gui_projects import ProjectFailure
from packages.resume_core.models.background import ProcessingCandidateV1
from packages.resume_core.project_store import encoded
from ..jobs.runtime import JobRuntime
from .session import ImportCoordinator, ImportSession, SKILL
from .result import import_workspace


class ImportJobRuntime(JobRuntime):
    instructions = SKILL
    revoke_owner = False

    def open_session(self, control):
        captured = self.service.fixed.input(self.job)
        self.captured = captured
        def guard():
            if control.cancel.is_set() or control.revoked or not self.service.supervisor.owns(control):
                raise ImportFailure("CANCELLED")
            reason = self.service.fixed.preflight(control.job)
            if reason:
                raise ImportFailure(reason)
        self.coordinator = ImportCoordinator(self.service.projects, control.project_id, control.run_id,
            captured.rules, control.cancel, guard=guard,
            allow_text_rewrite=captured.request.command.allow_text_rewrite)
        self.coordinator.begin()
        return ImportSession(self.coordinator)

    async def finish_result(self, control):
        if not self.result.cleanup_verified:
            raise ImportFailure("CLEANUP_FAILED")
        if self.result.state != "completed" or self.result.error is not None:
            return
        draft = self.coordinator.load()
        if not draft.finished:
            raise ImportFailure("IMPORT_NOT_FINISHED")
        workspace = import_workspace(self.coordinator.guard(), draft, self.captured.rules)
        candidate = ProcessingCandidateV1(schemaVersion=1, id="processing_" + self.captured.id[6:],
            inputId=self.captured.id, assessment=None, normalized=None, workspace=workspace, importDraft=draft)
        with self.service.store.guard(control.project_id) as directory:
            state = self.service.store._read(control.project_id, directory)
            self.service.fixed.inputs.save_processing(directory, state, candidate)
        await self.service.fixed.accept(control, {"kind": "processing", "candidateId": candidate.id},
            encoded(candidate.model_dump(mode="json", by_alias=True)), control.job.submission.guards)

    async def _execute(self, control):
        try:
            return await super()._execute(control)
        except (ImportFailure, BackgroundFailure, ProjectStoreFailure, ProjectFailure, RulesFailure) as error:
            from packages.resume_core.background_supervisor import ExecutionOutcome
            return ExecutionOutcome("cancelled" if error.code == "CANCELLED" else "failed", error.code)
