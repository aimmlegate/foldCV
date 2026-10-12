"""Retained authored changes, replay, block sessions and explicit membership."""

import itertools
import asyncio
from io import BytesIO
from zipfile import ZipFile
from pathlib import Path
import sys

import pytest
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/api/src'))

from packages.resume_core.gui_mutations import apply_mutation, checkpoint, document_content
from packages.resume_core.gui_projects import GuiRenameProjectRequest
from packages.resume_core.gui_rendering import render_input
from packages.resume_core.gui_selection import field_index, selection_fingerprint, valid_selection
from packages.resume_core.models.recovery import Mutation, Selection, authored_fields, record_slot
from tests.recovery.generation_fixtures import render_workspace
from tests.recovery.test_gui_projects import service, finish
from tests.recovery.candidate_fixtures import ROOT
from tests.recovery.generation_fixtures import CreationProvider, frozen_now
from resume_api.app import create_app
from resume_api.gui_projects import ProjectFailure
from resume_api.gui_rendering import GuiDocxRenderer
from resume_api.lifecycle import OperationFiles

COUNTER = itertools.count()
STAMP = '2026-10-11T12:00:00+00:00'


def mutation(workspace, kind, payload, *, base=None, id=None):
    return Mutation.model_validate({'projectId': workspace.project_id, 'baseRevision': workspace.document_revision if base is None else base,
        'clientMutationId': id or f'mutation-{next(COUNTER)}', 'kind': kind, 'payload': payload})


def apply(workspace, kind, payload, **kwargs):
    return apply_mutation(workspace, mutation(workspace, kind, payload, **kwargs), STAMP)


def edit(workspace, field_id, text, *, session='session-profile', completion='none', **kwargs):
    return apply(workspace, 'edit-field', {'fieldId': field_id, 'text': text, 'periods': None, 'focus': None,
        'sessionId': session, 'completion': completion}, **kwargs)


def restore(workspace, slot, session=None):
    return apply(workspace, 'restore-previous-block', {'slotId': slot, 'sessionId': session})


def new_record(workspace, section, id):
    record = getattr(workspace.project.document, section)[0].model_copy(deep=True)
    previous = record_slot(record)
    record.id = id
    slot = record_slot(record)
    for field in authored_fields(record):
        field.field_id = slot + field.field_id.removeprefix(previous)
        field.text = ''
    if record.kind == 'job': record.periods_field_id = slot + '/periods'
    return record


def test_incremental_edits_keep_baseline_and_pointer_until_slot_departure():
    workspace = render_workspace()
    baseline = workspace.project.document.profile.text.text
    assert edit(workspace, 'profile/text', baseline + '\r\nAdded 😀').status == 'applied'
    assert workspace.project.document.profile.text.text == baseline + '\nAdded 😀'
    assert workspace.undo_slots['profile'] is None and workspace.edit_sessions['profile'].baseline.record.text.text == baseline
    assert workspace.derived_state is None
    assert edit(workspace, 'profile/text', baseline + '\nAdded 😀 more', completion='paragraph').status == 'applied'
    assert workspace.undo_slots['profile'] is None
    counters = (workspace.project_revision, workspace.document_revision)
    edit(workspace, 'profile/text', workspace.project.document.profile.text.text, completion='field')
    assert (workspace.project_revision, workspace.document_revision) == counters
    assert 'profile' in workspace.edit_sessions
    edit(workspace, 'profile/text', workspace.project.document.profile.text.text, completion='slot')
    assert workspace.undo_slots['profile'].record.text.text == baseline and 'profile' not in workspace.edit_sessions
    assert (workspace.project_revision, workspace.document_revision) == counters


def test_two_step_restore_preserves_then_consumes_pointer_and_blur_cannot_recreate_it():
    workspace = render_workspace()
    original = workspace.project.document.profile.text.text
    edit(workspace, 'profile/text', 'First', completion='slot')
    edit(workspace, 'profile/text', 'Unfinished', session='second')
    restore(workspace, 'profile', 'second')
    assert workspace.project.document.profile.text.text == 'First'
    assert workspace.undo_slots['profile'].record.text.text == original
    assert workspace.edit_sessions['profile'].baseline.record.text.text == 'First'
    restore(workspace, 'profile', 'second')
    assert workspace.project.document.profile.text.text == original and workspace.undo_slots['profile'] is None
    before = (workspace.project_revision, workspace.document_revision)
    restore(workspace, 'profile', 'second')
    edit(workspace, 'profile/text', original, session='second', completion='slot')
    assert workspace.undo_slots['profile'] is None and (workspace.project_revision, workspace.document_revision) == before


