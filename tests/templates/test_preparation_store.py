"""Prepared retries and saves use exact opening authority and shared bounds."""

from dataclasses import replace
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from packages.resume_core import background_store
from packages.resume_core.background_store import BackgroundFailure, RetainedUsage
from packages.resume_core.models.template_writer import WriterMutationV2, WriterPrepareEditV2
from packages.resume_core.project_store import encoded
from packages.resume_core.template_preparation import prepare_text_edit
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_template_preparation import command, response
from tests.templates.test_template_writers import TemplateWriterFixture


def setup(root):
    value, sources = workspace()
    return TemplateWriterFixture(root, workspace=value, sources=sources)


def request(fixture, **kwargs):
    preparation = command(fixture.current(), **kwargs)
    preparation.capture.session_id = fixture.proof.session_id
    return WriterPrepareEditV2(schemaVersion=2, proof=fixture.proof, preparation=preparation)


def save_request(fixture, prepared, cursor=1):
    return WriterMutationV2(**fixture.advance_request(cursor, [{'cursor': cursor, 'mutation': prepared.mutation}]).model_dump(by_alias=True),
        mutation=prepared.mutation, preparation={'requestHash': prepared.request_hash})


def other_edit(fixture):
    value = fixture.current()
    intent = request(fixture)
    intent.preparation.client_mutation_id = 'other-edit'
    intent.preparation.capture.action_id = 'other-action'
    intent.preparation.operations[0].range.block_id = 'block-paper-b'
    prepared = prepare_text_edit(response(value), intent.preparation)
    raw = save_request(fixture, prepared)
    raw.preparation = None
    return fixture.writers.save(fixture.project, raw, originals=fixture.originals)


def assert_committed_preview(prepared, committed):
    assert prepared.preview.snapshot == response(committed).snapshot
    assert prepared.preview.workspace.model_dump(exclude={'updated_at'}) == committed.model_dump(exclude={'updated_at'})


def test_same_request_replays_exact_bytes_with_only_canonical_package_reference(tmp_path):
    fixture = setup(tmp_path)
    intent = request(fixture)
    before = canonical(fixture.current())
    prepared = fixture.writers.prepare_edit(fixture.project, intent)
    repeated = fixture.writers.prepare_edit(fixture.project, intent)
    assert canonical(prepared) == canonical(repeated) and canonical(fixture.current()) == before
    opening = fixture.writers.preparations.openings[fixture.project]
    assert set(opening.backing) == {'projectId', 'packageHash', 'fullPackageFingerprint'}
    compact = json.loads(opening.entries[prepared.client_mutation_id].payload)
    assert 'templatePackage' not in compact['preview']['workspace']['project']
    assert len(canonical(opening.backing)) < 512
    assert fixture.writers.preparations.usage()[fixture.project].draft_bytes < len(canonical(prepared))


def test_retry_reconstructs_original_preview_after_newer_canonical_state_without_repreparing(tmp_path, monkeypatch):
    fixture = setup(tmp_path)
    intent = request(fixture)
    prepared = fixture.writers.prepare_edit(fixture.project, intent)
    other_edit(fixture)
    def forbidden(*_args, **_kwargs):
        pytest.fail('retained preparation must not run again')
    monkeypatch.setattr('packages.resume_core.template_writer_preparation.prepare_edit', forbidden)
    assert canonical(fixture.writers.prepare_edit(fixture.project, intent)) == canonical(prepared)
    assert fixture.current().project_revision > prepared.base_snapshot.project_revision


@pytest.mark.parametrize('change', ['request', 'proof'])
def test_changed_request_or_owner_cannot_reuse_prepared_authority(tmp_path, change):
    fixture = setup(tmp_path)
    intent = request(fixture)
    fixture.writers.prepare_edit(fixture.project, intent)
    if change == 'request':
        intent.preparation.operations[0].text = 'Changed'
    else:
        intent.proof.credential = 'wrong' * 8
    with pytest.raises(BackgroundFailure, match='JOB_IDEMPOTENCY_CONFLICT' if change == 'request' else 'WRITER_UNKNOWN'):
        fixture.writers.prepare_edit(fixture.project, intent)


@pytest.mark.parametrize('change', ['omitted', 'hash', 'mutation'])
def test_registered_id_cannot_bypass_preparation_reference_or_exact_mutation(tmp_path, change):
    fixture = setup(tmp_path)
    prepared = fixture.writers.prepare_edit(fixture.project, request(fixture))
    save = save_request(fixture, prepared)
    before = canonical(fixture.current())
    if change == 'omitted':
        save.preparation = None
    elif change == 'hash':
        save.preparation.request_hash = '0' * 64
    else:
        step = save.mutation.steps[0]
        (step.block.content if step.kind == 'put_block' else step.content)[0].text = 'Forged'
    with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID' if change == 'omitted' else 'JOB_IDEMPOTENCY_CONFLICT'):
        fixture.writers.save(fixture.project, save, originals=fixture.originals)
    assert canonical(fixture.current()) == before


