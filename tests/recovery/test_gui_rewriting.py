"""Scoped Unicode replacements, durable checkpoints and guarded late replies."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import uuid

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/api/src'))

from packages.resume_core.gui_rewriting import GuiRewriteRequest, GuiRewriteProposal, apply_rewrite, rewriting_input
from packages.resume_core.gui_selection import field_index, selection_fingerprint
from packages.resume_core.models.recovery import Selection
from packages.resume_core.rules import captured_rules
from resume_api.gui_projects import ProjectFailure
from resume_api.providers.content import ContentFailure
from tests.recovery.generation_fixtures import CreationProvider, render_workspace, frozen_now
from tests.recovery.test_gui_mutations import edit, restore, mutation, apply, new_record
from tests.recovery.test_gui_projects import service
from tests.recovery.test_project_store import created, service as durable_service
from tests.recovery.draft_fixtures import RULES


def request(workspace, ids=None, rules=None, instruction='Make clearer'):
    rules = rules or workspace.rules_used or RULES
    if workspace.rules_used is None:
        workspace.rules_used = rules
    indexed = field_index(workspace.project.document)
    ids = ids or ['profile/text']
    spans = [{'fieldId': id, 'range': {'start': 0, 'end': len(indexed[id][0].text.encode('utf-16-le')) // 2},
              'capturedText': indexed[id][0].text} for id in ids if indexed[id][0].text]
    return GuiRewriteRequest(clientRequestId='rewrite-' + str(uuid.uuid4()),
        selection=Selection(projectId=workspace.project_id, documentRevision=workspace.document_revision,
            dependencyFingerprint=selection_fingerprint(workspace), spans=spans), instruction=instruction,
        rulesRevision=rules.revision, rulesSha256=rules.sha256)


def proposal(request, text):
    return GuiRewriteProposal(replacements=[{'fieldId': span.field_id, 'text': text} for span in request.selection.spans])


def test_partial_utf16_newline_replacement_preserves_surrounding_text_and_restore():
    workspace = render_workspace()
    edit(workspace, 'profile/text', 'Alpha 😀é\nBeta', completion='slot')
    before = workspace.project_revision, workspace.document_revision
    captured = request(workspace)
    span = captured.selection.spans[0]
    span.range.start, span.range.end, span.captured_text = 6, 11, '😀é\n'
    result = apply_rewrite(workspace, captured, proposal(captured, '🧩\r\n'), before[0], frozen_now().isoformat())
    assert result.changed_slot_ids == ['profile'] and workspace.project.document.profile.text.text == 'Alpha 🧩\nBeta'
    assert (workspace.project_revision, workspace.document_revision) == (before[0] + 1, before[1] + 1)
    restore(workspace, 'profile')
    assert workspace.project.document.profile.text.text == 'Alpha 😀é\nBeta'
    restore(workspace, 'profile')
    assert workspace.project.document.profile.text.text == 'Alpha 😀é\nBeta'


def test_direct_contact_edit_and_scoped_rewrite_preserve_other_authored_fields():
    from packages.resume_core.models.recovery import AuthoredField
    workspace = render_workspace()
    detail = AuthoredField(fieldId='private/email/0', text='old@example.invalid',
                          factIds=[], evidence=[], origin='user')
    workspace.project.document.candidate.details.append(detail)
    profile = workspace.project.document.profile.text.text
    edit(workspace, detail.field_id, 'new@example.invalid', completion='slot')
    captured = request(workspace, [detail.field_id], instruction='Use phone: +12345678901')
    assert 'new@example.invalid' in rewriting_input(workspace, captured, workspace.rules_used)
    result = apply_rewrite(workspace, captured, proposal(captured, 'phone: +12345678901'),
                           workspace.project_revision, frozen_now().isoformat())
    assert result.status == 'applied'
    assert workspace.project.document.candidate.details[0].text == 'phone: +12345678901'
    assert workspace.project.document.profile.text.text == profile


@pytest.mark.parametrize('suffix', ['candidate/title', '/role', '/startText'])
def test_authored_heading_structured_and_invalid_date_rewrite_keep_field_identity(suffix):
    workspace = render_workspace()
    indexed = field_index(workspace.project.document)
    id = next(key for key in indexed if key.endswith(suffix))
    captured = request(workspace, [id])
    result = apply_rewrite(workspace, captured, proposal(captured, 'User typed replacement'), workspace.project_revision, frozen_now().isoformat())
    assert result.status == 'applied' and field_index(workspace.project.document)[id][0].text == 'User typed replacement'
    if id.endswith('/startText'):
        value = next(value for value in workspace.derived_state.values if value.field_id == id)
        assert not value.valid and value.display is None


def test_cross_section_rewrite_checkpoints_each_affected_block_without_membership_change():
    workspace = render_workspace()
    indexed = field_index(workspace.project.document)
    ids = list(indexed)
    end = next(index for index, id in enumerate(ids) if id.endswith('/tasks'))
    selected = ids[3:end + 1]
    captured = request(workspace, selected)
    old = {id: indexed[id][0].text for id in selected}
    slots = list(dict.fromkeys(indexed[span.field_id][1] for span in captured.selection.spans))
    membership = [record.id for record in workspace.project.document.records()]
    result = apply_rewrite(workspace, captured, proposal(captured, 'Changed span'), workspace.project_revision, frozen_now().isoformat())
    assert result.changed_slot_ids == slots and [record.id for record in workspace.project.document.records()] == membership
    assert all(workspace.undo_slots[slot] is not None for slot in slots)
    for slot in slots:
        restore(workspace, slot)
    assert {id: field_index(workspace.project.document)[id][0].text for id in selected} == old


def test_rewrite_input_limits_context_to_current_authoritative_fields_and_public_references():
    workspace = render_workspace()
    edit(workspace, 'profile/text', 'Added instruction for duty shift.\nRemoved the old test detail.', completion='slot')
    captured = request(workspace)
    payload = json.loads(rewriting_input(workspace, captured, workspace.rules_used))
    assert payload['input']['facts'] == [] and payload['input']['excerpts'] == []
    assert [item['fieldId'] for item in payload['input']['selection']] == ['profile/text']
    assert payload['input']['selection'][0]['currentFieldText'] == workspace.project.document.profile.text.text
    assert 'sources' not in payload['input'] and 'jobs' not in payload['input']
    assert payload['rulesUsed']['sha256'] == workspace.rules_used.sha256
    bad_rules = captured_rules(workspace.rules_used.markdown + '\nChanged policy.', workspace.rules_used.revision + 1)
    with pytest.raises(ValueError, match='RULES_CHANGED'):
        rewriting_input(workspace, captured, bad_rules)


def test_mismatched_scope_surrogate_split_and_stale_counter_leave_text_unchanged():
    workspace = render_workspace()
    edit(workspace, 'profile/text', '😀 unchanged', completion='slot')
    captured = request(workspace)
    original = workspace.model_dump()
    wrong = proposal(captured, 'new');wrong.replacements[0].field_id = 'candidate/name'
    with pytest.raises(ValueError, match='REWRITE_SCOPE_INVALID'):
        apply_rewrite(workspace, captured, wrong, workspace.project_revision, frozen_now().isoformat())
    split = captured.model_copy(deep=True);split.selection.spans[0].range.start = 1
    assert apply_rewrite(workspace, split, proposal(split, 'x'), workspace.project_revision, '').status == 'stale'
    assert apply_rewrite(workspace, captured, proposal(captured, 'x'), workspace.project_revision - 1, '').status == 'stale'
    assert workspace.model_dump() == original


def test_user_added_row_and_empty_model_replacement_preserve_authoritative_structure():
    workspace = render_workspace()
    record = new_record(workspace, 'education', 'added')
    apply(workspace, 'add', {'sectionId': 'education', 'record': record.model_dump(by_alias=True), 'afterRecordId': None})
    edit(workspace, record.institution.field_id, 'User university', completion='slot')
    captured = request(workspace, [record.institution.field_id])
    apply_rewrite(workspace, captured, proposal(captured, ''), workspace.project_revision, frozen_now().isoformat())
    assert any(row.id == record.id for row in workspace.project.document.education)
    restore(workspace, 'education:' + record.id)
    assert field_index(workspace.project.document)[record.institution.field_id][0].text == 'User university'


class DelayedProvider(CreationProvider):
    def __init__(self):
        super().__init__();self.started, self.release = threading.Event(), threading.Event()
    def generate(self, request, files, cancel):
        if request.result_type is GuiRewriteProposal:
            self.started.set()
            self.release.wait(5)
        return super().generate(request, files, cancel)


async def wait_started(provider):
    async def waiting():
        while not provider.started.is_set():
            await asyncio.sleep(.01)
    await asyncio.wait_for(waiting(), 5)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['edit', 'rename', 'cancel'])
async def test_late_rewrite_rejects_new_text_metadata_or_cancellation_and_cleans_owned_files(tmp_path, change):
    provider = DelayedProvider();store = service(tmp_path, provider);workspace = render_workspace()
    store.workspaces[workspace.project_id] = workspace
    captured = request(workspace, rules=store.rules.load())
    task = asyncio.create_task(store.rewrite(workspace.project_id, captured));await wait_started(provider)
    if change == 'edit':
        store.mutate(workspace.project_id, mutation(workspace, 'edit-field', {'fieldId':'profile/text','text':'Newer typed text',
            'periods':None,'focus':None,'sessionId':'typing','completion':'none'}))
    elif change == 'rename':
        from packages.resume_core.gui_projects import GuiRenameProjectRequest
        store.rename(workspace.project_id, GuiRenameProjectRequest(title='Renamed', baseRevision=workspace.project_revision))
    else:
        store.cancels[(workspace.project_id, captured.client_request_id)].set()
    before = workspace.project.document.model_dump()
    provider.release.set();result = await task
    assert result.status in {'stale', 'rejected'} and workspace.project.document.model_dump() == before
    assert len(provider.calls) == 1 and [op for op in workspace.project.operations if op.kind == "rewrite_prose"][-1].usage.logical_attempts == 1
    assert list((tmp_path / 'operations').iterdir()) == []


@pytest.mark.asyncio
async def test_durable_rewrite_is_one_operation_replays_after_restart_and_preserves_checkpoint(tmp_path):
    store, id = await created(tmp_path);workspace = store.read(id)
    captured = request(workspace, rules=store.rules.load())
    result = await store.rewrite(id, captured)
    assert result.status == 'applied' and result.persistence == 'durable'
    assert store.read(id).undo_slots['profile'].record.text.text == workspace.project.document.profile.text.text
    assert len([op for op in store.read(id).project.operations if op.kind != "reconcile_edits"]) == 3
    replay = await store.rewrite(id, captured)
    assert replay.status == 'replayed' and len([op for op in store.read(id).project.operations if op.kind != "reconcile_edits"]) == 3
    provider = CreationProvider();reopened = durable_service(tmp_path, provider)
    assert (await reopened.rewrite(id, captured)).status == 'replayed' and provider.calls == []
    changed = captured.model_copy(update={'instruction':'Different payload'})
    with pytest.raises(ProjectFailure, match='REQUEST_ID_REUSED'):
        await reopened.rewrite(id, changed)
    assert all('replacement' not in item.model_dump_json().lower() for item in reopened.read(id).mutation_replay)


@pytest.mark.asyncio
async def test_rewrite_failure_preserves_document_counts_once_and_has_no_automatic_retry(tmp_path):
    provider = CreationProvider();store = service(tmp_path, provider);workspace = render_workspace();store.workspaces[workspace.project_id] = workspace
    captured = request(workspace, rules=store.rules.load(), instruction='TEST_ERROR');before = workspace.project.document.model_dump()
    result = await store.rewrite(workspace.project_id, captured)
    assert result.rejection_reason == 'MODEL_DENIED' and workspace.project.document.model_dump() == before
    assert len(provider.calls) == 1 and [op for op in workspace.project.operations if op.kind == "rewrite_prose"][-1].usage.logical_attempts == 1
    await asyncio.sleep(.02)
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_more_than_twenty_explicit_rewrites_do_not_use_the_legacy_lifetime_cap(tmp_path):
    provider = CreationProvider();store = service(tmp_path, provider);workspace = render_workspace();store.workspaces[workspace.project_id] = workspace
    for _ in range(21):
        result = await store.rewrite(workspace.project_id, request(workspace, rules=store.rules.load()))
        assert result.status == 'applied'
    assert len(provider.calls) == len([op for op in workspace.project.operations if op.kind == "rewrite_prose"]) == 21
    assert all(operation.usage.logical_attempts == 1 for operation in workspace.project.operations if operation.kind == "rewrite_prose")
    assert workspace.generations == [] and (workspace.project_revision, workspace.document_revision) == (23, 23)


class ForeignReplyProvider(CreationProvider):
    def generate(self, request, files, cancel):
        response = super().generate(request, files, cancel)
        proposal = response.value.model_copy(deep=True);proposal.replacements[0].field_id = 'candidate/name'
        return replace(response, value=proposal)


@pytest.mark.asyncio
async def test_foreign_model_span_fails_once_without_replacement_or_unsafe_error_text(tmp_path, capsys):
    provider = ForeignReplyProvider();store = service(tmp_path, provider);workspace = render_workspace();store.workspaces[workspace.project_id] = workspace
    original = workspace.project.document.model_dump()
    result = await store.rewrite(workspace.project_id, request(workspace, rules=store.rules.load()))
    assert result.status == 'rejected' and result.rejection_reason == 'INVALID_RESULT'
    assert workspace.project.document.model_dump() == original and len(provider.calls) == 1
    assert [op for op in workspace.project.operations if op.kind == "rewrite_prose"][-1].usage.logical_attempts == 1
    assert capsys.readouterr() == ('', '')


@pytest.mark.asyncio
async def test_invalid_capture_and_instruction_are_zero_call_preflight_failures(tmp_path):
    provider = CreationProvider();store = service(tmp_path, provider);workspace = render_workspace();store.workspaces[workspace.project_id] = workspace
    captured = request(workspace, rules=store.rules.load());captured.selection.spans[0].captured_text = 'mismatched'
    result = await store.rewrite(workspace.project_id, captured)
    assert result.rejection_reason == 'SELECTION_STALE' and [op for op in workspace.project.operations if op.kind == "rewrite_prose"][-1].usage.logical_attempts == 0
    assert provider.calls == []
    with pytest.raises(ValidationError):
        request(workspace, rules=store.rules.load(), instruction='\ud800')
    malformed = request(workspace, rules=store.rules.load()).model_copy(update={'instruction':'\ud800'})
    with pytest.raises(ProjectFailure, match='INVALID_CONTENT_INPUT'):
        await store.rewrite(workspace.project_id, malformed)
    assert provider.calls == []


def test_unchanged_replacement_finishes_session_without_counter_or_extra_pointer_movement():
    workspace = render_workspace();edit(workspace, 'profile/text', 'Current user text', session='typing')
    captured = request(workspace);before = workspace.project_revision, workspace.document_revision
    result = apply_rewrite(workspace, captured, proposal(captured, 'Current user text'), before[0], frozen_now().isoformat())
    assert result.status == 'applied' and result.changed_slot_ids == [] and 'profile' not in workspace.edit_sessions
    assert (workspace.project_revision, workspace.document_revision) == before
    assert workspace.undo_slots['profile'].record.text.text != 'Current user text'
