"""Project-action candidates are exact local drafts with explicit consequences."""

import pytest

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.assistant_actions import action_content_digest, lifecycle_preview, workspace_action_candidate
from packages.resume_core.assistant_proposals import content_digest
from packages.resume_core.models.agent import AgentProjectAction
from packages.resume_core.rich_limits import ImageReferences
from tests.recovery.test_agent_lifecycle import setup
from tests.recovery.test_rich_persistence import image_asset


def test_metadata_candidates_change_the_review_digest_without_saving_document_or_facts(tmp_path):
    _, runtime, projects, workspace, _, _, _ = setup(tmp_path, None)
    before = projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
    original = action_content_digest(workspace)
    for action, value in (("rename", "Синтетический заголовок 😀"), ("formatting_date", "2025-11")):
        request = AgentProjectAction(key=action, snapshotId="resources_1", action=action, value=value)
        candidate, result = workspace_action_candidate(workspace, request)
        assert action_content_digest(candidate) != original and content_digest(candidate) == content_digest(workspace)
        assert candidate.project_revision == workspace.project_revision and not result
        assert projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before
    assert not runtime.calls


def test_delete_preview_requires_the_exact_project_and_names_its_irreversible_target(tmp_path):
    _, runtime, projects, workspace, _, _, _ = setup(tmp_path, None)
    request = AgentProjectAction(key="delete", snapshotId="resources_1", action="delete")
    for target in (None, "another_project"):
        with pytest.raises(AgentFailure, match="AGENT_ARGUMENT_INVALID"):
            lifecycle_preview(workspace, request.model_copy(update={"target_id": target}), archived=False)
    before, after, reason = lifecycle_preview(workspace, request.model_copy(update={"target_id": workspace.project_id}), archived=False)
    assert workspace.title in before and workspace.project_id in before and after == "Удалён"
    assert "окончательно" in reason and "Отмены в редакторе нет" in reason
    assert not projects.storage.registry().entries[0].tombstoned and not runtime.calls


def test_image_removal_requires_current_live_history_and_inflight_reference_proof(tmp_path):
    _, runtime, projects, workspace, _, _, _ = setup(tmp_path, None)
    asset, _ = image_asset(workspace)
    request = AgentProjectAction(key="remove", snapshotId="resources_1", action="remove_asset", targetId=asset.id)
    for references in (None, ImageReferences(live=(asset.id,)), ImageReferences(history=(asset.id,)), ImageReferences(in_flight=(asset.id,))):
        with pytest.raises(AgentFailure, match="AGENT_EVIDENCE_INVALID"):
            workspace_action_candidate(workspace, request, image_references=references)
    candidate, _ = workspace_action_candidate(workspace, request, image_references=ImageReferences())
    assert asset.id not in {item.id for item in candidate.project.assets}
    assert asset.id in {item.id for item in workspace.project.assets} and not runtime.calls
    assert projects.storage.read_committed(workspace.project_id)[0].project_revision == workspace.project_revision