def test_prepared_save_never_rebases_onto_a_new_canonical_snapshot(tmp_path):
    fixture = setup(tmp_path)
    prepared = fixture.writers.prepare_edit(fixture.project, request(fixture))
    other_edit(fixture)
    before = canonical(fixture.current())
    with pytest.raises(BackgroundFailure, match='DEPENDENCY_CHANGED'):
        fixture.writers.save(fixture.project, save_request(fixture, prepared, 2), originals=fixture.originals)
    assert canonical(fixture.current()) == before


def test_commit_matches_preview_and_terminal_guard_replays_only_the_saved_mutation(tmp_path):
    fixture = setup(tmp_path)
    intent = request(fixture)
    prepared = fixture.writers.prepare_edit(fixture.project, intent)
    save = save_request(fixture, prepared)
    saved = fixture.writers.save(fixture.project, save, originals=fixture.originals)
    assert_committed_preview(prepared, saved.workspace)
    assert saved.local_history_ack is not None
    entry = fixture.writers.preparations.openings[fixture.project].entries[prepared.client_mutation_id]
    assert entry.payload is None and fixture.writers.preparations.usage()[fixture.project].draft_bytes == 0
    repeated = fixture.writers.save(fixture.project, save, originals=fixture.originals)
    assert repeated.replayed and repeated.workspace == saved.workspace
    with pytest.raises(BackgroundFailure, match='REQUEST_EXPIRED'):
        fixture.writers.prepare_edit(fixture.project, intent)
    save.preparation = None
    with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
        fixture.writers.save(fixture.project, save, originals=fixture.originals)


def test_durable_receipt_recovers_an_interrupted_memo_finalization(tmp_path, monkeypatch):
    fixture = setup(tmp_path)
    prepared = fixture.writers.prepare_edit(fixture.project, request(fixture))
    save = save_request(fixture, prepared)
    original = fixture.writers.preparations.committed
    def interrupt(*_args):
        raise RuntimeError('lost final reply')
    monkeypatch.setattr(fixture.writers.preparations, 'committed', interrupt)
    with pytest.raises(RuntimeError, match='lost final reply'):
        fixture.writers.save(fixture.project, save, originals=fixture.originals)
    assert_committed_preview(prepared, fixture.current())
    monkeypatch.setattr(fixture.writers.preparations, 'committed', original)
    assert fixture.writers.save(fixture.project, save, originals=fixture.originals).replayed
    assert len(fixture.current().mutation_replay) == 1


def test_noop_has_no_save_or_inverse_and_keeps_exact_response(tmp_path):
    fixture = setup(tmp_path)
    prepared = fixture.writers.prepare_edit(fixture.project, request(fixture, text='Shared'))
    assert prepared.mutation is None and not fixture.current().mutation_replay
    assert not fixture.writers.local_history.openings and not fixture.jobs.load(fixture.project).manual_intents
    assert prepared.preview.workspace == fixture.current()


@pytest.mark.parametrize('change', ['metadata', 'missing_project'])
def test_old_preview_cannot_reconstruct_from_missing_or_changed_package(tmp_path, change):
    fixture = setup(tmp_path)
    intent = request(fixture)
    fixture.writers.prepare_edit(fixture.project, intent)
    with fixture.writers.guard(fixture.project) as (_directory, state, current, _checksum):
        entry = fixture.writers.preparations.find(state, intent.preparation)
        if change == 'metadata':
            current.project.template_package.assets[0].mime_type += ';changed'
        else:
            current.project = None
        with pytest.raises(BackgroundFailure, match='REQUEST_EXPIRED|JOB_SCOPE_INVALID'):
            fixture.writers.preparations.read(state, current, entry)


@pytest.mark.parametrize('limit', ['draft_project_bytes', 'draft_global_bytes', 'sidecar_project_bytes', 'sidecar_global_bytes',
    'metadata_project_records', 'metadata_global_records'])