def test_restore_one_block_keeps_another_buffer_and_no_global_history():
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    edit(workspace, 'profile/text', 'Changed profile', completion='slot')
    edit(workspace, job.context.field_id, 'Changed job', session='job-session')
    restore(workspace, 'profile')
    assert workspace.project.document.jobs[0].context.text == 'Changed job'
    assert workspace.edit_sessions[record_slot(job)].baseline.record.context.text != 'Changed job'
    assert workspace.undo_slots[record_slot(job)] is None


def test_same_job_fields_share_session_and_mismatched_session_is_rejected():
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    slot = record_slot(job)
    edit(workspace, job.employer.field_id, 'New company', session='job-session')
    edit(workspace, job.tasks.field_id, 'New tasks', session='job-session')
    assert workspace.edit_sessions[slot].baseline.record.employer.text == job.employer.text
    assert workspace.undo_slots[slot] is None
    result = edit(workspace, job.role.field_id, 'Wrong session', session='other')
    assert result.status == 'rejected' and result.rejection_reason == 'SESSION_MISMATCH'
    assert workspace.project.document.jobs[0].role.text != 'Wrong session'
    restore(workspace, slot, 'job-session')
    assert workspace.project.document.jobs[0].employer.text == job.employer.text


def test_exact_replay_different_payload_and_stale_writes_never_overwrite_current_text():
    workspace = render_workspace()
    request = mutation(workspace, 'edit-field', {'fieldId': 'profile/text', 'text': 'First', 'periods': None,
        'focus': None, 'sessionId': 'session-profile', 'completion': 'none'}, id='same-id')
    result = apply_mutation(workspace, request, STAMP)
    edit(workspace, 'profile/text', 'Newer')
    before = (workspace.project_revision, workspace.document_revision)
    replay = apply_mutation(workspace, request, STAMP)
    assert replay.status == 'replayed' and (replay.project_revision, replay.document_revision) == (result.project_revision, result.document_revision)
    different = request.model_copy(deep=True);different.root.payload.text = 'Different'
    assert apply_mutation(workspace, different, STAMP).rejection_reason == 'MUTATION_ID_REUSED'
    stale = edit(workspace, 'profile/text', 'Stale', base=2, id='stale-id')
    assert stale.status == 'stale' and workspace.project.document.profile.text.text == 'Newer'
    stale_request = mutation(workspace, 'edit-field', {'fieldId': 'profile/text', 'text': 'Stale', 'periods': None,
        'focus': None, 'sessionId': 'session-profile', 'completion': 'none'}, base=2, id='stale-id')
    assert apply_mutation(workspace, stale_request, STAMP).status == 'replayed'
    assert (workspace.project_revision, workspace.document_revision) == before
    assert len(workspace.mutation_replay) == 3


def test_period_add_remove_reorder_and_present_revert_with_the_job_slot():
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    original = job.model_copy(deep=True)
    period = job.periods[0].model_copy(deep=True);period.id = 'extra'
    period.start_text.field_id = job.periods_field_id.removesuffix('/periods') + '/period:extra/startText'
    period.end_text.field_id = job.periods_field_id.removesuffix('/periods') + '/period:extra/endText'
    period.start_text.text, period.end_text.text, period.present = '2000', '2001', False
    for periods in ([*job.periods, period], [period, *job.periods], [period]):
        result = apply(workspace, 'edit-field', {'fieldId': job.periods_field_id, 'text': None,
            'periods': [item.model_dump(by_alias=True) for item in periods], 'focus': None, 'sessionId': 'periods', 'completion': 'field'})
        assert result.status == 'applied'
    restore(workspace, record_slot(job), 'periods')
    assert workspace.project.document.jobs[0].periods == original.periods
    assert workspace.undo_slots[record_slot(job)] is None