@pytest.mark.asyncio
async def test_read_only_project_action_draft_survives_review_with_exact_metadata_and_no_write(tmp_path):
    from packages.resume_core.models.assistant_actions import AssistantProjectActionPrepareV1, AssistantStoredActionV1
    from packages.resume_core.models.assistant_capabilities import AssistantTaskRequestV1
    from resume_api.agent.action_proposals import prepare_action
    from resume_api.agent.proposals import review
    from tests.recovery.test_assistant_proposals import environment
    from tests.recovery.test_manual_qa_project_actions import complete_resources
    service, runtime, projects, workspace, session = environment(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
    try:
        planned = await session.call("get_project_resources", AssistantTaskRequestV1(protocolVersion=1, taskId="project_metadata", scope="project"))
        assert planned["availability"]["state"] == "available"
        wrapper = AssistantProjectActionPrepareV1(protocolVersion=1, request=AgentProjectAction(key="rename_review",
            snapshotId=complete_resources(session), action="rename", value="Синтетический проект 😀"))
        draft = await prepare_action(session, wrapper)
        assert draft["disposition"] == "draft_ready" and not draft["durable"]
        assert await prepare_action(session, wrapper) == draft
        stored = service.proposals.get(workspace.project_id, draft["proposalId"], 1)
        assert isinstance(stored, AssistantStoredActionV1) and stored.batch is None
        assert stored.candidate.title == "Синтетический проект 😀" and stored.candidate.title_manually_set
        assert content_digest(stored.candidate) == content_digest(workspace)
        assert "закреплено пользователем" in stored.proposal.changes[0].after
        assert review(service, workspace.project_id)[0].proposal.state == "ready"
        assert projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before
        assert not service.store.load(workspace.project_id).journals[0].batches and not runtime.calls
    finally:
        await session.close()


async def ready_action(tmp_path, action, value="", target=None):
    from packages.resume_core.models.assistant_actions import AssistantProjectActionPrepareV1
    from packages.resume_core.models.assistant_approval import AssistantAcceptanceV1
    from packages.resume_core.models.assistant_capabilities import AssistantTaskRequestV1
    from packages.resume_core.agent_store import run_in
    from resume_api.agent.action_proposals import prepare_action, ACTION_TASKS
    from tests.recovery.test_assistant_proposals import environment
    from tests.recovery.test_manual_qa_project_actions import complete_resources
    service, runtime, projects, workspace, session = environment(tmp_path, message=value if action in {"add_source_text", "import_asset"} else None)
    if action == "remove_asset":
        current = projects.workspaces[workspace.project_id]
        asset, blob = image_asset(current)
        current.project.document.regions[2].blocks = [item for item in current.project.document.regions[2].blocks if item.id != "test-image"]
        projects.images[workspace.project_id, asset.id] = blob
        assert projects.persist(workspace.project_id) == "durable"
        target = asset.id
    elif action == "remove_source":
        import hashlib
        from packages.resume_core.models.contracts import Source
        blob = b"Unused synthetic source"
        source = Source(id="unused-source", revision=1, originalName="synthetic-unused.txt", mimeType="text/plain",
            byteSha256=hashlib.sha256(blob).hexdigest(), byteRef="sources/unused-source/original", parser="text", parserVersion="fixture-v1",
            units=[], overlays=[], warnings=[])
        projects.workspaces[workspace.project_id].project.sources.append(source)
        projects.originals[workspace.project_id, source.id] = blob
        assert projects.persist(workspace.project_id) == "durable"
        target = source.id
    if action == "restore":
        projects.catalog.update(workspace.project_id, archived=True)
    try:
        planned = await session.call("get_project_resources", AssistantTaskRequestV1(protocolVersion=1, taskId=ACTION_TASKS[action], scope="project"))
        assert planned["availability"]["state"] == "available"
        draft = await prepare_action(session, AssistantProjectActionPrepareV1(protocolVersion=1, request=AgentProjectAction(
            key="review_action", snapshotId=complete_resources(session), action=action, value=value,
            targetId=workspace.project_id if action == "delete" else target)))
        assert draft["disposition"] == "draft_ready", draft
        await session.close()
        service.store.finish(workspace.project_id, session.run.id, "interrupted", error="AGENT_INTERRUPTED")
        lease = service.leases.require(workspace.project_id)
        from packages.resume_core.models.agent import AgentOwner
        payload = AssistantAcceptanceV1(protocolVersion=1, proposalId=draft["proposalId"], version=1,
            contentSha256=draft["contentSha256"], acceptanceId="click_1", owner=AgentOwner(epoch=lease.epoch, token=lease.token))
        return service, runtime, projects, workspace, payload
    finally:
        await session.close()


def action_commit(payload, claimed):
    from packages.resume_core.models.assistant_approval import AssistantApplicationCommitV1
    return AssistantApplicationCommitV1.model_validate({**payload.model_dump(by_alias=True),
        "ticket": claimed.ticket, "requestSha256": claimed.request_sha256})


@pytest.mark.asyncio
@pytest.mark.parametrize("action,value", [("rename", "Reviewed title 😀"), ("formatting_date", "2025-11"),
    ("archive", ""), ("restore", ""), ("add_source_text", "Literal source supplied by the user 42."),
    ("remove_asset", ""), ("remove_source", "")])
async def test_explicit_action_after_generation_uses_one_catalog_receipt_and_preserves_text_history(tmp_path, action, value):
    service, runtime, projects, workspace, payload = await ready_action(tmp_path, action, value)
    before = projects.storage.read_committed(workspace.project_id)[0]
    coordinator = service.action_approval
    claim = coordinator.claim(workspace.project_id, payload)
    assert coordinator.claim(workspace.project_id, payload) == claim
    assert projects.storage.read_committed(workspace.project_id)[0] == before and not projects.catalog.actions()
    result = await coordinator.commit(workspace.project_id, action_commit(payload, claim))
    assert result.operation.durable and result.proposal.state == "applied"
    assert await coordinator.commit(workspace.project_id, action_commit(payload, claim)) == result
    retained = projects.storage.read_committed(workspace.project_id)[0]
    assert retained.project.document == before.project.document and retained.project.facts == before.project.facts
    assert len(projects.catalog.actions()) == 1 and not service.store.load(workspace.project_id).journals[0].batches
    if action == "rename":
        assert retained.title == value
    elif action == "formatting_date":
        assert retained.formatting_as_of.year == 2025 and retained.formatting_as_of.month == 11
    elif action in {"archive", "restore"}:
        assert projects.catalog.get(workspace.project_id).archived == (action == "archive")
    elif action == "add_source_text":
        assert retained.project.sources[-1].units[0].text == value
        import json
        assert value not in json.dumps(projects.catalog.actions())
    elif action == "remove_source":
        assert not retained.project.sources
    else:
        assert not retained.project.assets
    assert not runtime.calls


@pytest.mark.asyncio
async def test_stop_revokes_a_project_action_click_and_needs_a_fresh_explicit_retry(tmp_path):
    service, runtime, projects, workspace, payload = await ready_action(tmp_path, "rename", "Reviewed title")
    coordinator = service.action_approval
    claimed = coordinator.claim(workspace.project_id, payload)
    stopped = coordinator.cancel(workspace.project_id, payload)
    assert stopped.proposal.state == "failed_before_commit"
    with pytest.raises(AgentFailure):
        await coordinator.commit(workspace.project_id, action_commit(payload, claimed))
    fresh = payload.model_copy(update={"acceptance_id": "click_2"})
    coordinator.retry(workspace.project_id, fresh)
    saved = await coordinator.commit(workspace.project_id, action_commit(fresh, coordinator.claim(workspace.project_id, fresh)))
    assert saved.operation.durable and saved.project.workspace.title == "Reviewed title"
    assert not runtime.calls


@pytest.mark.asyncio
async def test_old_action_recovery_and_stop_cannot_cancel_the_new_explicit_retry(tmp_path, monkeypatch):
    from packages.resume_core.project_store import ProjectStoreFailure
    service, runtime, projects, workspace, payload = await ready_action(tmp_path, "rename", "Reviewed title")
    coordinator = service.action_approval
    first = coordinator.claim(workspace.project_id, payload)
    with monkeypatch.context() as fault:
        fault.setattr(projects.storage, "save", lambda *_args, **_kwargs: (_ for _ in ()).throw(ProjectStoreFailure("PROJECT_SAVE_FAILED")))
        failed = await coordinator.commit(workspace.project_id, action_commit(payload, first))
    assert not failed.operation.durable
    fresh = payload.model_copy(update={"acceptance_id": "click_2"})
    coordinator.retry(workspace.project_id, fresh)
    second = coordinator.claim(workspace.project_id, fresh)
    assert not coordinator.recover(workspace.project_id, payload).operation.durable
    coordinator.cancel(workspace.project_id, payload)
    current = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    assert current.proposal.state == "applying" and current.approval.acceptance_id == "click_2"
    assert current.approval.phase == "accepted"
    saved = await coordinator.commit(workspace.project_id, action_commit(fresh, second))
    assert saved.operation.durable and len(projects.storage.read_committed(workspace.project_id)[0].mutation_replay) == 1
    assert not runtime.calls


@pytest.mark.asyncio
async def test_reviewed_delete_uses_exact_target_and_recovers_receipt_after_private_project_cleanup(tmp_path):
    service, runtime, projects, workspace, payload = await ready_action(tmp_path, "delete")
    coordinator = service.action_approval
    claim = coordinator.claim(workspace.project_id, payload)
    saved = await coordinator.commit(workspace.project_id, action_commit(payload, claim))
    assert saved.proposal.state == "applied" and saved.project is None
    assert saved.operation.durable and saved.operation.status == "deleted"
    assert coordinator.recover(workspace.project_id, payload) == saved
    assert await coordinator.commit(workspace.project_id, action_commit(payload, claim)) == saved
    assert not (projects.storage.projects / workspace.project_id).exists() and not runtime.calls
    assert not service.proposals.directory(workspace.project_id).exists()


@pytest.mark.asyncio
async def test_project_cleanup_never_follows_a_private_draft_symlink_and_reports_incomplete_until_repaired(tmp_path):
    service, runtime, projects, workspace, payload = await ready_action(tmp_path, "delete")
    value = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    path = service.proposals.directory(workspace.project_id) / service.proposals.filename(value)
    outside = tmp_path / "unrelated.txt"
    outside.write_text("Keep this synthetic unrelated file")
    path.unlink()
    path.symlink_to(outside)
    result = await projects.delete_project(workspace.project_id)
    assert result.status == "cleanup_incomplete" and path.is_symlink()
    assert outside.read_text() == "Keep this synthetic unrelated file"
    path.unlink()
    result = await projects.delete_project(workspace.project_id)
    assert result.status == "deleted" and not service.proposals.directory(workspace.project_id).exists()
    assert outside.read_text() == "Keep this synthetic unrelated file" and not runtime.calls


@pytest.mark.asyncio
async def test_restart_cleanup_finishes_the_original_reviewed_delete_without_a_second_apply(tmp_path, monkeypatch):
    service, runtime, projects, workspace, payload = await ready_action(tmp_path, "delete")
    coordinator = service.action_approval
    claimed = coordinator.claim(workspace.project_id, payload)
    with monkeypatch.context() as fault:
        fault.setattr(service.store, "cleanup_deleted", lambda *_args: (_ for _ in ()).throw(AgentFailure("AGENT_CLEANUP_INCOMPLETE")))
        uncertain = await coordinator.commit(workspace.project_id, action_commit(payload, claimed))
    assert uncertain.operation.status == "cleanup_incomplete" and not uncertain.operation.durable
    assert uncertain.proposal.state == "outcome_unknown"
    assert projects.storage.registry().entries[0].tombstoned
    await projects.drain_catalog_actions()
    recovered = coordinator.recover(workspace.project_id, payload)
    assert recovered.operation.id == uncertain.operation.id and recovered.operation.status == "deleted"
    assert recovered.operation.durable and recovered.proposal.state == "applied"
    assert not service.proposals.directory(workspace.project_id).exists()
    assert len(projects.catalog.actions()) == 1 and not runtime.calls


@pytest.mark.asyncio
async def test_reviewed_image_uses_exact_user_bytes_and_never_claims_editor_undo(tmp_path):
    import base64
    from io import BytesIO
    from PIL import Image
    stream = BytesIO()
    Image.new("RGB", (3, 2), "red").save(stream, format="PNG")
    service, runtime, projects, workspace, payload = await ready_action(tmp_path, "import_asset", base64.b64encode(stream.getvalue()).decode())
    coordinator = service.action_approval
    value = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    assert "В истории текста отмены этого действия нет" in value.action.preview.consequence
    assert value.action.preview.image_preview_url.endswith("/versions/1/image-preview")
    assert not projects.images
    result = await coordinator.commit(workspace.project_id, action_commit(payload, coordinator.claim(workspace.project_id, payload)))
    asset = result.project.workspace.project.assets[-1]
    assert asset.width == 3 and asset.height == 2 and result.operation.durable
    from packages.resume_core.rich_images import normalize_image
    assert projects.images[workspace.project_id, asset.id] == normalize_image(stream.getvalue(), asset.id)[1]
    assert not runtime.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["lost_saved_reply", "known_no_save"])