def test_shared_limits_reject_admission_without_replacing_prior_entries(tmp_path, monkeypatch, limit):
    fixture = setup(tmp_path)
    intent = request(fixture)
    first = fixture.writers.prepare_edit(fixture.project, intent)
    old = fixture.writers.preparations.openings[fixture.project]
    intent.preparation.client_mutation_id = 'second-preparation'
    state = fixture.jobs.load(fixture.project)
    usage = fixture.writers.preparations.usage()[fixture.project]
    if limit.startswith('draft_'):
        bound = usage.draft_bytes
    elif limit.startswith('metadata_'):
        bound = background_store.records(state) + usage.records
    else:
        bound = (len(encoded(state.model_dump(mode='json', by_alias=True))) + fixture.jobs._reserved_bytes(state)
            + fixture.jobs._extra_bytes(fixture.project) + fixture.jobs._fixed_bytes(state) + usage.owned_bytes)
    monkeypatch.setattr(background_store, 'LIMITS', replace(background_store.LIMITS, **{limit: bound}))
    with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
        fixture.writers.prepare_edit(fixture.project, intent)
    assert fixture.writers.preparations.openings[fixture.project] is old
    assert list(old.entries) == [first.client_mutation_id]


def test_ordinary_job_write_includes_retained_memo_usage_and_other_projects(tmp_path, monkeypatch):
    fixture = setup(tmp_path)
    fixture.writers.prepare_edit(fixture.project, request(fixture))
    used = fixture.writers.preparations.usage()[fixture.project].draft_bytes
    fixture.jobs.usage_providers['other_owner'] = lambda **_kwargs: {'other-project': RetainedUsage(draft_bytes=123, owned_bytes=456, records=1)}
    monkeypatch.setattr(background_store, 'LIMITS', replace(background_store.LIMITS, draft_global_bytes=used + 122))
    with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
        fixture.writers.heartbeat(fixture.project, fixture.proof)


def test_clean_detach_releases_all_memo_state(tmp_path):
    fixture = setup(tmp_path)
    fixture.writers.prepare_edit(fixture.project, request(fixture))
    fixture.writers.detach(fixture.project, fixture.advance_request())
    assert fixture.project not in fixture.writers.preparations.openings
    assert fixture.writers.preparations.usage() == {}


def test_durable_project_tombstone_releases_payloads_and_package_backing(tmp_path):
    fixture = setup(tmp_path)
    intent = request(fixture)
    fixture.writers.prepare_edit(fixture.project, intent)
    fixture.jobs.canonical.tombstone(fixture.project)
    fixture.jobs.mark_deleted(fixture.project)
    assert fixture.writers.preparations.usage() == {}
    with pytest.raises(BackgroundFailure, match='PROJECT_DELETED'):
        fixture.writers.prepare_edit(fixture.project, intent)


def test_opening_replacement_releases_old_authority_after_durable_transition(tmp_path):
    from packages.resume_core.models.background import WriterAbandonV1
    from packages.resume_core.background_history import digest_bytes
    fixture = setup(tmp_path)
    old = request(fixture)
    fixture.writers.prepare_edit(fixture.project, old)
    current = fixture.current()
    fixture.writers.abandon(fixture.project, WriterAbandonV1(schemaVersion=1, sessionId='new-session',
        incarnation='new-opening', credential='new-synthetic-credential-0123456789',
        canonicalRevision=current.project_revision, canonicalSha256=digest_bytes(current)))
    assert fixture.writers.preparations.usage() == {}
    with pytest.raises(BackgroundFailure, match='WRITER_UNKNOWN'):
        fixture.writers.prepare_edit(fixture.project, old)


