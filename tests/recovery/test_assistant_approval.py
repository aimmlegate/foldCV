"""Post-run UI preparation uses exact reviewed content and no inference authority."""

import json

import pytest

from packages.resume_core.agent_store import AgentFailure, run_in
from packages.resume_core.models.assistant_approval import AssistantAcceptanceV1, AssistantApplicationCommitV1
from packages.resume_core.assistant_proposals import content_digest
from tests.recovery.test_assistant_proposals import environment, read_document, append, complete
from resume_api.agent.approval import AssistantApproval


async def ready(tmp_path):
    service, runtime, projects, workspace, session = environment(tmp_path)
    try:
        snapshot = await read_document(session)
        initial, _ = await append(session, "approved", snapshot=snapshot)
        proposal = await complete(session, initial)
        def expire(state):
            run_in(state, session.run.id)[1].deadline = "2000-01-01T00:00:00Z"
        service.store.update(workspace.project_id, expire)
        await session.close()
        service.store.finish(workspace.project_id, session.run.id, "interrupted", error="AGENT_INTERRUPTED")
        old = service.leases.require(workspace.project_id)
        from packages.resume_core.models.agent import AgentOwner
        service.leases.close(workspace.project_id, AgentOwner(epoch=old.epoch, token=old.token))
        lease = service.leases.open(workspace.project_id, "reopened_history")
        payload = AssistantAcceptanceV1(protocolVersion=1, proposalId=proposal["proposalId"], version=1,
            contentSha256=proposal["contentSha256"], acceptanceId="click_1", owner=lease.owner)
        return service.approval, service, runtime, projects, workspace, payload
    finally:
        await session.close()


def commit_request(payload, claimed):
    return AssistantApplicationCommitV1.model_validate({**payload.model_dump(by_alias=True),
        "ticket": claimed.claim.ticket, "requestSha256": claimed.claim.batch.request_sha256})


@pytest.mark.asyncio
@pytest.mark.parametrize("lost", ["missing_preview", "corrupt_preview", "old_replay"])
async def test_saved_receipt_outlives_private_preview_and_current_replay_retention(tmp_path, lost):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    claim = approval.claim(workspace.project_id, payload)
    saved = approval.commit(workspace.project_id, commit_request(payload, claim))
    value = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    path = service.proposals.directory(workspace.project_id) / service.proposals.filename(value)
    if lost == "missing_preview":
        path.unlink()
    elif lost == "corrupt_preview":
        path.write_text("corrupt")
    else:
        later = projects.read(workspace.project_id).model_copy(deep=True)
        later.project_revision += 1
        later.project.revision = later.project_revision
        later.mutation_replay = []
        projects.workspaces[workspace.project_id] = later
        assert projects.persist(workspace.project_id) == "durable"
    before = projects.storage.read_committed(workspace.project_id)[1]
    recovered = AssistantApproval(service).recover(workspace.project_id, payload)
    assert recovered.saved_receipt == saved.receipt and recovered.reload_required
    assert (recovered.proposal is None) == (lost != "old_replay")
    if lost == "old_replay":
        assert recovered.result is None and recovered.proposal.state == "applied"
    assert service.publication.recover(workspace.project_id, claim.claim.batch.run_id, claim.claim.batch.id) == saved.receipt
    assert projects.storage.read_committed(workspace.project_id)[1] == before
    assert not runtime.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", [False, True])
async def test_missing_private_payload_and_lost_ui_receipt_recover_only_exact_canonical_save_proof(tmp_path, monkeypatch, saved):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    claim = approval.claim(workspace.project_id, payload)
    with monkeypatch.context() as fault:
        fault.setattr(service.store, "record_reviewed_receipt", lambda *_args: (_ for _ in ()).throw(OSError("lost UI receipt")))
        if not saved:
            fault.setattr(projects.storage, "save", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("no save")))
        with pytest.raises(AgentFailure, match="AGENT_OUTCOME_UNKNOWN"):
            approval.commit(workspace.project_id, commit_request(payload, claim))
    value = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    (service.proposals.directory(workspace.project_id) / service.proposals.filename(value)).unlink()
    from resume_api.agent.service import AgentService
    service = AgentService(projects, runtime, service.connection, tools=service.tools)
    projects.agent = service
    service.assistant_protocol_enabled = True
    service.recover()
    assert not service.store.load(workspace.project_id).conversations[0].runs[0].outcome_unknown
    before = projects.storage.read_committed(workspace.project_id)[1]
    if saved:
        recovered = AssistantApproval(service).recover(workspace.project_id, payload)
        assert recovered.saved_receipt.durable and recovered.proposal is None and recovered.reload_required
        item = service.store.load(workspace.project_id).journals[0].batches[0]
        assert item.receipt.durable and workspace.project_id not in projects.agent_recovery_fences
        assert service.publication.recover(workspace.project_id, item.batch.run_id, item.batch.id) == item.receipt
    else:
        with pytest.raises(AgentFailure, match="AGENT_OUTCOME_UNKNOWN"):
            AssistantApproval(service).recover(workspace.project_id, payload)
        assert workspace.project_id in projects.agent_recovery_fences
    assert projects.storage.read_committed(workspace.project_id)[1] == before and not runtime.calls