async def test_project_action_reconciles_original_catalog_intent_without_repeating_the_save(tmp_path, monkeypatch, failure):
    service, runtime, projects, workspace, payload = await ready_action(tmp_path, "rename", "Reviewed title")
    from packages.resume_core.project_store import ProjectStoreFailure
    from resume_api.agent.action_approval import AssistantActionApproval
    original = projects.storage.save
    calls = []
    def interrupted(*args, **kwargs):
        calls.append(1)
        if failure == "lost_saved_reply":
            original(*args, **kwargs)
        raise ProjectStoreFailure("PROJECT_SAVE_FAILED")
    monkeypatch.setattr(projects.storage, "save", interrupted)
    coordinator = service.action_approval
    request = action_commit(payload, coordinator.claim(workspace.project_id, payload))
    result = await coordinator.commit(workspace.project_id, request)
    assert result.operation.durable == (failure == "lost_saved_reply")
    assert result.proposal.state == ("applied" if failure == "lost_saved_reply" else "failed_before_commit")
    recovered = AssistantActionApproval(service).recover(workspace.project_id, payload)
    assert recovered == result and calls == [1] and not runtime.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["owner_closed", "read_only", "changed_content"])
async def test_reviewed_action_rechecks_current_authority_and_baseline_before_commit(tmp_path, boundary):
    service, runtime, projects, workspace, payload = await ready_action(tmp_path, "rename", "Reviewed title")
    coordinator = service.action_approval
    request = action_commit(payload, coordinator.claim(workspace.project_id, payload))
    if boundary == "owner_closed":
        service.leases.close(workspace.project_id, payload.owner)
    elif boundary == "read_only":
        projects.catalog.update(workspace.project_id, read_only=True)
    else:
        projects.workspaces[workspace.project_id].title = "Human title"
        assert projects.persist(workspace.project_id) == "durable"
    before = projects.storage.read_committed(workspace.project_id)[1]
    with pytest.raises(AgentFailure):
        await coordinator.commit(workspace.project_id, request)
    assert projects.storage.read_committed(workspace.project_id)[1] == before
    assert not projects.catalog.actions() and not runtime.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("action,value", [("rename", "Reviewed title"), ("remove_asset", ""), ("remove_source", "")])
