"""Chat navigation reviews one captured native action without a new history stack."""

import pytest

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.background_inverse import inverse_mutation
from packages.resume_core.models.agent import AgentHistoryOffer, AgentProjectAction
from packages.resume_core.models.assistant_approval import AssistantAcceptanceV1
from packages.resume_core.models.assistant_history import AssistantHistoryOfferV1
from packages.resume_core.models.assistant_actions import AssistantProjectActionPrepareV1
from tests.recovery.test_agent_publication import manual, block
from tests.recovery.test_assistant_proposals import environment, read_document
from tests.recovery.test_assistant_approval import commit_request
from resume_api.agent.history_proposals import offer_history, prepare_history


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["undo", "redo"])
async def test_read_only_generation_reviews_the_captured_native_action_then_apply_navigates_it(tmp_path, direction):
    service, runtime, projects, workspace, session = environment(tmp_path)
    try:
        before = workspace.model_copy(deep=True)
        projects.mutate(workspace.project_id, manual(before, value="User edit 42"))
        edited = projects.read(workspace.project_id).model_copy(deep=True)
        inverse = inverse_mutation(before, edited, mutation_id="local_undo", session_id="history_1")
        if direction == "redo":
            projects.mutate(workspace.project_id, inverse)
            inverse = inverse_mutation(edited, projects.read(workspace.project_id), mutation_id="local_redo", session_id="history_1")
            inverse.kind = "redo"
        inverse.action_id = inverse.capture.action_id = "history_1:original_action"
        current = projects.read(workspace.project_id).model_copy(deep=True)
        lease = service.leases.open(workspace.project_id, "history_1")
        offered = AssistantHistoryOfferV1(protocolVersion=1, requestId=session.run.client_request_id,
            offer=AgentHistoryOffer(owner=lease.owner, projectRevision=current.project_revision,
                documentRevision=current.document_revision, factsRevision=current.project.facts.revision,
                undo=inverse if direction == "undo" else None, redo=inverse if direction == "redo" else None))
        offer_history(service, workspace.project_id, offered)
        offer_history(service, workspace.project_id, offered)
        snapshot = await read_document(session, direction)
        wrapper = AssistantProjectActionPrepareV1(protocolVersion=1, request=AgentProjectAction(
            key="native_history", snapshotId=snapshot.id, action=direction))
        draft = prepare_history(session, wrapper)
        assert await session.call("prepare_edit_batch", wrapper) == draft
        assert draft.get("disposition") == "draft_ready", draft
        stored = service.proposals.get(workspace.project_id, draft["proposalId"], 1)
        assert stored.history.action_id == inverse.action_id and stored.batch.mutation.action_id == inverse.action_id
        assert stored.history.request_id == session.run.client_request_id
        assert projects.storage.read_committed(workspace.project_id)[0] == current
        await session.close()
        service.store.finish(workspace.project_id, session.run.id, "interrupted", error="AGENT_INTERRUPTED")
        payload = AssistantAcceptanceV1(protocolVersion=1, proposalId=draft["proposalId"], version=1,
            contentSha256=draft["contentSha256"], acceptanceId="history_click", owner=lease.owner)
        claim = service.approval.claim(workspace.project_id, payload)
        assert claim.claim.batch.mutation.action_id == "history_1:original_action"
        saved = service.approval.commit(workspace.project_id, commit_request(payload, claim))
        assert saved.receipt.durable
        assert block(saved.project.workspace).content[0].text == (block(before).content[0].text if direction == "undo" else "User edit 42")
        assert not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_new_history_offer_cannot_replace_the_action_captured_for_the_same_request(tmp_path):
    service, runtime, projects, workspace, session = environment(tmp_path)
    try:
        current = projects.read(workspace.project_id)
        owner = service.leases.open(workspace.project_id, "history_1").owner
        offered = AssistantHistoryOfferV1(protocolVersion=1, requestId=session.run.client_request_id,
            offer=AgentHistoryOffer(owner=owner, projectRevision=current.project_revision,
                documentRevision=current.document_revision, factsRevision=current.project.facts.revision, undo=None, redo=None))
        offer_history(service, workspace.project_id, offered)
        changed = offered.model_copy(deep=True)
        changed.offer.project_revision += 1
        with pytest.raises(AgentFailure, match="AGENT_IDEMPOTENCY_CONFLICT"):
            offer_history(service, workspace.project_id, changed)
        snapshot = await read_document(session, "undo")
        result = await session.call("prepare_edit_batch", AssistantProjectActionPrepareV1(protocolVersion=1,
            request=AgentProjectAction(key="missing_history", snapshotId=snapshot.id, action="undo")))
        assert result["error"]["code"] == "AGENT_NOT_FOUND"
        assert not service.proposals.list(workspace.project_id) and not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_chat_undo_reuses_the_existing_backend_inverse_owner_and_native_redo_receipt(tmp_path):
    import time
    from resume_api.agent.runtime import ScriptedAgentRuntime
    from packages.resume_core.background_history import digest_bytes
    from packages.resume_core.models.agent import AgentSettingsRequest, RichMutation
    from packages.resume_core.models.background import WriterAdvanceV1, WriterHistoryCommandV1
    from packages.resume_core.models.assistant_history import AssistantHistoryTargetV1
    from resume_api.agent.service import AgentService, AgentConnection, RunControl
    from resume_api.agent.tools import ToolSession
    from resume_api.jobs.service import JobService
    from resume_api.rich_projects import RichProjectService
    from packages.resume_core.rules import RulesStore
    from tests.recovery.test_agent_lifecycle import Tools
    from tests.recovery.test_agent_tools import Fetcher
    from tests.recovery.test_background_history_transfer import saved_background, transfer_request
    from tests.support.agent import run_request
    fixture, job, proposal = saved_background(tmp_path / "FoldCV")
    project = fixture.project
    projects = RichProjectService(tmp_path / "operations", RulesStore(fixture.publication.canonical.root), lambda: None,
        storage=fixture.publication.canonical)
    projects.ensure_loaded()
    runtime = ScriptedAgentRuntime(None)
    service = AgentService(projects, runtime, lambda: AgentConnection(True, ("assistant-model",), "account-one"), tools=Tools())
    projects.agent = service
    service.assistant_protocol_enabled = True
    service.settings.save(AgentSettingsRequest(expectedRevision=1, enabled=True, selectedAgentModel="assistant-model"), ("assistant-model",))
    jobs = JobService(projects, None, service.connection, enabled=True)
    projects.background_jobs = jobs
    fixture.publication.coordinator.assistant_review_required = jobs.publisher.assistant_review_required
    jobs.store, jobs.publisher, jobs.writers = fixture.publication.jobs, fixture.publication.coordinator, fixture.writers
    jobs.history, jobs.artifacts = fixture.publication.history, fixture.publication.artifacts
    lease = service.leases.open(project, fixture.proof.session_id)
    current = projects.read(project)
    request = run_request(fixture.publication.conversation.id, owner=lease.owner.model_dump(by_alias=True), settingsRevision=2,
        clientRequestId="captured_backend_undo", allowEdits=False, projectRevision=current.project_revision,
        documentRevision=current.document_revision, factsRevision=current.project.facts.revision)
    native_request = transfer_request(fixture, job, proposal)
    native = jobs.writers.history_offer(project, native_request)
    inverse = RichMutation.model_validate_json(native.mutation_wire)
    inverse.action_id = inverse.capture.action_id = "background:" + job.id + ":" + proposal.id
    inverse.capture.session_id = lease.session_id
    offer_history(service, project, AssistantHistoryOfferV1(protocolVersion=1, requestId=request.client_request_id,
        offer=AgentHistoryOffer(owner=lease.owner, projectRevision=current.project_revision,
            documentRevision=current.document_revision, factsRevision=current.project.facts.revision, undo=inverse, redo=None),
        undoBackend=AssistantHistoryTargetV1(jobId=job.id, proposalId=proposal.id, transferId=native.ownership.transfer_id)))
    run, _ = service.submit(project, request)
    session = ToolSession(service, RunControl(project, run.id, run.owner_epoch, run.connection_epoch, time.monotonic()), run, Fetcher())
    try:
        snapshot = await read_document(session, "undo")
        draft = prepare_history(session, AssistantProjectActionPrepareV1(protocolVersion=1,
            request=AgentProjectAction(key="backend_undo", snapshotId=snapshot.id, action="undo")))
        await session.close()
        service.store.finish(project, run.id, "interrupted", error="AGENT_INTERRUPTED")
        payload = AssistantAcceptanceV1(protocolVersion=1, proposalId=draft["proposalId"], version=1,
            contentSha256=draft["contentSha256"], acceptanceId="backend_history_click", owner=lease.owner)
        claim = service.approval.claim(project, payload)
        jobs.writers.begin_history_transfer(project, native_request)
        jobs.writers.acknowledge_history_transfer(project, native_request)
        header = WriterAdvanceV1(schemaVersion=1, proof=fixture.proof, canonicalRevision=current.project_revision,
            canonicalSha256=digest_bytes(current), actionCursor=0)
        command = commit_request(payload, claim).model_copy(update={"writer": header})
        saved = service.approval.commit(project, command)
        assert saved.receipt.durable
        state = jobs.store.load(project)
        assert len(state.inverses) == len(state.history_commands) == 1
        assert state.inverses[0].direction == "redo" and state.inverses[0].owner == "session"
        assert service.approval.commit(project, command).receipt == saved.receipt
        redo = jobs.writers.history_command(project, WriterHistoryCommandV1(schemaVersion=1, proof=fixture.proof,
            canonicalRevision=saved.project.workspace.project_revision, canonicalSha256=digest_bytes(saved.project.workspace),
            actionCursor=1, touches=[{"cursor": 1, "mutation": None}], jobId=job.id, proposalId=proposal.id,
            transferId=state.inverses[0].transfer_id, commandId="native_redo_after_chat", direction="redo"))
        assert block(redo.view.workspace).content[0].text == block(current).content[0].text
        assert len(jobs.store.load(project).history_commands) == 2 and not runtime.calls
    finally:
        await session.close()
        await jobs.shutdown()