@pytest.mark.parametrize('section', ['jobs', 'education', 'languages'])
def test_explicit_rows_add_reorder_hide_delete_and_undo_cannot_restore_membership(section):
    workspace = render_workspace()
    record = new_record(workspace, section, 'new')
    result = apply(workspace, 'add', {'sectionId': section, 'record': record.model_dump(by_alias=True), 'afterRecordId': None})
    assert result.status == 'applied' and getattr(workspace.project.document, section)[-1].id == 'new'
    slots = [item.id for item in getattr(workspace.project.document, section)]
    assert apply(workspace, 'reorder', {'sectionId': section, 'orderedIds': slots[::-1]}).status == 'applied'
    assert getattr(workspace.project.document, section)[0].id == 'new'
    slot = record_slot(record)
    apply(workspace, 'hide', {'slotId': slot, 'visible': False})
    assert not getattr(workspace.project.document, section)[0].visible
    assert any(item.record_id == slot and item.reason == 'hidden' for item in workspace.source_exclusions)
    apply(workspace, 'hide', {'slotId': slot, 'visible': True})
    assert not any(item.record_id == slot and item.reason == 'hidden' for item in workspace.source_exclusions)
    apply(workspace, 'delete', {'sectionId': section, 'recordId': 'new'})
    assert all(item.id != 'new' for item in getattr(workspace.project.document, section))
    assert restore(workspace, slot).rejection_reason == 'TARGET_NOT_FOUND'
    assert slot not in workspace.undo_slots and slot not in workspace.edit_sessions
    assert any(item.record_id == slot and item.reason == 'deleted' for item in workspace.source_exclusions)


def test_hide_is_explicit_and_restore_never_changes_visibility():
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    edit(workspace, job.context.field_id, 'Edited', session='job', completion='slot')
    apply(workspace, 'hide', {'slotId': record_slot(job), 'visible': False})
    restore(workspace, record_slot(job))
    assert not workspace.project.document.jobs[0].visible
    assert workspace.project.document.jobs[0].context.text == job.context.text
    assert apply(workspace, 'hide', {'slotId': 'candidate', 'visible': False}).rejection_reason == 'CANDIDATE_REQUIRED'


@pytest.mark.parametrize('section', ['education', 'languages'])
def test_fixed_legacy_text_rows_edit_select_and_restore_without_restructuring(section):
    from packages.resume_core.models.recovery import AuthoredField
    workspace = render_workspace()
    row = getattr(workspace.project.document, section)[0]
    for field in authored_fields(row):field.text = ''
    row.legacy_text = AuthoredField(fieldId=f'{record_slot(row)}/legacyText', text='Unsplit legacy\nContent 😀', origin='migration', factIds=[], evidence=[])
    before = row.legacy_text.text
    captured = Selection(projectId=workspace.project_id, documentRevision=workspace.document_revision,
        dependencyFingerprint=selection_fingerprint(workspace), spans=[{'fieldId': row.legacy_text.field_id, 'range': {'start': 0, 'end': 6}, 'capturedText': 'Unsplit'[:6]}])
    assert valid_selection(workspace, captured)
    edit(workspace, row.legacy_text.field_id, 'Changed legacy', session='legacy', completion='slot')
    restore(workspace, record_slot(row))
    restored = getattr(workspace.project.document, section)[0]
    assert restored.legacy_text.text == before
    assert all(field.text == '' for field in authored_fields(restored) if field is not restored.legacy_text)


def test_restore_removes_only_new_user_facts_owned_by_its_block_and_keeps_source_history():
    workspace = render_workspace()
    sources = [source.model_dump() for source in workspace.project.sources]
    edit(workspace, 'profile/text', 'New user claim', completion='none')
    source = next(fact for fact in workspace.project.facts if fact.kind == 'text')
    added = source.model_copy(deep=True)
    added.id, added.origin, added.job_id, added.evidence, added.literal_evidence = 'user-claim', 'user', None, [], []
    added.value.text = 'New user claim'
    workspace.project.facts.append(added)
    workspace.project.document.profile.text.fact_ids = [added.id]
    restore(workspace, 'profile')
    assert all(fact.id != 'user-claim' for fact in workspace.project.facts)
    assert [source.model_dump() for source in workspace.project.sources] == sources


def test_invalid_membership_field_identity_unicode_and_noop_preserve_state():
    workspace = render_workspace()
    before = document_content(workspace.project.document)
    assert edit(workspace, 'missing', 'x').status == 'rejected'
    assert edit(workspace, 'profile/text', '\ud800', id='invalid-unicode').rejection_reason == 'INVALID_DOCUMENT'
    assert edit(workspace, 'profile/text', '\ud800', id='invalid-unicode').status == 'replayed'
    assert apply(workspace, 'reorder', {'sectionId': 'jobs', 'orderedIds': []}).rejection_reason == 'INVALID_MEMBERSHIP'
    record = new_record(workspace, 'jobs', 'bad');record.context.field_id = 'profile/text'
    assert apply(workspace, 'add', {'sectionId': 'jobs', 'record': record.model_dump(by_alias=True), 'afterRecordId': None}).rejection_reason == 'INVALID_FIELD_IDENTITY'
    assert document_content(workspace.project.document) == before and (workspace.project_revision, workspace.document_revision) == (2, 2)
    edit(workspace, 'profile/text', workspace.project.document.profile.text.text)
    assert workspace.edit_sessions == {} and (workspace.project_revision, workspace.document_revision) == (2, 2)
    assert not any('text' in item.model_dump() for item in workspace.mutation_replay)


