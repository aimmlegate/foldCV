"""Durable draft assembly uses no canonical publication or model dispatch."""

import json
import time
import asyncio

import pytest

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.assistant_proposals import AssistantProposals
from packages.resume_core.models.agent import AgentQuery, AgentReadSnapshot
from packages.resume_core.models.assistant_capabilities import AssistantTaskRequestV1
from packages.resume_core.models.assistant_proposals import AssistantAssemblyRequestV1
from tests.recovery.test_agent_lifecycle import setup
from tests.recovery.test_agent_tools import Fetcher
from tests.recovery.test_agent_edits import replace
from resume_api.agent.service import RunControl
from resume_api.agent.tools import ToolSession


def environment(tmp_path, *, edits=False, selected=False, message=None):
    service, runtime, projects, workspace, _, request, _ = setup(tmp_path, None)
    service.assistant_protocol_enabled = True
    changes = {"allow_edits": edits}
    if message is not None:
        changes["message"] = message
    if selected:
        from tests.recovery.test_agent_edits import selection
        changes["scope"] = selection(workspace, "narrative", 0, 6)
    run, _ = service.submit(workspace.project_id, request.model_copy(update=changes))
    control = RunControl(workspace.project_id, run.id, run.owner_epoch, run.connection_epoch, time.monotonic())
    session = ToolSession(service, control, run, Fetcher())
    return service, runtime, projects, workspace, session


def test_new_tool_protocol_has_a_distinct_compatibility_identity_without_a_probe(tmp_path):
    from resume_api.agent.tools import AgentTools
    service, runtime, _, workspace, _, _, _ = setup(tmp_path, None)
    service.tools = AgentTools(service, fetcher=Fetcher())
    old = service.capabilities(workspace.project_id)
    service.assistant_protocol_enabled = True
    current = service.capabilities(workspace.project_id)
    assert "apply_edit_batch" in old.tools and "apply_edit_batch" not in current.tools
    assert current.protocol_sha256 != old.protocol_sha256 and current.config_sha256 != old.config_sha256
    assert all(model.state == "unverified" for model in current.models)
    assert not runtime.calls


def test_reviewed_digest_includes_rich_references_and_excludes_derived_revisions(tmp_path):
    from packages.resume_core.assistant_proposals import content_digest
    _, _, _, workspace, _, _, _ = setup(tmp_path, None)
    value = workspace.model_copy(deep=True)
    original = content_digest(value)
    value.project.facts.revision += 1
    value.project.document.blocks()[0].revision += 1
    assert content_digest(value) == original
    narrative = next(block for block in value.project.document.blocks() if block.id == "narrative")
    narrative.content[0].styles.bold = not narrative.content[0].styles.bold
    assert content_digest(value) != original


def test_corrupt_proposal_namespace_disables_assistant_recovery_without_blocking_manual_document(tmp_path):
    from resume_api.agent.capabilities import catalog
    service, runtime, projects, workspace, _, _, _ = setup(tmp_path, None)
    service.assistant_protocol_enabled = True
    outside = tmp_path / "unrelated"; outside.mkdir()
    service.proposals.root.symlink_to(outside, target_is_directory=True)
    service.recover()
    assert service.proposal_recovery_error == "AGENT_STORE_CORRUPT"
    assert not service.capabilities(workspace.project_id).ready
    assert all(task.review.state == "temporarily_unavailable" for task in catalog(service, workspace.project_id).tasks if task.id == "rewrite_resume")
    assert projects.read(workspace.project_id).project is not None
    assert list(outside.iterdir()) == [] and not runtime.calls


async def read_document(session, task_id="rewrite_resume"):
    task = await session.call("get_project_resources", AssistantTaskRequestV1(protocolVersion=1, taskId=task_id))
    assert task["availability"]["state"] == "available"
    for tool, kind in (("get_resume_context", "context"), ("get_working_facts", "facts")):
        query = AgentQuery(kind=kind)
        page = await session.call(tool, query)
        while page["snapshot"]["nextCursor"]:
            page = await session.call(tool, query.model_copy(update={"cursor": page["snapshot"]["nextCursor"]}))
    query = AgentQuery(kind="document")
    page = await session.call("get_resume_context", query)
    first = AgentReadSnapshot.model_validate(page["snapshot"])
    while page["snapshot"]["nextCursor"]:
        page = await session.call("get_resume_context", query.model_copy(update={"cursor": page["snapshot"]["nextCursor"]}))
    return first


