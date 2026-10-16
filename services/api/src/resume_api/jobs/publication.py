"""Adapt durable Job proof without changing the original prepared payload."""

from packages.resume_core.agent_store import digest
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.agent import AgentCommitResult, AgentEditBatch, AgentEditReceipt
from packages.resume_core.models.background import SavedApplyV2
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_api import RichProjectResponse
from packages.resume_core.rich_identity import resume_identity
from packages.resume_core.rich_presentation import presentation


class JobPublication:
    def __init__(self, service):
        self.service = service

    def adopt(self, project, workspace, checksum):
        projects = self.service.projects
        projects.workspaces[project] = workspace
        projects.storage.expected[project] = checksum
        projects.saved_hashes[project] = digest(workspace)
        projects.saved_revisions[project] = (workspace.project_revision, workspace.document_revision)
        projects.save_errors.pop(project, None)

    def publish(self, project, job_id, proposal_sha256):
        service, projects = self.service, self.service.projects
        with projects.state_lock:
            job = service.publisher.publish(project, job_id, proposal_sha256, originals=projects.originals,
                artifacts=projects.artifacts, images=projects.images)
            if job.receipt is not None:
                try:
                    current, checksum = projects.storage.read_committed(project)
                    self.adopt(project, current, checksum)
                except ProjectStoreFailure as error:
                    if error.code != "PROJECT_DELETED":
                        raise
            return job

    def native_result(self, project, job_id):
        service = self.service
        with service.store.guard(project) as directory:
            state = service.store._read(project, directory)
            job = next(item for item in state.jobs if item.id == job_id)
            if job.receipt is None:
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            intent = next((item for item in state.intents if item.job_id == job_id and item.phase == "receipt_stored"), None)
            if intent is None:
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            candidate = service.publisher._load_candidate(state, directory, intent)
            batch = AgentEditBatch.model_validate_json(service.artifacts.payload_unlocked(state, directory, candidate.payload))
            saved, workspace = job.receipt, candidate.workspace
        receipt = AgentEditReceipt(batchId=batch.id, runId=job.id, toolKey=batch.tool_key,
            clientMutationId=saved.client_mutation_id, requestSha256=saved.request_sha256, disposition="saved",
            projectRevision=saved.project_revision, documentRevision=saved.document_revision,
            factsRevision=saved.facts_revision, durable=True, error=None)
        response = RichProjectResponse(workspace=workspace, durability="durable", savedProjectRevision=workspace.project_revision,
            savedDocumentRevision=workspace.document_revision, saveError=None, generation=None,
            presentation=presentation(workspace.project.document, workspace.project.facts), identity=resume_identity(workspace))
        return SavedApplyV2(schemaVersion=2, disposition="saved", jobId=job.id, proposalId=job.proposal_id,
            proposalStored=True, durable=True, result=AgentCommitResult(receipt=receipt, project=response))