def test_shared_fact_restore_keeps_newer_authoritative_other_block_but_not_older_mentions():
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    fact = next(fact for fact in workspace.project.facts if fact.kind == 'technology' and fact.value.canonical_id == 'python')
    baseline = checkpoint(workspace, 'profile')
    edit(workspace, 'profile/text', 'Profile edited', completion='slot')
    edit(workspace, job.context.field_id, 'New authoritative mention', session='job', completion='slot')
    current_job = workspace.project.document.jobs[0]
    current_job.context.fact_ids = [fact.id]
    effective = next(item for item in workspace.project.facts if item.id == fact.id)
    effective.value.display, effective.origin, effective.revision = 'Python newer', 'user', effective.revision + 1
    restore(workspace, 'profile')
    assert next(item for item in workspace.project.facts if item.id == fact.id).value.display == 'Python newer'
    assert any(mark.code == 'restore_shared_fact_conflict' for mark in workspace.annotations)
    assert current_job.context.text == workspace.project.document.jobs[0].context.text
    older = render_workspace()
    edit(older, 'profile/text', 'Changed', completion='slot')
    old_fact = next(item for item in older.project.facts if item.id == fact.id)
    old_fact.value.display, old_fact.origin, old_fact.revision = 'Changed only here', 'user', old_fact.revision + 1
    restore(older, 'profile')
    assert next(item for item in older.project.facts if item.id == fact.id).value.display == 'Python'