async def append(session, key, *, snapshot=None, text="Clear", proposal=None, phase="append", unchanged=(), task_id="rewrite_resume"):
    operations = [replace(snapshot, "narrative", 0, 6, text)] if snapshot else []
    request = AssistantAssemblyRequestV1(protocolVersion=1, key=key, taskId=task_id, phase=phase,
        proposalId=proposal, operations=operations, snapshotIds=[snapshot.id] if snapshot else [], unchanged=list(unchanged))
    return await session.call("prepare_edit_batch", request), request


async def complete(session, initial, task_id="rewrite_resume"):
    current, index = initial, 0
    while current["unresolvedUnits"]:
        declarations = [{"unitId": unit["unitId"], "reason": "Сохранить текущую часть без изменений."} for unit in current["coverage"] if unit["state"] == "unresolved"]
        assert declarations
        current, _ = await append(session, "coverage_" + str(index), proposal=current["proposalId"], unchanged=declarations, task_id=task_id)
        assert "error" not in current, current
        index += 1
        assert index < 10
    final, _ = await append(session, "finalize", proposal=current["proposalId"], phase="finalize", task_id=task_id)
    return final


@pytest.mark.asyncio
async def test_read_only_multicall_draft_is_durable_without_document_history_or_apply(tmp_path):
    service, runtime, projects, workspace, session = environment(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
    try:
        assert "apply_edit_batch" not in session.names
        listed = await session.sdk.list_tools()
        assert "apply_edit_batch" not in {tool.name for tool in listed}
        advertised = json.dumps(next(tool.inputSchema for tool in listed if tool.name == "prepare_edit_batch"))
        assert '"protocolVersion"' in advertised and '"phase"' in advertised and '"approved"' not in advertised
        snapshot = await read_document(session)
        initial, request = await append(session, "first", snapshot=snapshot)
        assert initial["disposition"] == "building" and not initial["durable"]
        replay = await session.call("prepare_edit_batch", request)
        assert replay == initial
        changed = request.model_copy(deep=True); changed.operations[0].content[0].text = "Different"
        assert (await session.call("prepare_edit_batch", changed))["error"]["code"] == "AGENT_IDEMPOTENCY_CONFLICT"
        ready = await complete(session, initial)
        assert ready["disposition"] == "draft_ready" and not ready["durable"] and ready["unresolvedUnits"] == 0
        saved = AssistantProposals(service.store).get(workspace.project_id, ready["proposalId"], 1)
        assert saved.proposal.state == "ready" and saved.batch is not None
        assert saved.candidate != saved.baseline
        assert saved.proposal.changes and saved.proposal.content_sha256 == ready["contentSha256"]
        assert len(saved.calls) > 1 and len(saved.operations) == 1
        assert (await session.call("apply_edit_batch", {}))["error"]["code"] == "AGENT_TOOL_DENIED"
        assert projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before
        assert not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_interrupted_build_survives_reopen_and_never_becomes_ready_implicitly(tmp_path):
    service, runtime, projects, workspace, session = environment(tmp_path)
    try:
        snapshot = await read_document(session)
        draft, _ = await append(session, "first", snapshot=snapshot)
        reopened = AssistantProposals(service.store)
        assert reopened.recover() == {}
        retained = reopened.get(workspace.project_id, draft["proposalId"], 1)
        assert retained.proposal.state == "incomplete"
        assert retained.candidate and retained.proposal.changes
        assert retained.proposal.operation_count == 1
        assert not projects.storage.read_committed(workspace.project_id)[0].mutation_replay
        assert not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_partial_finalize_and_no_op_are_distinct_and_neither_creates_history(tmp_path):
    service, runtime, projects, workspace, session = environment(tmp_path)
    try:
        snapshot = await read_document(session)
        initial, _ = await append(session, "first", snapshot=snapshot, text="Styled")
        no_change = await complete(session, initial)
        assert no_change["disposition"] == "no_change" and no_change["proposalId"] is None
        assert not no_change["durable"] and not projects.storage.read_committed(workspace.project_id)[0].mutation_replay
        assert not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_expiry_corruption_and_cancelled_authority_preserve_canonical_bytes(tmp_path):
    service, _, projects, workspace, session = environment(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
    try:
        snapshot = await read_document(session)
        initial, _ = await append(session, "first", snapshot=snapshot)
        ready = await complete(session, initial)
        service.proposals.finish(workspace.project_id, session.run.id, cancelled=True)
        cancelled = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        assert cancelled.proposal.state == "discarded"
        service.store.clock = lambda: "2099-01-01T00:00:00Z"
        expired = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        assert expired.proposal.state == "expired" and expired.candidate is None and expired.batch is None
        path = service.proposals.directory(workspace.project_id) / service.proposals.filename(expired)
        envelope = json.loads(path.read_text()); envelope["payload"]["proposal"]["state"] = "ready"
        path.write_text(json.dumps(envelope))
        with pytest.raises(AgentFailure, match="AGENT_STORE_CORRUPT"):
            service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        assert projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_generation_finishes_with_a_ready_draft_and_releases_the_permit(tmp_path):
    from resume_api.agent.runtime import RuntimeResult
    from resume_api.agent.tools import AgentTools
    from resume_api.inference_admission import INFERENCE
    sessions = []
    async def script(_value, _cancel, _emit):
        session = sessions[0]
        snapshot = await read_document(session)
        initial, _ = await append(session, "first", snapshot=snapshot)
        ready = await complete(session, initial)
        assert ready["disposition"] == "draft_ready"
        return RuntimeResult(state="completed", text="Вариант готов. Документ не изменён.", tool_calls=session.calls)
    service, runtime, projects, workspace, _, request, _ = setup(tmp_path, script)
    service.assistant_protocol_enabled = True
    class CapturedTools(AgentTools):
        async def open(self, *args):
            session = await super().open(*args)
            sessions.append(session)
            return session
    service.tools = CapturedTools(service, fetcher=Fetcher())
    before = projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
    run, _ = service.submit(workspace.project_id, request.model_copy(update={"allow_edits": False}))
    control = service.start(workspace.project_id, run.id)
    try:
        await asyncio.wait_for(control.task, 10)
        from packages.resume_core.agent_store import run_in
        finished = run_in(service.store.load(workspace.project_id), run.id)[1]
        assert finished.state == "completed" and finished.saved_batch_id is None
        assert service.proposals.list(workspace.project_id)[0].proposal.state == "ready"
        assert not INFERENCE.locked() and not sessions[0].active
        assert projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before
        assert runtime.native is False and runtime.calls == ["assistant-model"]
    finally:
        await service.stop_all()


@pytest.mark.asyncio
async def test_queued_check_only_completion_never_enters_background_publication(tmp_path):
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from tests.recovery.test_background_agent import environment as queued_environment
    jobs, factory, workspace, payload, _, service = await queued_environment(tmp_path)
    service.assistant_protocol_enabled = True
    payload.request.allow_edits = False
    before = jobs.projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
    observed = []
    async def execute(control, _actor):
        session = jobs.tools.session(control)
        try:
            assert "prepare_edit_batch" in control.job.submission.tools
            assert "apply_edit_batch" not in session.names
            snapshot = await read_document(session)
            initial, _ = await append(session, "first", snapshot=snapshot)
            observed.append(await complete(session, initial))
            return ExecutionOutcome(finished_at=jobs.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = execute
    try:
        job, _ = await jobs.submit(workspace.project_id, payload)
        await factory.actor(job)
        await asyncio.wait_for(jobs.supervisor.controls[job.id].task, 10)
        assert observed[0]["disposition"] == "draft_ready"
        saved = jobs.store.read(workspace.project_id, job.id)
        assert saved.publication == "none" and saved.receipt is None
        assert not jobs.store.load(workspace.project_id).proposals
        assert jobs.projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before
    finally:
        await jobs.shutdown()
        factory.verify(); jobs.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_ready_version_is_immutable_and_capacity_failure_keeps_the_prior_draft(tmp_path, monkeypatch):
    from packages.resume_core import assistant_proposals as persistence
    service, _, projects, workspace, session = environment(tmp_path)
    try:
        snapshot = await read_document(session)
        initial, original = await append(session, "first", snapshot=snapshot)
        stored = service.proposals.get(workspace.project_id, initial["proposalId"], 1)
        path = service.proposals.directory(workspace.project_id) / service.proposals.filename(stored)
        before = path.read_bytes()
        monkeypatch.setattr(persistence, "VERSION_BYTES", len(before))
        assert await session.call("prepare_edit_batch", original) == initial
        denied, _ = await append(session, "new_call", proposal=initial["proposalId"])
        assert denied["error"]["code"] == "AGENT_EDIT_LIMIT"
        retained = service.proposals.get(workspace.project_id, initial["proposalId"], 1)
        unchanged = {"proposal": {"reason"}, "control_padding": True}
        assert retained.model_dump(exclude=unchanged) == stored.model_dump(exclude=unchanged)
        assert path.stat().st_size == len(before) and retained.proposal.reason.startswith("Лимит:")
        monkeypatch.setattr(persistence, "VERSION_BYTES", 2 * 1024 * 1024)
        ready = await complete(session, initial)
        def forge(values):
            value = values[0]; value.proposal.changes[0].after = "Unreviewed replacement"
            return value
        with pytest.raises(AgentFailure, match="AGENT_IDEMPOTENCY_CONFLICT"):
            service.proposals.update(workspace.project_id, forge)
        assert service.proposals.get(workspace.project_id, ready["proposalId"], 1).proposal.state == "ready"
        assert not projects.storage.read_committed(workspace.project_id)[0].mutation_replay
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_proposal_routes_are_authenticated_read_only_and_discard_exact_versions(tmp_path):
    from tests.recovery.test_agent_routes import application, enabled
    from tests.support.agent import run_request
    async with application(tmp_path, None) as (client, _, service, workspace, conversation, prefix, runtime, _):
        await enabled(client); service.assistant_protocol_enabled = True
        owner = service.leases.open(workspace.project_id, "history_1").owner
        run, _ = service.submit(workspace.project_id, run_request(conversation.id, owner=owner.model_dump(by_alias=True), settingsRevision=2, allowEdits=False))
        control = RunControl(workspace.project_id, run.id, run.owner_epoch, run.connection_epoch, time.monotonic())
        session = ToolSession(service, control, run, Fetcher())
        before = service.projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
        headers = {"X-FoldCV-Assistant-Protocol": "1"}
        try:
            snapshot = await read_document(session)
            initial, _ = await append(session, "first", snapshot=snapshot)
            ready = await complete(session, initial)
            assert (await client.get(prefix + "/proposals")).status_code == 409
            listed = await client.get(prefix + "/proposals", headers=headers)
            assert listed.status_code == 200 and listed.json()["proposals"][0]["state"] == "ready"
            route = prefix + f"/proposals/{ready['proposalId']}/versions/1"
            assert (await client.get(route, headers=headers)).json()["contentSha256"] == ready["contentSha256"]
            request = {"protocolVersion": 1, "proposalId": ready["proposalId"], "version": 1, "contentSha256": ready["contentSha256"]}
            assert (await client.post(prefix + "/proposals/discard", json={**request, "approved": True}, headers=headers)).status_code == 422
            assert (await client.post(prefix + "/proposals/discard", json={**request, "contentSha256": "f" * 64}, headers=headers)).status_code == 409
            discarded = await client.post(prefix + "/proposals/discard", json=request, headers=headers)
            assert discarded.status_code == 200 and discarded.json()["state"] == "discarded"
            client.cookies.clear()
            assert (await client.get(route, headers={**headers, "Authorization": "Bearer " + session.token})).status_code == 401
            assert service.projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before
            assert not runtime.calls
        finally:
            await session.close()


@pytest.mark.asyncio
async def test_selected_draft_uses_frozen_scope_and_partial_whole_draft_cannot_finalize_as_ready(tmp_path):
    service, _, projects, workspace, session = environment(tmp_path / "selected", selected=True)
    try:
        snapshot = await read_document(session)
        initial, _ = await append(session, "first", snapshot=snapshot)
        ready = await complete(session, initial)
        assert ready["disposition"] == "draft_ready"
        value = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        ids = {unit.unit_id for unit in value.proposal.coverage}
        assert {"block:narrative", "field:narrative:content", "scope:selection"} <= ids
        assert not any(key.startswith("block:") and key != "block:narrative" for key in ids)
        assert not projects.storage.read_committed(workspace.project_id)[0].mutation_replay
    finally:
        await session.close()
    service, _, projects, workspace, session = environment(tmp_path / "whole")
    try:
        await session.call("get_project_resources", AssistantTaskRequestV1(protocolVersion=1, taskId="rewrite_resume"))
        read = await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"]))
        partial, _ = await append(session, "first", snapshot=AgentReadSnapshot.model_validate(read["snapshot"]), phase="finalize")
        assert partial["disposition"] == "building" and partial["unresolvedUnits"] > 0
        value = service.proposals.get(workspace.project_id, partial["proposalId"], 1)
        assert value.candidate is not None and value.proposal.changes
        service.proposals.finish(workspace.project_id, session.run.id)
        assert service.proposals.get(workspace.project_id, partial["proposalId"], 1).proposal.state == "incomplete"
        denied, _ = await append(session, "late", proposal=partial["proposalId"])
        assert denied["error"]["code"] == "AGENT_EDIT_LIMIT"
        assert not projects.storage.read_committed(workspace.project_id)[0].mutation_replay
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_finalize_keeps_every_fully_read_untouched_unit_without_declarations(tmp_path):
    from resume_api.agent.proposals import KEPT
    service, runtime, projects, workspace, session = environment(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
    try:
        snapshot = await read_document(session)
        ready, _ = await append(session, "only", snapshot=snapshot, phase="finalize")
        assert ready["disposition"] == "draft_ready" and ready["unresolvedUnits"] == 0 and ready["changedUnits"] >= 1
        stored = service.proposals.list(workspace.project_id)[0].proposal
        kept = [unit for unit in stored.coverage if unit.state == "unchanged"]
        assert kept and all(unit.read and unit.reason == KEPT for unit in kept)
        assert projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before and not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_finalize_never_keeps_unread_units_and_keeps_explicit_reasons(tmp_path):
    service, _, _, workspace, session = environment(tmp_path)
    try:
        task = await session.call("get_project_resources", AssistantTaskRequestV1(protocolVersion=1, taskId="rewrite_resume"))
        assert task["availability"]["state"] == "available"
        query = AgentQuery(kind="document")
        page = await session.call("get_resume_context", query)
        snapshot = AgentReadSnapshot.model_validate(page["snapshot"])
        while page["snapshot"]["nextCursor"]:
            page = await session.call("get_resume_context", query.model_copy(update={"cursor": page["snapshot"]["nextCursor"]}))
        started, _ = await append(session, "start", snapshot=snapshot)
        block = next(unit["unitId"] for unit in started["coverage"] if unit["unitId"].startswith("block:") and unit["read"])
        reason = "Оставить авторскую формулировку."
        partial, _ = await append(session, "end", proposal=started["proposalId"], phase="finalize",
            unchanged=[{"unitId": block, "reason": reason}])
        # Unread scope keeps the draft open and names the reads still needed in the same turn.
        assert partial["disposition"] == "building" and partial["unresolvedUnits"] > 0
        assert "get_working_facts" in partial["reason"] and "kind=context" in partial["reason"]
        service.proposals.finish(workspace.project_id, session.run.id)
        stored = service.proposals.list(workspace.project_id)[0].proposal
        assert stored.state == "incomplete"
        assert all(not unit.read for unit in stored.coverage if unit.state == "unresolved")
        assert next(unit for unit in stored.coverage if unit.unit_id == block).reason == reason
    finally:
        await session.close()