@pytest.mark.asyncio
async def test_post_run_ui_ticket_keeps_reviewed_content_and_deduplicates_the_original_click(tmp_path):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    value = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    reply = approval.claim(workspace.project_id, payload)
    again = approval.claim(workspace.project_id, payload)
    assert reply == again and reply.accepted.acceptance_id == "click_1"
    assert reply.claim.batch.mutation.capture.session_id == "reopened_history"
    assert reply.claim.batch.mutation.action_id == value.batch.mutation.action_id
    assert reply.claim.batch.mutation.client_mutation_id != value.batch.mutation.client_mutation_id
    assert reply.claim.batch.request_sha256 != value.batch.request_sha256
    retained = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    assert retained.proposal.state == "applying" and retained.candidate == value.candidate
    assert retained.proposal.content_sha256 == payload.content_sha256
    raw = (service.proposals.directory(workspace.project_id) / service.proposals.filename(retained)).read_text()
    assert payload.owner.token not in raw and reply.claim.ticket not in raw
    assert json.loads(raw)["payload"]["approval"]["phase"] == "accepted"
    assert projects.storage.read_committed(workspace.project_id)[0] == before
    assert not service.controls and not runtime.calls


@pytest.mark.asyncio
async def test_stop_before_delayed_claim_revokes_only_that_click_durably(tmp_path):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    stopped = approval.cancel(workspace.project_id, payload)
    assert stopped.proposal.state == "ready" and stopped.result is None
    with pytest.raises(AgentFailure, match="AGENT_CANCELLED"):
        AssistantApproval(service).claim(workspace.project_id, payload)
    fresh = payload.model_copy(update={"acceptance_id": "click_2"})
    result = approval.commit(workspace.project_id, commit_request(fresh, approval.claim(workspace.project_id, fresh)))
    assert result.receipt.durable
    assert projects.storage.read_committed(workspace.project_id)[0].project_revision == before.project_revision + 1
    assert not runtime.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["expired", "revocation_limit"])
async def test_stop_at_a_retention_boundary_keeps_delayed_application_unavailable(tmp_path, boundary):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    if boundary == "expired":
        service.store.clock = lambda: "2026-11-10T00:00:00Z"
    else:
        def fill(values):
            values[0].revoked_acceptances = [f"old_click_{index}" for index in range(100)]
            return values[0]
        service.proposals.update(workspace.project_id, fill)
    stopped = approval.cancel(workspace.project_id, payload)
    assert stopped.proposal.state == ("expired" if boundary == "expired" else "discarded")
    with pytest.raises(AgentFailure):
        approval.claim(workspace.project_id, payload)
    assert projects.storage.read_committed(workspace.project_id)[0] == before and not runtime.calls


@pytest.mark.asyncio
async def test_cancelled_preparation_cannot_commit_and_retry_requires_a_new_explicit_click(tmp_path):
    approval, _, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    claimed = approval.claim(workspace.project_id, payload)
    stopped = approval.cancel(workspace.project_id, payload)
    assert stopped.proposal.state == "failed_before_commit" and not stopped.result.receipt.durable
    assert not approval.commit(workspace.project_id, commit_request(payload, claimed)).receipt.durable
    with pytest.raises(AgentFailure, match="AGENT_CANCELLED"):
        approval.claim(workspace.project_id, payload)
    with pytest.raises(AgentFailure, match="AGENT_TICKET_INVALID"):
        approval.retry(workspace.project_id, payload)
    fresh = payload.model_copy(update={"acceptance_id": "click_2"})
    assert approval.retry(workspace.project_id, fresh).state == "ready"
    assert approval.commit(workspace.project_id, commit_request(fresh, approval.claim(workspace.project_id, fresh))).receipt.durable
    assert projects.storage.read_committed(workspace.project_id)[0].project_revision == before.project_revision + 1
    assert not runtime.calls