def test_job_dates_precede_prose_in_the_same_backend_and_browser_selection_order():
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    ids = list(field_index(workspace.project.document))
    assert ids.index(job.role.field_id) < ids.index(job.periods[0].start_text.field_id) < ids.index(job.context.field_id)
    field = job.periods[0].start_text
    end = job.context
    selected_ids = ids[ids.index(field.field_id):ids.index(end.field_id) + 1]
    fields = field_index(workspace.project.document)
    captured = Selection(projectId=workspace.project_id, documentRevision=workspace.document_revision,
        dependencyFingerprint=selection_fingerprint(workspace), spans=[{'fieldId': id, 'range': {'start': 0, 'end': len(fields[id][0].text.encode('utf-16-le')) // 2}, 'capturedText': fields[id][0].text} for id in selected_ids if fields[id][0].text])
    assert valid_selection(workspace, captured)


@pytest.mark.asyncio
async def test_predraft_generation_edit_facts_rename_status_and_replay_use_both_counters(tmp_path):
    store = service(tmp_path)
    selected = await store.select((ROOT / 'E1.txt').read_bytes(), 'pasted.txt', True)
    assert (selected.project_revision, selected.document_revision) == (1, 1)
    id = selected.project_id
    workspace = await finish(store, id, store.start(id))
    assert (workspace.project_revision, workspace.document_revision) == (2, 2)
    request = mutation(workspace, 'edit-field', {'fieldId': 'profile/text', 'text': 'New authored text', 'periods': None, 'focus': None, 'sessionId': 's', 'completion': 'slot'})
    result = store.mutate(id, request)
    assert (result.project_revision, result.document_revision) == (3, 3)
    current = store.workspaces[id]
    current.project.facts[0].revision += 1;current.project_revision += 1;current.project.revision = current.project_revision
    assert (current.project_revision, current.document_revision) == (4, 3)
    store.rename(id, GuiRenameProjectRequest(title='Named', baseRevision=4))
    assert (current.project_revision, current.document_revision) == (5, 3)
    current.generations[-1].status = 'completed'
    store.read(id);store.mutate(id, request)
    assert (current.project_revision, current.document_revision) == (5, 3)
    fresh = edit(current, 'candidate/title', 'Edited title', session='candidate')
    assert (fresh.project_revision, fresh.document_revision) == (6, 4)
    prepared, _, _ = render_input(current)
    assert prepared.candidate.title == 'Edited title' and prepared.candidate.summary == 'New authored text'


@pytest.mark.asyncio
async def test_render_consumes_authored_additions_removals_and_hidden_rows_with_zero_model_calls(tmp_path):
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    edit(workspace, job.tasks.field_id, 'Подготовила инструкцию для дежурной смены', session='job', completion='slot')
    apply(workspace, 'hide', {'slotId': record_slot(workspace.project.document.jobs[1]), 'visible': False})
    document, anchors, _ = render_input(workspace)
    with OperationFiles(tmp_path / 'operations').open() as files:
        rendered = await GuiDocxRenderer().render(document, anchors, files)
    with ZipFile(BytesIO(rendered)) as archive:
        xml = archive.read('word/document.xml').decode()
    assert 'Подготовила инструкцию для дежурной смены' in xml and 'Интеграционные тесты' not in xml
    assert 'Внутренняя CRM' not in xml and 'mail@example.com' not in xml


@pytest.mark.asyncio
async def test_edit_during_initial_render_rejects_old_artifact_and_retry_cannot_replace_user_text(tmp_path):
    entered, released = asyncio.Event(), asyncio.Event()
    class WaitingRenderer:
        async def render(self, *args):
            entered.set();await released.wait()
            return await GuiDocxRenderer().render(*args)
    provider = CreationProvider()
    store = service(tmp_path, provider, WaitingRenderer())
    selected = await store.select((ROOT / 'E1.txt').read_bytes(), 'pasted.txt', True)
    id, gid = selected.project_id, store.start(selected.project_id)
    await asyncio.wait_for(entered.wait(), 5)
    current = store.read(id)
    store.mutate(id, mutation(current, 'edit-field', {'fieldId': 'profile/text', 'text': 'User during render',
        'periods': None, 'focus': None, 'sessionId': 's', 'completion': 'slot'}))
    released.set()
    result = await finish(store, id, gid)
    assert result.project.document.profile.text.text == 'User during render'
    assert result.generations[-1].stages[-1].error_code == 'STALE_GENERATION'
    assert result.project.renders == [] and store.artifacts == {} and len(provider.calls) == 2
    with pytest.raises(ProjectFailure, match='STALE_GENERATION'):store.start(id, gid)


@pytest.mark.asyncio
async def test_gui_operation_base_is_project_revision_after_predraft_rename(tmp_path):
    store = service(tmp_path)
    selected = await store.select((ROOT / 'E1.txt').read_bytes(), 'pasted.txt', True)
    id = selected.project_id
    store.rename(id, GuiRenameProjectRequest(title='User title', baseRevision=1))
    result = await finish(store, id, store.start(id))
    assert result.title == 'User title' and (result.project_revision, result.document_revision) == (3, 2)
    assert all(op.base_revision == 2 and op.captured_document_revision == 1 for op in result.project.operations)
    assert all(op.base_revision == op.dependencies.project_revision for op in result.project.operations)


@pytest.mark.asyncio
async def test_protected_mutation_api_preserves_stale_replay_and_facts_only_base(tmp_path):
    origin, secret = 'http://127.0.0.1:39329', 'synthetic-mutation-secret-0123456789'
    dist = tmp_path / 'dist';dist.mkdir()
    provider = CreationProvider()
    app = create_app(origin=origin, secret=secret, temp_root=tmp_path / 'operations', dist=dist,
        data_root=tmp_path / 'FoldCV', gui_provider=provider, gui_clock=frozen_now)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin) as client:
        headers = {'Origin': origin}
        await client.post('/v1/session/exchange', headers=headers, json={'secret': secret})
        created = (await client.post('/v1/projects', headers=headers, json={'text': (ROOT / 'E1.txt').read_text()})).json()
        id = created['workspace']['projectId'];store = app.app.state.gui_projects
        current = await finish(store, id, created['generationId'])
        request = mutation(current, 'edit-field', {'fieldId': 'profile/text', 'text': 'API edit', 'periods': None,
            'focus': None, 'sessionId': 's', 'completion': 'slot'})
        body = request.model_dump(by_alias=True)
        assert (await client.post(f'/v1/projects/{id}/mutations', json=body)).status_code == 403
        stored = store.workspaces[id]
        stored.project_revision += 1;stored.project.revision = stored.project_revision;stored.project.facts[0].revision += 1
        result = (await client.post(f'/v1/projects/{id}/mutations', headers=headers, json=body)).json()
        assert result['status'] == 'applied' and (result['projectRevision'], result['documentRevision']) == (4, 3)
        assert (await client.post(f'/v1/projects/{id}/mutations', headers=headers, json=body)).json()['status'] == 'replayed'
        renamed = await client.patch(f'/v1/projects/{id}/metadata', headers=headers, json={'title': 'Named', 'baseRevision': 4})
        assert renamed.json()['workspace']['projectRevision'] == 5 and renamed.json()['workspace']['documentRevision'] == 3
        assert len(provider.calls) == 2 and len(stored.project.operations) == 2