def test_failed_detach_keeps_the_uncommitted_preparation_and_capacity_usage(tmp_path, monkeypatch):
    fixture = setup(tmp_path)
    prepared = fixture.writers.prepare_edit(fixture.project, request(fixture))
    original = fixture.jobs._confirm
    def unavailable(*_args):
        raise BackgroundFailure('JOB_STORE_UNAVAILABLE')
    monkeypatch.setattr('packages.resume_core.background_store.atomic_write', lambda *_args: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(fixture.jobs, '_confirm', unavailable)
    with pytest.raises(BackgroundFailure, match='JOB_STORE_UNAVAILABLE'):
        fixture.writers.detach(fixture.project, fixture.advance_request())
    monkeypatch.setattr(fixture.jobs, '_confirm', original)
    opening = fixture.writers.preparations.openings[fixture.project]
    assert opening.entries[prepared.client_mutation_id].payload is not None
    assert fixture.writers.preparations.usage()[fixture.project].draft_bytes > 0


def test_read_reconciles_a_durable_detach_after_its_confirmation_was_unavailable(tmp_path, monkeypatch):
    fixture = setup(tmp_path)
    fixture.writers.prepare_edit(fixture.project, request(fixture))
    original_write = background_store.atomic_write
    def lost_reply(path, raw):
        original_write(path, raw)
        raise OSError('lost write reply')
    def unavailable(*_args):
        raise BackgroundFailure('OUTCOME_UNKNOWN')
    monkeypatch.setattr(background_store, 'atomic_write', lost_reply)
    monkeypatch.setattr(fixture.jobs, '_confirm', unavailable)
    with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
        fixture.writers.detach(fixture.project, fixture.advance_request())
    assert fixture.project in fixture.writers.preparations.openings
    assert fixture.jobs.load(fixture.project).writer.status == 'clean_detached'
    assert fixture.writers.preparations.usage() == {}


def test_recreated_writer_owner_keeps_one_shared_accounted_registry(tmp_path):
    from packages.resume_core.background_writers import WriterSessions
    fixture = setup(tmp_path)
    fixture.writers.prepare_edit(fixture.project, request(fixture))
    replacement = WriterSessions(fixture.publisher)
    assert replacement.preparations is fixture.writers.preparations
    assert sum(getattr(provider, '__self__', None) is replacement.preparations
        for provider in fixture.jobs.usage_providers.values()) == 1
    assert sum(getattr(observer, '__self__', None) is replacement.preparations
        for observer in fixture.jobs.state_observers.values()) == 1


@pytest.mark.parametrize('prefix', ['background_', 'agent_', 'inverse_', 'history_'])
def test_preparation_cannot_register_an_id_owned_by_another_canonical_command(tmp_path, prefix):
    fixture = setup(tmp_path)
    intent = request(fixture)
    intent.preparation.client_mutation_id = prefix + 'reserved'
    with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
        fixture.writers.prepare_edit(fixture.project, intent)
    assert not fixture.writers.preparations.openings


@pytest.mark.parametrize('path', ['history', 'draft'])
def test_other_writer_commands_cannot_reuse_a_registered_preparation_id(tmp_path, path):
    from packages.resume_core.models.template_writer import WriterDraftResolveV2
    from tests.templates.test_template_local_history import history_request
    fixture = setup(tmp_path)
    other = other_edit(fixture)
    prepared = fixture.writers.prepare_edit(fixture.project, request(fixture))
    before = canonical(fixture.current())
    if path == 'history':
        intent = history_request(fixture, other.local_history_ack)
        intent.client_mutation_id = prepared.client_mutation_id
        function = fixture.writers.local_history_command
    else:
        intent = WriterDraftResolveV2(schemaVersion=2, proof=fixture.proof, id='unknown-draft', sequence=1,
            payloadSha256='0' * 64, canonicalRevision=fixture.current().project_revision,
            canonicalSha256=fixture.advance_request().canonical_sha256, mutation=prepared.mutation)
        function = fixture.writers.use_draft
    with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
        function(fixture.project, intent, originals=fixture.originals)
    assert canonical(fixture.current()) == before


def test_new_preparation_rejects_an_id_retained_by_a_reconciled_canonical_intent(tmp_path, monkeypatch):
    fixture = setup(tmp_path)
    intent = request(fixture)
    prepared = prepare_text_edit(response(fixture.current()), intent.preparation)
    raw = save_request(fixture, prepared)
    raw.preparation = None
    before = canonical(fixture.current())
    def interrupt(name, _project):
        if name == 'before_workspace_replaced':
            raise SystemExit('controlled cut')
    fixture.publisher.observer = interrupt
    with pytest.raises(SystemExit, match='controlled cut'):
        fixture.writers.save(fixture.project, raw, originals=fixture.originals)
    fixture.publisher.observer = lambda *_args: None
    fixture.publisher.recover(fixture.project)
    assert canonical(fixture.current()) == before
    assert [(item.client_mutation_id, item.phase) for item in fixture.jobs.load(fixture.project).manual_intents] == [('text-edit', 'reconciled')]
    intent.preparation.operations[0].text = 'Another edit'
    def forbidden(*_args):
        pytest.fail('canonical-occupied ID must reject before preparation or capacity admission')
    monkeypatch.setattr('packages.resume_core.template_writer_preparation.prepare_edit', forbidden)
    with pytest.raises(BackgroundFailure, match='REQUEST_EXPIRED'):
        fixture.writers.prepare_edit(fixture.project, intent)
    assert not fixture.writers.preparations.openings


@pytest.mark.asyncio
async def test_real_writer_prepare_route_retains_preview_without_canonical_adoption(tmp_path):
    import threading
    from resume_api.jobs.writers import mount_writers
    fixture = setup(tmp_path)
    service = SimpleNamespace(enabled=True, writers=fixture.writers, projects=SimpleNamespace(state_lock=threading.RLock()))
    app = FastAPI()
    @app.exception_handler(BackgroundFailure)
    async def failure(_request, error):
        return JSONResponse({'error': {'code': error.code}}, status_code=409)
    mount_writers(app, service)
    before = canonical(fixture.current())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://foldcv.test') as client:
        result = await client.post('/v1/rich/projects/' + fixture.project + '/writer/prepare',
            json=request(fixture).model_dump(mode='json', by_alias=True))
    assert result.status_code == 200 and result.json()['mutation'] is not None
    assert canonical(fixture.current()) == before