@pytest.mark.asyncio
async def test_delayed_recovery_and_stop_for_an_old_click_never_settle_a_new_acceptance(tmp_path):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    first = approval.claim(workspace.project_id, payload)
    approval.cancel(workspace.project_id, payload)
    fresh = payload.model_copy(update={"acceptance_id": "click_2"})
    approval.retry(workspace.project_id, fresh)
    second = approval.claim(workspace.project_id, fresh)
    for recovered in (approval.recover(workspace.project_id, payload), approval.cancel(workspace.project_id, payload),
            approval.recover(workspace.project_id, payload, resume=True)):
        assert recovered.result.receipt.batch_id == first.claim.batch.id and not recovered.result.receipt.durable
        current = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
        assert current.proposal.state == "applying" and current.approval.acceptance_id == "click_2"
        assert current.approval.phase == "accepted"
    saved = approval.commit(workspace.project_id, commit_request(fresh, second))
    assert saved.receipt.durable
    assert len(projects.storage.read_committed(workspace.project_id)[0].mutation_replay) == 1 and not runtime.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", [False, True])
async def test_restart_recovers_the_original_write_or_proves_no_save_without_generation(tmp_path, monkeypatch, saved):
    from resume_api.agent.service import AgentService
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    projects.agent.approval = approval
    before = projects.storage.read_committed(workspace.project_id)[0]
    claimed = approval.claim(workspace.project_id, payload)
    with monkeypatch.context() as fault:
        fault.setattr(service.store, "record_reviewed_receipt", lambda *_args: (_ for _ in ()).throw(OSError("receipt unavailable")))
        if not saved:
            fault.setattr(projects.storage, "save", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(AgentFailure, match="AGENT_OUTCOME_UNKNOWN"):
            approval.commit(workspace.project_id, commit_request(payload, claimed))
    assert workspace.project_id in projects.agent_recovery_fences
    restarted = AgentService(projects, runtime, service.connection, tools=service.tools)
    restarted.assistant_protocol_enabled = True
    projects.agent = restarted
    restarted.recover()
    recovered = restarted.approval.recover(workspace.project_id, payload)
    assert recovered.result.receipt.durable is saved
    assert recovered.proposal.state == ("applied" if saved else "failed_before_commit")
    persisted = projects.storage.read_committed(workspace.project_id)[0]
    assert persisted.project_revision == before.project_revision + int(saved)
    assert workspace.project_id not in projects.agent_recovery_fences
    _, run, journal = run_in(restarted.store.load(workspace.project_id), claimed.claim.batch.run_id)
    assert run.state == "interrupted" and not run.allow_edits and not run.outcome_unknown
    assert journal.batches[0].receipt == recovered.result.receipt
    assert not restarted.controls and not runtime.calls


@pytest.mark.asyncio
async def test_lost_claim_reply_can_resume_only_in_memory_and_restart_cannot_apply_it(tmp_path):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    claimed = approval.claim(workspace.project_id, payload)
    assert approval.recover(workspace.project_id, payload, resume=True).claim == claimed
    after_restart = AssistantApproval(service).recover(workspace.project_id, payload)
    assert after_restart.proposal.state == "failed_before_commit" and not after_restart.result.receipt.durable
    assert projects.storage.read_committed(workspace.project_id)[0] == before and not runtime.calls


@pytest.mark.asyncio
async def test_navigation_review_recovers_an_abandoned_claim_without_replaying_it_and_requires_a_new_click(tmp_path):
    from resume_api.agent.proposals import review, review_view
    from resume_api.agent.capabilities import catalog
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    approval.claim(workspace.project_id, payload)
    assert review(service, workspace.project_id)[0].proposal.state == "applying"
    service.leases.close(workspace.project_id, payload.owner)
    recovered = review(service, workspace.project_id)[0]
    assert recovered.proposal.state == "failed_before_commit"
    assert projects.storage.read_committed(workspace.project_id)[0] == before
    owner = service.leases.open(workspace.project_id, "new_window").owner
    assert review_view(service, recovered, catalog(service, workspace.project_id)).apply.state == "available"
    fresh = payload.model_copy(update={"owner": owner, "acceptance_id": "new_window_click"})
    approval.retry(workspace.project_id, fresh)
    assert approval.commit(workspace.project_id, commit_request(fresh, approval.claim(workspace.project_id, fresh))).receipt.durable
    assert len(projects.storage.read_committed(workspace.project_id)[0].mutation_replay) == 1 and not runtime.calls


@pytest.mark.asyncio
async def test_unreadable_application_journal_keeps_private_review_unknown_and_fences_manual_writes(tmp_path):
    from resume_api.agent.proposals import review
    from resume_api.gui_projects import ProjectFailure
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    approval.claim(workspace.project_id, payload)
    service.leases.close(workspace.project_id, payload.owner)
    (service.store.projects / workspace.project_id / "state.json").write_text("{broken")
    unresolved = review(service, workspace.project_id)[0]
    assert unresolved.proposal.state == "outcome_unknown" and unresolved.candidate is not None
    assert workspace.project_id in projects.agent_recovery_fences
    with pytest.raises(ProjectFailure, match="AGENT_OUTCOME_UNKNOWN"):
        projects.require_agent_writable(workspace.project_id)
    assert projects.storage.read_committed(workspace.project_id)[0] == before and not runtime.calls


@pytest.mark.asyncio
async def test_missing_claim_recovery_revokes_the_original_click_before_its_delayed_request_arrives(tmp_path):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    resumed = approval.recover(workspace.project_id, payload, resume=True)
    assert resumed.claim is None and resumed.result is None and resumed.proposal.state == "ready"
    with pytest.raises(AgentFailure, match="AGENT_CANCELLED"):
        approval.claim(workspace.project_id, payload)
    retained = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    assert retained.candidate is not None and payload.acceptance_id in retained.revoked_acceptances
    assert projects.storage.read_committed(workspace.project_id)[0] == before and not runtime.calls


@pytest.mark.asyncio
async def test_interrupted_claim_persistence_aborts_its_orphan_journal_without_a_save(tmp_path, monkeypatch):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    original = service.proposals.update
    calls = []
    def unavailable_once(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise OSError("draft disk full")
        return original(*args, **kwargs)
    monkeypatch.setattr(service.proposals, "update", unavailable_once)
    with pytest.raises(OSError, match="draft disk full"):
        approval.claim(workspace.project_id, payload)
    value = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    _, _, journal = run_in(service.store.load(workspace.project_id), value.proposal.origin_run_id)
    assert value.proposal.state == "ready" and journal.batches[0].receipt.disposition == "cancelled"
    assert workspace.project_id not in projects.agent_recovery_fences
    assert projects.storage.read_committed(workspace.project_id)[0] == before and not runtime.calls


@pytest.mark.asyncio
async def test_post_run_apply_uses_the_existing_attached_canonical_writer_and_history(tmp_path):
    from resume_api.jobs.service import JobService
    from packages.resume_core.background_history import digest_bytes
    from packages.resume_core.models.background import WriterOpenV1, WriterProofV1, WriterAdvanceV1
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    jobs = JobService(projects, None, service.connection, enabled=True)
    projects.background_jobs = jobs
    try:
        current = projects.storage.read_committed(workspace.project_id)[0]
        opened = jobs.writers.open(workspace.project_id, WriterOpenV1(schemaVersion=1, sessionId="reopened_history",
            incarnation="cap_connection", credential="synthetic_cap_writer_credential_0123456789",
            canonicalRevision=current.project_revision, canonicalSha256=digest_bytes(current), actionCursor=0))
        proof = WriterProofV1(schemaVersion=1, lineage=opened.writer.lineage, epoch=opened.writer.epoch,
            sessionId=opened.writer.session_id, incarnation=opened.writer.incarnation,
            credential="synthetic_cap_writer_credential_0123456789")
        header = WriterAdvanceV1(schemaVersion=1, proof=proof, canonicalRevision=current.project_revision,
            canonicalSha256=digest_bytes(current), actionCursor=0)
        claimed = approval.claim(workspace.project_id, payload)
        request = commit_request(payload, claimed).model_copy(update={"writer": header})
        result = approval.commit(workspace.project_id, request)
        assert result.receipt.durable
        state = jobs.store.load(workspace.project_id)
        assert len(state.manual_intents) == 1 and state.manual_intents[0].phase == "receipt_stored"
        assert state.writer.acknowledged_revision == current.project_revision + 1
        assert state.writer.acknowledged_sha256 == digest_bytes(result.project.workspace)
        assert state.writer.acknowledged_cursor == 0 and not state.inverses
        assert content_digest(result.project.workspace) == payload.content_sha256
        assert approval.commit(workspace.project_id, request).receipt == result.receipt
        assert not runtime.calls
    finally:
        await jobs.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["account", "owner", "permission", "content"])
async def test_revocation_after_acceptance_never_saves_or_rebases_the_reviewed_draft(tmp_path, revocation):
    from resume_api.agent.service import AgentConnection
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    claimed = approval.claim(workspace.project_id, payload)
    retained = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    if revocation == "account":
        service.connection = lambda: AgentConnection(True, ("assistant-model",), "account_2")
    elif revocation == "owner":
        service.leases.close(workspace.project_id, payload.owner)
    elif revocation == "permission":
        projects.catalog.update(workspace.project_id, read_only=True)
    else:
        current = projects.workspaces[workspace.project_id]
        next(block for block in current.project.document.blocks() if block.id == "narrative").content[0].text = "Human correction 😀"
        assert projects.persist(workspace.project_id) == "durable"
    before = projects.storage.read_committed(workspace.project_id)[0]
    with pytest.raises(AgentFailure):
        approval.commit(workspace.project_id, commit_request(payload, claimed))
    assert projects.storage.read_committed(workspace.project_id)[0] == before
    current = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    assert current.candidate == retained.candidate and current.proposal.content_sha256 == payload.content_sha256
    assert current.proposal.state == "failed_before_commit" and not runtime.calls


@pytest.mark.asyncio
async def test_applied_payload_compacts_and_expiry_preserves_the_original_journal_receipt(tmp_path):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    value = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    path = service.proposals.directory(workspace.project_id) / service.proposals.filename(value)
    original_size = path.stat().st_size
    claimed = approval.claim(workspace.project_id, payload)
    saved = approval.commit(workspace.project_id, commit_request(payload, claimed))
    compact = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    assert compact.compacted and compact.baseline is compact.candidate is compact.batch is None
    assert not compact.operations and compact.proposal.changes == value.proposal.changes
    assert compact.proposal.content_sha256 == payload.content_sha256 and path.stat().st_size < original_size
    service.store.clock = lambda: "2026-11-10T00:00:00Z"
    expired = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    assert expired.proposal.state == "expired"
    _, _, journal = run_in(service.store.load(workspace.project_id), compact.proposal.origin_run_id)
    assert journal.batches[0].receipt == saved.receipt
    assert service.publication.recover(workspace.project_id, compact.proposal.origin_run_id, claimed.claim.batch.id) == saved.receipt
    assert len(projects.storage.read_committed(workspace.project_id)[0].mutation_replay) == 1 and not runtime.calls


@pytest.mark.asyncio
async def test_private_cleanup_failure_after_the_saved_receipt_remains_saved_and_retries_without_a_write(tmp_path, monkeypatch):
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    claimed = approval.claim(workspace.project_id, payload)
    with monkeypatch.context() as fault:
        fault.setattr(service.proposals, "compact_applied", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("cleanup disk full")))
        saved = approval.commit(workspace.project_id, commit_request(payload, claimed))
        assert saved.receipt.durable
        value = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
        assert value.proposal.state == "applied" and not value.compacted and value.candidate is not None
        assert approval.compaction_errors[workspace.project_id] == "AGENT_STORE_UNAVAILABLE"
        projects.require_agent_writable(workspace.project_id)
        assert workspace.project_id not in projects.agent_recovery_fences
    recovered = approval.recover(workspace.project_id, payload)
    assert recovered.result.receipt == saved.receipt and recovered.proposal.state == "applied"
    assert not approval.compaction_errors and service.proposals.get(workspace.project_id, payload.proposal_id, 1).compacted
    assert len(projects.storage.read_committed(workspace.project_id)[0].mutation_replay) == 1 and not runtime.calls


