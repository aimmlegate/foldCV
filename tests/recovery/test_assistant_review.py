"""Review detects changed dependencies without saving or rebasing the candidate."""

import pytest

from packages.resume_core.models.assistant_proposals import AssistantProposalAcceptV1
from tests.recovery.test_assistant_proposals import environment, read_document, append, complete
from resume_api.agent.proposals import review, review_view
from resume_api.agent.capabilities import catalog


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["text", "membership", "facts"])
async def test_review_marks_changed_authored_scope_stale_and_preserves_both_versions(tmp_path, changed):
    service, runtime, projects, workspace, session = environment(tmp_path)
    try:
        snapshot = await read_document(session)
        draft, _ = await append(session, "review", snapshot=snapshot)
        ready = await complete(session, draft)
        original = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        before_review = projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
        assert review(service, workspace.project_id)[0].proposal.state == "ready"
        assert projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before_review
        workspace = projects.workspaces[workspace.project_id]
        if changed == "text":
            next(block for block in workspace.project.document.blocks() if block.id == "narrative").content[0].text = "Manual correction 😀"
        elif changed == "membership":
            workspace.project.document.regions[0].blocks.reverse()
        else:
            workspace.project.facts.records[0].title.raw_text = "Human title"
        assert projects.persist(workspace.project_id) == "durable"
        manual = projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
        current = review(service, workspace.project_id)[0]
        assert current.proposal.state == "stale" and "Текущие правки" in current.proposal.reason
        assert current.candidate == original.candidate and current.proposal.content_sha256 == original.proposal.content_sha256
        assert projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == manual
        assert not runtime.calls
    finally:
        await session.close()


def test_ui_acceptance_is_strict_and_never_a_model_supplied_boolean():
    from pydantic import ValidationError
    payload = dict(protocolVersion=1, proposalId="proposal_1", version=1, contentSha256="a" * 64,
        owner={"epoch": 1, "token": "synthetic_owner_capability_0123456789"})
    assert AssistantProposalAcceptV1.model_validate(payload).version == 1
    for changed in ({"owner": None}, {"approved": True}, {"protocolVersion": 2}):
        with pytest.raises(ValidationError):
            AssistantProposalAcceptV1.model_validate({**payload, **changed})


@pytest.mark.asyncio
async def test_local_review_availability_requires_origin_generation_to_finish_and_current_identity(tmp_path):
    service, runtime, _, workspace, session = environment(tmp_path, edits=True)
    try:
        snapshot = await read_document(session)
        draft, _ = await append(session, "review", snapshot=snapshot)
        ready = await complete(session, draft)
        value = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        pending = review_view(service, value, catalog(service, workspace.project_id))
        assert not pending.generation_finished and pending.apply.state != "available"
        await session.close()
        service.store.finish(workspace.project_id, session.run.id, "interrupted", error="AGENT_INTERRUPTED", text="Offline draft; no generation ran")
        done = review_view(service, value, catalog(service, workspace.project_id))
        assert done.generation_finished and done.apply.state == "available"
        from resume_api.agent.service import AgentConnection
        service.connection = lambda: AgentConnection(True, ("assistant-model",), "other_account")
        revoked = review_view(service, value, catalog(service, workspace.project_id))
        assert revoked.apply.reason_code == "AGENT_CONNECTION_CHANGED"
        assert not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_durable_cancelled_origin_cannot_rearm_a_ready_payload_left_by_an_interruption(tmp_path):
    service, runtime, _, workspace, session = environment(tmp_path, edits=True)
    try:
        snapshot = await read_document(session)
        draft, _ = await append(session, "review", snapshot=snapshot)
        ready = await complete(session, draft)
        await session.close()
        service.store.finish(workspace.project_id, session.run.id, "cancelled", error="AGENT_CANCELLED")
        value = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        assert value.proposal.state == "ready"
        current = review_view(service, value, catalog(service, workspace.project_id))
        assert current.generation_finished and current.apply.reason_code == "AGENT_CANCELLED"
        assert not runtime.calls
    finally:
        await session.close()
