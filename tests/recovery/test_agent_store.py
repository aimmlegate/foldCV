"""Assistant persistence protects retries, readable limits and canonical project data."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import stat

import pytest
from pydantic import ValidationError

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.agent_store import AgentFailure, AgentStore, digest, run_in
from packages.resume_core.models.agent import (
    AgentEditBatch, AgentEditReceipt, AgentFinding, AgentMessage, AgentPageRequest,
    AgentPrepareRequest, AgentPrepareResult, AgentSettingsRequest, AgentWebSource, wire_bytes,
)
from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.rich_mutations import mutation_sha256
from packages.resume_core.storage import atomic_write
from tests.support.agent import NOW, OWNER_TOKEN, isolated_project, run_request


def submit(store, workspace, conversation, key="send_1", **changes):
    return store.submit(workspace.project_id, run_request(conversation.id, clientRequestId=key, **changes),
        model="assistant-model", connection_epoch="account_1")


def prepared(run, workspace, key="prepare_1"):
    from packages.resume_core.models.rich_mutations import RichMutation
    block = workspace.project.document.regions[0].blocks[0].model_copy(deep=True)
    block.content[0].text = "Updated synthetic text"
    mutation = RichMutation.model_validate({"schemaVersion": 1, "projectId": workspace.project_id,
        "clientMutationId": "mutation_1", "actionId": "action_1", "kind": "structure",
        "capture": {"sessionId": "session_1", "actionId": "action_1", "actionToken": 0, "dependencies": []},
        "steps": [{"kind": "put_block", "parentId": "header", "afterId": None,
            "beforeRevision": 1, "block": block.model_dump(by_alias=True)}]})
    return AgentEditBatch(id="batch_1", runId=run.id, toolKey=key, ownerEpoch=run.owner_epoch,
        state="prepared", scope=run.scope, readSnapshotIds=[], dependencies=[], mutation=mutation,
        requestSha256=mutation_sha256(mutation), previewSha256="b" * 64, affected=[], factRecordIds=[])


def prepare_request(key="prepare_1"):
    return AgentPrepareRequest.model_validate({"key": key, "snapshotIds": [], "operations": [{
        "kind": "replace_text", "target": {"snapshotId": "read_1", "blockId": "profile", "cellId": None,
            "field": "content", "start": 0, "end": 1}, "content": [{"text": "Updated", "marks": []}]}]})


def test_settings_choices_are_independent_revisioned_and_retained_without_catalog(tmp_path):
    processing = PreferencesStore(tmp_path)
    processing.select_model("processing-model")
    original = processing.path.read_bytes()
    settings = AgentSettingsStore(tmp_path)
    assert settings.load().selected_agent_model is None and not settings.load().enabled
    assert not settings.path.exists()
    request = AgentSettingsRequest(expectedRevision=1, enabled=True, selectedAgentModel="assistant-model")
    saved = settings.save(request, ("assistant-model", "processing-model"))
    assert saved.revision == 2 and saved.selected_agent_model == "assistant-model"
    assert processing.path.read_bytes() == original
    assert AgentSettingsStore(tmp_path).load() == saved
    with pytest.raises(AgentFailure, match="AGENT_SETTINGS_CONFLICT"):
        settings.save(request, None)
    assert settings.save(AgentSettingsRequest(expectedRevision=2, enabled=False,
        selectedAgentModel="assistant-model"), None).selected_agent_model == "assistant-model"
    processing.select_model("other-processing")
    assert settings.load().selected_agent_model == "assistant-model"
    with pytest.raises(AgentFailure, match="AGENT_MODEL_UNAVAILABLE"):
        settings.save(AgentSettingsRequest(expectedRevision=3, enabled=True, selectedAgentModel="removed"), ())
    with pytest.raises(AgentFailure, match="AGENT_CONNECTION_UNAVAILABLE"):
        settings.save(AgentSettingsRequest(expectedRevision=3, enabled=True, selectedAgentModel="new"), None)
    assert settings.load().revision == 3


def test_concurrent_settings_writes_conflict_and_damage_does_not_reset(tmp_path):
    def save(model):
        try:
            return AgentSettingsStore(tmp_path).save(AgentSettingsRequest(expectedRevision=1,
                enabled=True, selectedAgentModel=model), ("a", "b")).selected_agent_model
        except AgentFailure as error:
            return error.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, ["a", "b"]))
    assert results.count("AGENT_SETTINGS_CONFLICT") == 1
    store = AgentSettingsStore(tmp_path)
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    raw = b'{"schemaVersion":1,"schemaVersion":1}'
    atomic_write(store.path, raw)
    with pytest.raises(AgentFailure, match="AGENT_SETTINGS_CORRUPT"):
        store.load()
    assert store.path.read_bytes() == raw


def test_submission_retry_keeps_original_text_model_and_permissions_after_restart(tmp_path):
    store, _, workspace, conversation = isolated_project(tmp_path)
    message = "Проверь Python.\nKeep my original wording 😀"
    run, created = submit(store, workspace, conversation, message=message)
    assert created and run.model == "assistant-model"
    assert OWNER_TOKEN not in (store.projects / workspace.project_id / "state.json").read_text()
    store.recover(workspace.project_id)
    def no_new_admission():
        raise AssertionError("an identical retry cannot recheck changed settings or start inference")
    restored, created = AgentStore(tmp_path).submit(workspace.project_id, run_request(conversation.id,
        message=message), model="changed-model", connection_epoch="account_2", validate_new=no_new_admission)
    assert not created and restored.id == run.id and restored.state == "interrupted"
    assert restored.model == "assistant-model" and restored.connection_epoch == "account_1"
    with pytest.raises(AgentFailure, match="AGENT_IDEMPOTENCY_CONFLICT"):
        submit(store, workspace, conversation, message=message + " changed")
    state = store.load(workspace.project_id)
    assert [msg.text for msg in state.conversations[0].messages] == [message, ""]
    assert state.owner_epoch == 1


def test_terminal_success_requires_native_completion_and_late_events_cannot_relabel_it(tmp_path):
    store, _, workspace, conversation = isolated_project(tmp_path)
    run, _ = submit(store, workspace, conversation)
    with pytest.raises(AgentFailure, match="AGENT_PROTOCOL"):
        store.finish(workspace.project_id, run.id, "completed", text="a final delta alone")
    with pytest.raises(AgentFailure, match="AGENT_OUTPUT_LIMIT"):
        store.finish(workspace.project_id, run.id, "completed", text="😀" * 16385, native_completed=True)
    assert run_in(store.load(workspace.project_id), run.id)[1].state == "queued"
    completed = store.finish(workspace.project_id, run.id, "completed", text="Verified result", native_completed=True)
    assert store.finish(workspace.project_id, run.id, "failed", error="AGENT_PROTOCOL") == completed
    store.recover(workspace.project_id)
    state = store.load(workspace.project_id)
    assert state.conversations[0].runs[0].state == "completed"
    assert [msg.text for msg in state.conversations[0].messages] == ["Check the Python evidence.", "Verified result"]


def test_preparation_keys_no_change_and_saved_plus_cancelled_are_durable(tmp_path):
    store, _, workspace, conversation = isolated_project(tmp_path)
    run, _ = submit(store, workspace, conversation)
    no_op = AgentPrepareRequest(key="noop", snapshotIds=[], operations=[])
    no_change = AgentPrepareResult(disposition="no_change", batchId=None, affected=[], preview="")
    assert store.prepare(workspace.project_id, run.id, no_op, lambda *_: (no_change, None)) == no_change
    def must_not_compile(*_):
        raise AssertionError("duplicate tool invocation")
    assert store.prepare(workspace.project_id, run.id, no_op, must_not_compile) == no_change
    changed = AgentPrepareRequest(key="noop", snapshotIds=["different"], operations=[])
    with pytest.raises(AgentFailure, match="AGENT_IDEMPOTENCY_CONFLICT"):
        store.prepare(workspace.project_id, run.id, changed, must_not_compile)
    request = prepare_request()
    batch = prepared(run, workspace)
    from packages.resume_core.rich_mutations import apply_rich_mutation
    candidate, _ = apply_rich_mutation(workspace, batch.mutation)
    assert candidate.mutation_replay[-1].request_sha256 == batch.request_sha256
    result = AgentPrepareResult(disposition="prepared", batchId=batch.id, affected=[], preview="Changed text")
    store.prepare(workspace.project_id, run.id, request, lambda *_: (result, batch))
    receipt = AgentEditReceipt(batchId=batch.id, runId=run.id, toolKey=batch.tool_key,
        clientMutationId=batch.mutation.client_mutation_id, requestSha256=batch.request_sha256,
        disposition="saved", projectRevision=2, documentRevision=2, factsRevision=1, durable=True, error=None)
    assert store.record_receipt(workspace.project_id, run.id, receipt) == receipt
    assert store.record_receipt(workspace.project_id, run.id, receipt) == receipt
    with pytest.raises(AgentFailure, match="AGENT_EDIT_LIMIT"):
        store.prepare(workspace.project_id, run.id, prepare_request("second_edit"), must_not_compile)
    terminal = store.finish(workspace.project_id, run.id, "cancelled", error="AGENT_CANCELLED")
    assert terminal.saved_batch_id == batch.id and terminal.state == "cancelled"
    with pytest.raises(AgentFailure, match="AGENT_TOOL_DENIED"):
        store.prepare(workspace.project_id, run.id, prepare_request("second_edit"), must_not_compile)
    store.recover(workspace.project_id)
    _, restored, journal = run_in(store.load(workspace.project_id), run.id)
    assert restored.saved_batch_id == batch.id and journal.batches[-1].receipt == receipt
    assert store.prepare(workspace.project_id, run.id, request, must_not_compile) == result


def test_retired_batch_keeps_receipt_identity_and_terminal_cancels_unapplied_offer(tmp_path):
    store, _, workspace, conversation = isolated_project(tmp_path)
    run, _ = submit(store, workspace, conversation)
    batch = prepared(run, workspace)
    request = prepare_request()
    result = AgentPrepareResult(disposition="prepared", batchId=batch.id, affected=[], preview="")
    store.prepare(workspace.project_id, run.id, request, lambda *_: (result, batch))
    stale = AgentEditReceipt(batchId=batch.id, runId=run.id, toolKey=batch.tool_key,
        clientMutationId=batch.mutation.client_mutation_id, requestSha256=batch.request_sha256,
        disposition="stale", projectRevision=None, documentRevision=None, factsRevision=None,
        durable=False, error={"code": "AGENT_STALE_READ"})
    store.record_receipt(workspace.project_id, run.id, stale)
    no_op = AgentPrepareRequest(key="noop_after_stale", snapshotIds=[], operations=[])
    store.prepare(workspace.project_id, run.id, no_op, lambda *_: pytest.fail("no-op cannot compile"))
    assert store.load(workspace.project_id).journals[0].batches[0].batch is None
    assert store.record_receipt(workspace.project_id, run.id, stale) == stale
    second = prepared(run, workspace, "prepare_2")
    second.id = "batch_2"
    result = AgentPrepareResult(disposition="prepared", batchId=second.id, affected=[], preview="")
    store.prepare(workspace.project_id, run.id, prepare_request("prepare_2"), lambda *_: (result, second))
    store.finish(workspace.project_id, run.id, "cancelled", error="AGENT_CANCELLED")
    _, terminal, journal = run_in(store.load(workspace.project_id), run.id)
    assert terminal.saved_batch_id is None and not journal.reserved
    assert journal.batches[-1].batch.state == journal.batches[-1].receipt.disposition == "cancelled"


def test_restart_preserves_applying_as_unknown_until_exact_receipt_reconciles(tmp_path):
    store, _, workspace, conversation = isolated_project(tmp_path)
    run, _ = submit(store, workspace, conversation)
    batch = prepared(run, workspace)
    batch.state = "applying"
    request = prepare_request(batch.tool_key)
    result = AgentPrepareResult(disposition="prepared", batchId=batch.id, affected=[], preview="")
    store.prepare(workspace.project_id, run.id, request, lambda *_: (result, batch))
    assert store.recover(workspace.project_id) == [batch.id]
    _, interrupted, journal = run_in(store.load(workspace.project_id), run.id)
    assert interrupted.state == "interrupted" and interrupted.outcome_unknown and journal.reserved
    receipt = AgentEditReceipt(batchId=batch.id, runId=run.id, toolKey=batch.tool_key,
        clientMutationId=batch.mutation.client_mutation_id, requestSha256=batch.request_sha256,
        disposition="saved", projectRevision=2, documentRevision=2, factsRevision=1, durable=True, error=None)
    store.record_receipt(workspace.project_id, run.id, receipt)
    _, recovered, journal = run_in(store.load(workspace.project_id), run.id)
    assert recovered.state == "interrupted" and not recovered.outcome_unknown
    assert recovered.saved_batch_id == batch.id and not journal.reserved


def test_capacity_reserves_before_admission_and_serializes_competing_submissions(tmp_path):
    store, _, workspace, conversation = isolated_project(tmp_path)
    for i in range(2):
        current = conversation if i == 0 else store.create_conversation(workspace.project_id)
        submit(store, workspace, current, f"initial_{i}")
    targets = [store.create_conversation(workspace.project_id) for _ in range(2)]
    def attempt(index):
        try:
            return submit(AgentStore(tmp_path), workspace, targets[index], f"concurrent_{index}")[0].id
        except AgentFailure as error:
            return error.code
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(attempt, [0, 1]))
    assert outcomes.count("AGENT_PROJECT_FULL") == 1
    state = store.load(workspace.project_id)
    assert len(state.journals) == sum(len(conv.messages) for conv in state.conversations) == 3
    assert len(wire_bytes(state)) < limits.PROJECT_BYTES
    for conv in state.conversations:
        for run in conv.runs:
            store.finish(workspace.project_id, run.id, "interrupted", error="AGENT_INTERRUPTED")
    assert submit(store, workspace, conversation, "after_cleanup")[1]


def test_last_conversation_slots_are_reserved_and_new_dialog_retains_history(tmp_path):
    store, _, workspace, conversation = isolated_project(tmp_path)
    run, _ = submit(store, workspace, conversation)
    store.finish(workspace.project_id, run.id, "completed", native_completed=True, text="Checked")
    def fill(state):
        conv, old, journal = run_in(state, run.id)
        original_messages = list(conv.messages)
        for i in range(1, 99):
            clone = old.model_copy(update={"id": f"old_run_{i}", "client_request_id": f"old_send_{i}"})
            copied = journal.model_copy(deep=True)
            copied.run_id = clone.id
            copied.request.client_request_id = clone.client_request_id
            copied.request_sha256 = digest(copied.request)
            conv.runs.append(clone)
            state.journals.append(copied)
            conv.messages.extend(msg.model_copy(update={"id": f"old_message_{i}_{j}", "run_id": clone.id})
                for j, msg in enumerate(original_messages))
    store.update(workspace.project_id, fill)
    last, _ = submit(store, workspace, conversation, "last_send")
    with pytest.raises(AgentFailure, match="AGENT_BUSY"):
        submit(store, workspace, conversation, "one_over")
    store.finish(workspace.project_id, last.id, "cancelled", error="AGENT_CANCELLED")
    with pytest.raises(AgentFailure, match="AGENT_CONVERSATION_FULL"):
        submit(store, workspace, conversation, "one_over")
    assert len(store.load(workspace.project_id).conversations[0].messages) == 200
    fresh = store.create_conversation(workspace.project_id)
    assert submit(store, workspace, fresh, "new_dialog")[1]
    assert len(store.load(workspace.project_id).conversations[0].messages) == 200


def test_failed_atomic_sidecar_write_does_not_acknowledge_or_mutate_history(tmp_path, monkeypatch):
    store, _, workspace, conversation = isolated_project(tmp_path)
    path = store.projects / workspace.project_id / "state.json"
    original = path.read_bytes()
    def denied(*_):
        raise OSError("synthetic write failure")
    monkeypatch.setattr("packages.resume_core.agent_store.atomic_write", denied)
    with pytest.raises(AgentFailure, match="AGENT_STORE_SAVE_FAILED"):
        submit(store, workspace, conversation)
    assert path.read_bytes() == original and store.load(workspace.project_id).journals == []


def test_ambiguous_sidecar_reply_preserves_idempotency_after_atomic_replace(tmp_path, monkeypatch):
    store, _, workspace, conversation = isolated_project(tmp_path)
    def lost_reply(path, raw):
        atomic_write(path, raw)
        raise OSError("synthetic lost reply after replace")
    monkeypatch.setattr("packages.resume_core.agent_store.atomic_write", lost_reply)
    with pytest.raises(AgentFailure, match="AGENT_STORE_SAVE_FAILED"):
        submit(store, workspace, conversation)
    state = store.load(workspace.project_id)
    assert len(state.journals) == 1
    run, created = submit(store, workspace, conversation)
    assert not created and run.id == state.journals[0].run_id


def test_corruption_and_symlinks_preserve_bytes_without_touching_canonical_resume(tmp_path):
    store, canonical, workspace, _ = isolated_project(tmp_path)
    workspace_path = canonical.projects / workspace.project_id / "workspace.json"
    before = workspace_path.read_bytes()
    path = store.projects / workspace.project_id / "state.json"
    damaged = b'{"schemaVersion":1,"schemaVersion":2}'
    atomic_write(path, damaged)
    with pytest.raises(AgentFailure, match="AGENT_STORE_CORRUPT"):
        store.create_conversation(workspace.project_id)
    assert path.read_bytes() == damaged and workspace_path.read_bytes() == before
    assert canonical.load_all()[1] == {}
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_text("synthetic private bytes")
    path.symlink_to(outside)
    with pytest.raises(AgentFailure, match="AGENT_STORE_CORRUPT"):
        store.load(workspace.project_id)
    assert outside.read_text() == "synthetic private bytes"


def test_tombstone_blocks_late_publication_and_cleanup_recovers_without_model_work(tmp_path, monkeypatch):
    store, canonical, workspace, conversation = isolated_project(tmp_path)
    submit(store, workspace, conversation)
    canonical.tombstone(workspace.project_id)
    with pytest.raises(AgentFailure, match="AGENT_PROJECT_DELETED"):
        store.create_conversation(workspace.project_id)
    path = store.projects / workspace.project_id / "state.json"
    original = Path.unlink
    def denied(target, *args, **kwargs):
        if target == path:
            raise OSError("synthetic denied cleanup")
        return original(target, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", denied)
        assert store.recover_all()[1] == {workspace.project_id: "AGENT_CLEANUP_INCOMPLETE"}
    assert path.exists()
    assert canonical.registry().entries[0].tombstoned
    assert store.recover_all() == ({}, {})
    assert not path.parent.exists()
    with pytest.raises(AgentFailure, match="AGENT_PROJECT_DELETED"):
        submit(store, workspace, conversation, "late")
    assert not path.parent.exists()


def test_portable_resume_omits_local_conversation_and_import_uses_fresh_namespace(tmp_path):
    from packages.resume_core.gui_archive_zip import read_zip
    from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
    store, canonical, workspace, conversation = isolated_project(tmp_path)
    run, _ = submit(store, workspace, conversation, message="Keep this local conversation")
    store.finish(workspace.project_id, run.id, "completed", text="Stored locally", native_completed=True)
    archive = export_rich_archive(workspace, {}, {}, {})
    entries = read_zip(archive)
    assert all("assistant" not in name and "conversation" not in name for name in entries)
    assert all(b"Keep this local conversation" not in data for data in entries.values())
    imported, originals, artifacts, images = open_rich_archive(archive, "project_imported")
    canonical.save(imported, {(imported.project_id, key): data for key, data in originals.items()}, artifacts, images)
    assert store.load(imported.project_id).conversations == []
    assert store.load(workspace.project_id).conversations[0].id == conversation.id


def maximum_escaped(model, data, field, limit):
    value = model.model_validate({**data, field: "x"})
    available = limit - (len(wire_bytes(value)) - 1)
    return model.model_validate({**data, field: "\x00" * (available // 6) + "x" * (available % 6)})


def test_maximum_serialized_records_remain_readable_with_lazy_escaped_pages(tmp_path):
    store, _, workspace, conversation = isolated_project(tmp_path)
    run, _ = submit(store, workspace, conversation)
    message = maximum_escaped(AgentMessage, {"id": "m" * 32, "role": "assistant", "text": "",
        "runId": run.id, "timestamp": NOW, "sources": [], "findings": [], "truncated": False,
        "error": None}, "text", limits.MESSAGE_BYTES)
    source = maximum_escaped(AgentWebSource, {"id": "source_0", "runId": run.id,
        "requestedUrl": "https://example.invalid/vacancy", "finalUrl": "https://example.invalid/vacancy",
        "title": "Synthetic vacancy", "retrievedAt": NOW, "contentSha256": "a" * 64,
        "text": "", "truncated": True, "originalBytes": 100000}, "text", limits.SOURCE_BYTES)
    finding = maximum_escaped(AgentFinding, {"id": "finding_0", "runId": run.id, "severity": "warning",
        "message": "x", "anchors": [], "sourceIds": []}, "message", limits.FINDING_BYTES)
    for value, field, limit in [(message, "text", limits.MESSAGE_BYTES), (source, "text", limits.SOURCE_BYTES),
                                 (finding, "message", limits.FINDING_BYTES)]:
        assert len(wire_bytes(value)) == limit
        with pytest.raises(ValidationError):
            type(value).model_validate({**value.model_dump(by_alias=True), field: getattr(value, field) + "x"})
    def publish(state):
        conv, _, _ = run_in(state, run.id)
        conv.sources.extend(source.model_copy(update={"id": f"source_{i}"}) for i in range(4))
        conv.findings.append(finding)
    store.update(workspace.project_id, publish)
    store.finish(workspace.project_id, run.id, "completed", native_completed=True, text=message.text)
    second, _ = submit(store, workspace, conversation, "send_2")
    store.finish(workspace.project_id, second.id, "completed", native_completed=True, text=message.text)
    sources = store.page(workspace.project_id, conversation.id, "sources", AgentPageRequest())
    assert len(sources.sources) == 3 and len(wire_bytes(sources)) <= limits.RESPONSE_BYTES
    remaining = store.page(workspace.project_id, conversation.id, "sources", AgentPageRequest(cursor=sources.next_cursor))
    assert len(remaining.sources) == 1 and remaining.next_cursor is None
    first_page = store.page(workspace.project_id, conversation.id, "messages", AgentPageRequest())
    assert len(first_page.items) == 3 and first_page.next_cursor is not None
    assert len(wire_bytes(first_page)) <= limits.RESPONSE_BYTES
    last = store.page(workspace.project_id, conversation.id, "messages", AgentPageRequest(cursor=first_page.next_cursor))
    assert len(last.items) == 1 and last.items[0].text == message.text
    assert store.page(workspace.project_id, conversation.id, "findings", AgentPageRequest()).findings == [finding]
    with pytest.raises(AgentFailure, match="AGENT_NOT_FOUND"):
        store.page(workspace.project_id, conversation.id, "findings", AgentPageRequest(cursor=sources.next_cursor))


def test_unicode_user_and_assistant_text_limits_are_independent():
    assert len(run_request("conversation_1", message="😀" * 8000).message) == 8000
    with pytest.raises(ValidationError):
        run_request("conversation_1", message="😀" * 8001)
    data = {"id": "message_1", "role": "assistant", "runId": "run_1", "timestamp": NOW,
        "sources": [], "findings": [], "truncated": False, "error": None}
    assert len(AgentMessage(**data, text="😀" * 16384).text.encode()) == 65536
    with pytest.raises(ValidationError):
        AgentMessage(**data, text="😀" * 16384 + "x")
    with pytest.raises((ValidationError, UnicodeEncodeError)):
        run_request("conversation_1", message="\ud800")