@pytest.mark.asyncio
async def test_new_application_routes_require_protocol_exact_owner_and_nonce_and_fence_legacy_mutation(tmp_path):
    import httpx
    from fastapi import FastAPI
    from resume_api.agent.routes import mount_agent
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    service.approval = approval
    app = FastAPI(); mount_agent(app, service)
    prefix = f"/v1/rich/projects/{workspace.project_id}/assistant"
    body = payload.model_dump(by_alias=True)
    headers = {"X-FoldCV-Assistant-Protocol": "1"}
    before = projects.storage.read_committed(workspace.project_id)[0]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://synthetic.local") as client:
        missing = await client.post(prefix + "/applications/claim", json=body)
        assert missing.status_code == 409 and missing.json()["error"]["code"] == "AGENT_PROTOCOL"
        for wrong in ({**body, "acceptanceId": None}, {**body, "approved": True}, {**body, "protocolVersion": 2}):
            assert (await client.post(prefix + "/applications/claim", json=wrong, headers=headers)).status_code == 422
        forged = {**body, "owner": {**body["owner"], "token": "synthetic_mcp_bearer_0123456789012345"}}
        assert (await client.post(prefix + "/applications/claim", json=forged, headers=headers)).status_code == 409
        claimed = await client.post(prefix + "/applications/claim", json=body, headers=headers)
        assert claimed.status_code == 200 and claimed.json()["accepted"]["acceptanceId"] == payload.acceptance_id
        batch = claimed.json()["claim"]["batch"]
        legacy = await client.post(prefix + f"/runs/{batch['runId']}/edits/{batch['id']}/claim", json={"owner": body["owner"]}, headers=headers)
        assert legacy.status_code == 409 and legacy.json()["error"]["code"] == "AGENT_PROTOCOL"
        request = {**body, "ticket": claimed.json()["claim"]["ticket"], "requestSha256": batch["requestSha256"]}
        saved = await client.post(prefix + "/applications/commit", json=request, headers=headers)
        assert saved.status_code == 200 and saved.json()["receipt"]["durable"]
        again = await client.post(prefix + "/applications/commit", json=request, headers=headers)
        assert again.json()["receipt"] == saved.json()["receipt"]
    assert projects.storage.read_committed(workspace.project_id)[0].project_revision == before.project_revision + 1
    assert not runtime.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["before_claim", "after_durable"])