async def test_metadata_action_uses_attached_writer_snapshot_without_a_second_history_action(tmp_path, action, value):
    from resume_api.jobs.service import JobService
    from packages.resume_core.background_history import digest_bytes
    from packages.resume_core.models.background import WriterOpenV1, WriterProofV1, WriterAdvanceV1
    service, runtime, projects, workspace, payload = await ready_action(tmp_path, action, value)
    jobs = JobService(projects, None, service.connection, enabled=True)
    projects.background_jobs = jobs
    try:
        current = projects.storage.read_committed(workspace.project_id)[0]
        opened = jobs.writers.open(workspace.project_id, WriterOpenV1(schemaVersion=1, sessionId="history_1",
            incarnation="cap_action", credential="synthetic_cap_action_credential_0123456789",
            canonicalRevision=current.project_revision, canonicalSha256=digest_bytes(current), actionCursor=0))
        proof = WriterProofV1(schemaVersion=1, lineage=opened.writer.lineage, epoch=opened.writer.epoch,
            sessionId="history_1", incarnation="cap_action", credential="synthetic_cap_action_credential_0123456789")
        header = WriterAdvanceV1(schemaVersion=1, proof=proof, canonicalRevision=current.project_revision,
            canonicalSha256=digest_bytes(current), actionCursor=0)
        coordinator = service.action_approval
        command = action_commit(payload, coordinator.claim(workspace.project_id, payload)).model_copy(update={"writer": header})
        saved = await coordinator.commit(workspace.project_id, command)
        assert saved.operation.durable
        if action == "rename":
            assert saved.project.workspace.title == "Reviewed title"
        state = jobs.store.load(workspace.project_id)
        assert len(state.manual_intents) == 1 and state.manual_intents[0].phase == "receipt_stored"
        assert state.writer.acknowledged_revision == saved.project.workspace.project_revision
        assert state.writer.acknowledged_cursor == 0 and not state.inverses
        assert not runtime.calls
    finally:
        await jobs.shutdown()