async def test_http_stop_can_reach_the_actual_commit_boundary_without_a_live_generation_control(tmp_path, monkeypatch, phase):
    import asyncio
    import threading
    import httpx
    from fastapi import FastAPI
    from resume_api.agent.routes import mount_agent
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    service.approval = approval
    claimed = approval.claim(workspace.project_id, payload)
    before = projects.storage.read_committed(workspace.project_id)[0]
    entered, signaled = threading.Event(), threading.Event()
    original_save, original_cancel = projects.storage.save, approval.signal_cancel
    def signal(project, request):
        subject = original_cancel(project, request)
        signaled.set()
        return subject
    def save(*args, **kwargs):
        name = "before_workspace" if phase == "before_claim" else "after_workspace"
        callback = kwargs[name]
        def boundary(*values):
            if phase == "after_durable":
                callback(*values)
            entered.set()
            assert signaled.wait(3)
            if phase == "before_claim":
                callback(*values)
        return original_save(*args, **{**kwargs, name: boundary})
    monkeypatch.setattr(approval, "signal_cancel", signal)
    monkeypatch.setattr(projects.storage, "save", save)
    app = FastAPI(); mount_agent(app, service)
    prefix = f"/v1/rich/projects/{workspace.project_id}/assistant/applications"
    headers = {"X-FoldCV-Assistant-Protocol": "1"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://synthetic.local") as client:
        applying = asyncio.create_task(client.post(prefix + "/commit", headers=headers, json=commit_request(payload, claimed).model_dump(by_alias=True)))
        assert await asyncio.to_thread(entered.wait, 3)
        stopped = await client.post(prefix + "/cancel", headers=headers, json=payload.model_dump(by_alias=True))
        saved = await applying
    assert stopped.status_code == saved.status_code == 200
    durable = phase == "after_durable"
    assert saved.json()["receipt"]["durable"] is durable
    assert stopped.json()["result"]["receipt"] == saved.json()["receipt"]
    assert stopped.json()["proposal"]["state"] == ("applied" if durable else "failed_before_commit")
    persisted = projects.storage.read_committed(workspace.project_id)[0]
    assert persisted.project_revision == before.project_revision + int(durable)
    assert len(persisted.mutation_replay) == int(durable)
    if not durable:
        assert payload.acceptance_id in service.proposals.get(workspace.project_id, payload.proposal_id, 1).revoked_acceptances
    assert not service.controls and not runtime.calls


@pytest.mark.asyncio
async def test_post_run_native_undo_redo_reuses_the_saved_action_and_original_receipt(tmp_path):
    from tests.recovery.test_agent_publication import manual, block
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    claimed = approval.claim(workspace.project_id, payload)
    saved = approval.commit(workspace.project_id, commit_request(payload, claimed))
    for direction, target in (("undo", before), ("redo", saved.project.workspace)):
        current = projects.read(workspace.project_id)
        request = manual(current, action=claimed.claim.batch.mutation.action_id, kind=direction)
        request.steps[0].block = block(target).model_copy(update={"children": []})
        request.capture.session_id = claimed.claim.batch.mutation.capture.session_id
        result = projects.mutate(workspace.project_id, request)
        assert result.durability == "durable" and content_digest(result.workspace) == content_digest(target)
    _, run, journal = run_in(service.store.load(workspace.project_id), claimed.claim.batch.run_id)
    assert not run.allow_edits and run.saved_batch_id is None and journal.batches[0].receipt == saved.receipt
    assert [action.kind for action in journal.batches[0].history_actions] == ["undo", "redo"]
    assert len(projects.read(workspace.project_id).mutation_replay) == 3 and not runtime.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery", ["normal", "lost_saved", "lost_no_save", "lost_saved_missing_payload", "lost_claim_missing_payload"])
async def test_queued_read_only_origin_uses_its_existing_artifact_journal_and_the_current_ui_writer(tmp_path, monkeypatch, recovery):
    import asyncio
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from packages.resume_core.models.background import WriterAdvanceV1
    from tests.recovery.test_background_agent import environment as queued_environment, hold_writer
    from packages.resume_core.background_history import digest_bytes
    jobs, factory, workspace, request, _, service = await queued_environment(tmp_path)
    service.assistant_protocol_enabled = True
    request.request.allow_edits = False
    observed = []
    async def execute(control, _actor):
        session = jobs.tools.session(control)
        try:
            snapshot = await read_document(session)
            initial, _ = await append(session, "queued_approved", snapshot=snapshot)
            observed.append(await complete(session, initial))
            return ExecutionOutcome(finished_at=jobs.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[request.request.client_request_id] = execute
    try:
        job, _ = await jobs.submit(workspace.project_id, request)
        actor = await factory.actor(job)
        await asyncio.wait_for(jobs.supervisor.controls[job.id].task, 10)
        assert actor.verified_dead() and not jobs.admission.locked() and observed[0]["disposition"] == "draft_ready"
        old = service.leases.require(workspace.project_id)
        from packages.resume_core.models.agent import AgentOwner
        service.leases.close(workspace.project_id, AgentOwner(epoch=old.epoch, token=old.token))
        proof = hold_writer(jobs, workspace)
        owner = service.leases.open(workspace.project_id, proof.session_id).owner
        payload = AssistantAcceptanceV1(protocolVersion=1, proposalId=observed[0]["proposalId"], version=1,
            contentSha256=observed[0]["contentSha256"], acceptanceId="queued_click_1", owner=owner)
        claimed = service.approval.claim(workspace.project_id, payload)
        _, reserved = jobs.artifacts.record(workspace.project_id, job.id)
        reserved_path = jobs.artifacts._path(jobs.store.projects / workspace.project_id, job.submission.input.id)
        assert reserved_path.stat().st_size == reserved.application_control_capacity
        assert len(reserved.application_control_padding) > 32000
        current = jobs.projects.storage.read_committed(workspace.project_id)[0]
        header = WriterAdvanceV1(schemaVersion=1, proof=proof, canonicalRevision=current.project_revision,
            canonicalSha256=digest_bytes(current), actionCursor=0)
        command = commit_request(payload, claimed).model_copy(update={"writer": header})
        if recovery == "normal":
            saved = service.approval.commit(workspace.project_id, command)
        else:
            from packages.resume_core.agent_artifacts import JobArtifactView
            from resume_api.agent.service import AgentService
            if recovery != "lost_claim_missing_payload":
                with monkeypatch.context() as fault:
                    fault.setattr(JobArtifactView, "record_reviewed_receipt", lambda *_args: (_ for _ in ()).throw(OSError("lost UI receipt")))
                    if recovery == "lost_no_save":
                        fault.setattr(jobs.publisher, "apply_reviewed", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))
                    with pytest.raises(AgentFailure, match="AGENT_OUTCOME_UNKNOWN"):
                        service.approval.commit(workspace.project_id, command)
            if recovery.endswith("missing_payload"):
                value = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
                (service.proposals.directory(workspace.project_id) / service.proposals.filename(value)).unlink()
            restarted = AgentService(jobs.projects, service.runtime, service.connection, tools=service.tools)
            restarted.assistant_protocol_enabled = True
            jobs.projects.agent, jobs.projects.background_jobs = restarted, None
            restarted.recover()
            assert not restarted.startup_errors
            if not recovery.endswith("missing_payload"):
                assert workspace.project_id in jobs.projects.agent_recovery_fences
            jobs.projects.background_jobs = jobs
            restarted.approval.recover_all()
            saved = restarted.approval.recover(workspace.project_id, payload).result
            assert not jobs.projects.agent_recovery_fences and not restarted.controls
        assert saved.receipt.durable is (recovery not in {"lost_no_save", "lost_claim_missing_payload"})
        if saved.receipt.durable:
            assert content_digest(saved.project.workspace) == payload.content_sha256
        artifact = jobs.artifacts.record(workspace.project_id, job.id)[1]
        assert not artifact.batches and len(artifact.applications) == 1 and artifact.applications[0].receipt == saved.receipt
        assert not service.store.load(workspace.project_id).journals
        persisted_job = jobs.store.read(workspace.project_id, job.id)
        assert persisted_job.execution == "completed" and persisted_job.publication == "none" and persisted_job.receipt is None
        if not recovery.endswith("missing_payload"):
            assert service.proposals.get(workspace.project_id, payload.proposal_id, 1).compacted is saved.receipt.durable
        assert len(factory.calls) == 1 and not service.runtime.calls
    finally:
        await jobs.shutdown()
        factory.verify(); jobs.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_model_bearer_and_changed_digest_cannot_obtain_a_ui_ticket(tmp_path):
    approval, _, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0]
    from packages.resume_core.models.agent import AgentOwner
    forged = payload.model_copy(update={"owner": AgentOwner(epoch=payload.owner.epoch, token="synthetic_model_bearer_0123456789012345")})
    with pytest.raises(AgentFailure, match="AGENT_OWNER_MISMATCH"):
        approval.claim(workspace.project_id, forged)
    with pytest.raises(AgentFailure, match="AGENT_IDEMPOTENCY_CONFLICT"):
        approval.claim(workspace.project_id, payload.model_copy(update={"content_sha256": "f" * 64}))
    assert projects.storage.read_committed(workspace.project_id)[0] == before and not runtime.calls


@pytest.mark.asyncio
async def test_local_commit_after_generation_deadline_saves_exact_displayed_content_once_without_inference(tmp_path):
    from resume_api.agent.service import AgentConnection
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    service.connection = lambda: AgentConnection(False, (), "account_1")
    before = projects.storage.read_committed(workspace.project_id)[0]
    claimed = approval.claim(workspace.project_id, payload)
    request = AssistantApplicationCommitV1.model_validate({**payload.model_dump(by_alias=True),
        "ticket": claimed.claim.ticket, "requestSha256": claimed.claim.batch.request_sha256})
    result = approval.commit(workspace.project_id, request)
    again = approval.commit(workspace.project_id, request)
    assert result.receipt == again.receipt and result.receipt.durable
    persisted = projects.storage.read_committed(workspace.project_id)[0]
    assert content_digest(persisted) == payload.content_sha256
    assert persisted.project_revision == before.project_revision + 1 and len(persisted.mutation_replay) == 1
    state = service.store.load(workspace.project_id)
    _, run, journal = run_in(state, claimed.claim.batch.run_id)
    assert run.state == "interrupted" and run.deadline == "2000-01-01T00:00:00Z"
    assert run.saved_batch_id is None and not run.allow_edits and not run.outcome_unknown and len(journal.batches) == 1
    assert journal.batches[0].receipt == result.receipt
    retained = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    assert retained.proposal.state == "applied" and retained.approval.phase == "receipt_stored"
    assert not service.controls and not runtime.calls
