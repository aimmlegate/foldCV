"""Compact save proofs bind the original commit without replaying a newer view."""

from dataclasses import replace
from types import SimpleNamespace
import asyncio
import json
import threading

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from packages.resume_core.background_history import digest_bytes
from packages.resume_core import background_store
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.canonical_patch import apply_patch
from packages.resume_core.models.template_writer import WriterMutationV2, WriterPreparedSaveAckV2, WriterPreparedSaveRecoveryV2
from packages.resume_core.project_store import encoded
from packages.resume_core.rich_api import RichGenerationState
from packages.resume_core.templates.compiler import canonical, sha256
from tests.templates.test_bounded_history import large_workspace
from tests.templates.test_delta_preparation_store import save_delta
from tests.templates.test_preparation_store import request, setup, save_request
from tests.templates.test_template_writers import TemplateWriterFixture


def compact_command(fixture, prepared, cursor=1):
    if hasattr(prepared, 'mutation_wire'):
        command = save_delta(fixture, prepared)
        if cursor != 1:
            command.action_cursor = cursor
            command.touches[0].cursor = cursor
    else:
        command = save_request(fixture, prepared, cursor)
    command.response_mode = 'prepared_delta'
    return command


def prepare(fixture, *, identifier='text-edit', action='action-edit', form='delta'):
    intent = request(fixture)
    intent.preparation.client_mutation_id = identifier
    intent.preparation.capture.action_id = action
    method = fixture.writers.prepare_edit_delta if form == 'delta' else fixture.writers.prepare_edit
    return method(fixture.project, intent)


@pytest.mark.parametrize('form', ['full', 'delta'])
def test_original_commit_proof_survives_newer_saves_and_full_mode_retry(tmp_path, form):
    fixture = setup(tmp_path)
    before = fixture.current()
    prepared = prepare(fixture, form=form)
    command = compact_command(fixture, prepared)
    first = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert isinstance(first, WriterPreparedSaveAckV2) and not first.replayed and first.current_equals_committed
    assert first.local_history_ack.action_id == command.mutation.action_id
    preview = (apply_patch(before.model_dump(mode='json', by_alias=True), prepared.workspace_patch)
        if form == 'delta' else prepared.preview.workspace.model_dump(mode='json', by_alias=True))
    assert first.prepared_workspace_sha256 == sha256(canonical(preview))
    assert canonical(apply_patch(preview, first.commit_patch)) == canonical(fixture.current())
    original_proof = first.model_dump(exclude={'writer', 'replayed', 'current_canonical_revision',
        'current_canonical_sha256', 'current_equals_committed'})
    second = prepare(fixture, identifier='next-edit', action='next-action')
    fixture.writers.save(fixture.project, compact_command(fixture, second, 2), originals=fixture.originals)
    replayed = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert replayed.replayed and not replayed.current_equals_committed
    assert replayed.writer.acknowledged_cursor == 2 and replayed.current_canonical_revision == fixture.current().project_revision
    assert replayed.model_dump(exclude={'writer', 'replayed', 'current_canonical_revision',
        'current_canonical_sha256', 'current_equals_committed'}) == original_proof
    command.response_mode = 'full'
    assert fixture.writers.save(fixture.project, command, originals=fixture.originals).workspace == fixture.current()
    command.response_mode = 'prepared_delta'
    assert fixture.writers.save(fixture.project, command, originals=fixture.originals).committed_workspace_sha256 == first.committed_workspace_sha256


def test_full_save_first_retains_proof_for_a_later_compact_retry(tmp_path):
    fixture = setup(tmp_path); prepared = prepare(fixture)
    command = save_delta(fixture, prepared)
    assert 'responseMode' not in command.model_dump(by_alias=True)
    full = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    command.response_mode = 'prepared_delta'
    compact = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert compact.replayed and compact.committed_workspace_sha256 == full.workspace_sha256
    assert compact.local_history_ack == full.local_history_ack
    value = command.model_dump(by_alias=True); value.pop('preparation')
    with pytest.raises(ValueError):
        WriterMutationV2.model_validate(value)


def test_commit_metadata_and_history_generation_are_original_after_coalescing(tmp_path, monkeypatch):
    fixture = setup(tmp_path)
    original_view = fixture.writers.view
    def view(state, workspace, checksum):
        result = original_view(state, workspace, checksum)
        generation = RichGenerationState(id='generation-' + str(workspace.project_revision),
            status='completed', stage='render', errorCode=None)
        result.response.generation = generation
        return result
    monkeypatch.setattr(fixture.writers, 'view', view)
    first_prepared = prepare(fixture, action='same-action')
    command = compact_command(fixture, first_prepared)
    first = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert first.committed_generation != first_prepared.result_generation
    second_prepared = prepare(fixture, identifier='coalesced-edit', action='same-action')
    second = fixture.writers.save(fixture.project, compact_command(fixture, second_prepared, 2), originals=fixture.originals)
    assert second.local_history_ack.generation > first.local_history_ack.generation
    repeated = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert repeated.local_history_ack == first.local_history_ack
    assert repeated.committed_generation == first.committed_generation != second.committed_generation


def test_large_transaction_transports_only_actual_edit_and_commit_stamp(tmp_path):
    value, sources = large_workspace(); fixture = TemplateWriterFixture(tmp_path, value, sources)
    assert len(canonical(fixture.current())) > 2 * 1024 * 1024
    intent = request(fixture, start=2, end=2, text='!', target={'kind': 'literal'})
    prepared = fixture.writers.prepare_edit_delta(fixture.project, intent)
    command = compact_command(fixture, prepared)
    saved = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert len(canonical(prepared)) < 6000 and len(canonical(command)) < 6000 and len(canonical(saved)) < 6000
    assert [step.pointer for step in saved.commit_patch] == ['/updatedAt']
    entry = fixture.writers.preparations.openings[fixture.project].entries[prepared.client_mutation_id]
    assert entry.payload is None and len(entry.commit_proof) < 4000 and entry.committed
    assert fixture.writers.preparations.usage()[fixture.project].draft_bytes == 0


def test_expired_large_proof_returns_only_preparation_bound_recovery(tmp_path):
    fixture = setup(tmp_path); prepared = prepare(fixture); command = compact_command(fixture, prepared)
    first = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    registry = fixture.writers.preparations; opening = registry.openings[fixture.project]
    old_usage = registry.usage()[fixture.project]
    entry = opening.entries[prepared.client_mutation_id]
    opening.entries[prepared.client_mutation_id] = replace(entry, proof_expires_at='2000-01-01T00:00:00Z')
    recovered = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert isinstance(recovered, WriterPreparedSaveRecoveryV2) and recovered.replay == first.replay
    assert recovered.preparation_request_hash == prepared.request_hash
    assert not {'commitPatch', 'committedSnapshot', 'localHistoryAck', 'committedIdentity', 'committedGeneration'} & recovered.model_dump(by_alias=True).keys()
    assert registry.usage()[fixture.project].owned_bytes < old_usage.owned_bytes
    assert registry.usage()[fixture.project].records == old_usage.records - 1
    opening.entries.pop(prepared.client_mutation_id)
    with pytest.raises(BackgroundFailure, match='REQUEST_EXPIRED'):
        fixture.writers.save(fixture.project, command, originals=fixture.originals)


@pytest.mark.parametrize('phase', ['before_workspace_replaced', 'before_local_history_receipt'])
def test_interrupted_compact_save_keeps_exact_pending_proof(tmp_path, phase):
    fixture = setup(tmp_path); prepared = prepare(fixture); command = compact_command(fixture, prepared)
    target = fixture.publisher if phase == 'before_workspace_replaced' else fixture.writers
    def interrupt(name, _project):
        if name == phase:
            raise SystemExit('controlled compact interruption')
    target.observer = interrupt
    with pytest.raises(SystemExit, match='controlled compact'):
        fixture.writers.save(fixture.project, command, originals=fixture.originals)
    opening = fixture.writers.preparations.openings[fixture.project]
    entry = opening.entries[prepared.client_mutation_id]
    assert entry.commit_proof is not None and not entry.committed
    target.observer = lambda *_args: None
    if phase == 'before_workspace_replaced':
        fixture.publisher.recover(fixture.project)
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN|SAVE_FAILED|DEPENDENCY_CHANGED'):
            fixture.writers.save(fixture.project, command, originals=fixture.originals)
    else:
        saved = fixture.writers.save(fixture.project, command, originals=fixture.originals)
        assert saved.replayed and saved.model_dump(mode='json', by_alias=True)['commitPatch'] == json.loads(entry.commit_proof)['commitPatch']
        assert saved.local_history_ack.generation == 1


def test_definitive_commit_proof_capacity_failure_preserves_preparation_and_releases_pending(tmp_path, monkeypatch):
    fixture = setup(tmp_path); prepared = prepare(fixture); command = compact_command(fixture, prepared)
    registry = fixture.writers.preparations; old = registry.openings[fixture.project].entries[prepared.client_mutation_id]
    original = fixture.jobs._capacity
    def capacity(state, *args, retained_usage=None, **kwargs):
        proposed = (retained_usage or {}).get(registry.usage_key)
        if proposed is not None and proposed[fixture.project].records > registry.usage()[fixture.project].records:
            raise BackgroundFailure('JOB_STORAGE_FULL')
        return original(state, *args, retained_usage=retained_usage, **kwargs)
    with monkeypatch.context() as failed:
        failed.setattr(fixture.jobs, '_capacity', capacity)
        with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
            fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert registry.openings[fixture.project].entries[prepared.client_mutation_id] == old
    assert not fixture.writers.local_history.openings and not fixture.jobs.load(fixture.project).manual_intents
    assert not fixture.current().mutation_replay
    assert fixture.writers.save(fixture.project, command, originals=fixture.originals).kind == 'committed'


@pytest.mark.parametrize('limit', ['sidecar_project_bytes', 'sidecar_global_bytes', 'metadata_project_records', 'metadata_global_records'])
def test_real_shared_limit_reserves_proof_before_any_durable_intent(tmp_path, monkeypatch, limit):
    fixture = setup(tmp_path); prepared = prepare(fixture); command = compact_command(fixture, prepared)
    registry = fixture.writers.preparations; original = registry.prepare_commit
    before = canonical(fixture.current())
    def limited(owner, state, *args):
        usage = [provider(states={fixture.project: state}).get(fixture.project, background_store.RetainedUsage())
            for provider in fixture.jobs.usage_providers.values()]
        if limit.startswith('metadata'):
            bound = background_store.records(state) + sum(value.records for value in usage)
        else:
            bound = (len(encoded(state.model_dump(mode='json', by_alias=True))) + fixture.jobs._reserved_bytes(state)
                + fixture.jobs._extra_bytes(fixture.project) + fixture.jobs._fixed_bytes(state)
                + sum(value.owned_bytes for value in usage))
        with monkeypatch.context() as capped:
            capped.setattr(background_store, 'LIMITS', replace(background_store.LIMITS, **{limit: bound}))
            return original(owner, state, *args)
    with monkeypatch.context() as capped:
        capped.setattr(registry, 'prepare_commit', limited)
        with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
            fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert canonical(fixture.current()) == before and not fixture.jobs.load(fixture.project).manual_intents
    assert registry.openings[fixture.project].entries[prepared.client_mutation_id].commit_proof is None
    assert not fixture.writers.local_history.openings


def test_unknown_intent_write_keeps_proof_reservation(tmp_path, monkeypatch):
    fixture = setup(tmp_path); prepared = prepare(fixture); command = compact_command(fixture, prepared)
    original = fixture.publisher._store_intent
    def store(*args):
        original(*args)
        raise BackgroundFailure('OUTCOME_UNKNOWN')
    with monkeypatch.context() as interrupted:
        interrupted.setattr(fixture.publisher, '_store_intent', store)
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            fixture.writers.save(fixture.project, command, originals=fixture.originals)
    entry = fixture.writers.preparations.openings[fixture.project].entries[prepared.client_mutation_id]
    assert entry.commit_proof is not None and not entry.committed and entry.payload is not None
    assert fixture.jobs.load(fixture.project).manual_intents and fixture.writers.local_history.openings[fixture.project].pending


@pytest.mark.parametrize('change', ['snapshot', 'replay', 'binding', 'current'])
def test_compact_ack_rejects_mislabelled_commit_or_current_state(tmp_path, change):
    fixture = setup(tmp_path); prepared = prepare(fixture)
    result = fixture.writers.save(fixture.project, compact_command(fixture, prepared), originals=fixture.originals)
    value = result.model_dump(mode='json', by_alias=True)
    if change == 'snapshot': value['committedSnapshot']['projectRevision'] += 1
    elif change == 'replay': value['replay']['requestSha256'] = '0' * 64
    elif change == 'binding': value['commitBinding']['incarnation'] = 'another-opening'
    else: value['currentEqualsCommitted'] = False
    with pytest.raises(ValueError): WriterPreparedSaveAckV2.model_validate(value)


@pytest.mark.asyncio
async def test_compact_save_route_adopts_current_server_workspace_without_sending_it(tmp_path):
    from resume_api.jobs.writers import mount_writers
    value, sources = large_workspace(); fixture = TemplateWriterFixture(tmp_path, value, sources)
    intent = request(fixture, start=2, end=2, text='!', target={'kind': 'literal'})
    adopted = []
    service = SimpleNamespace(enabled=True, writers=fixture.writers,
        projects=SimpleNamespace(originals=fixture.originals, artifacts={}, images={}, state_lock=threading.RLock()),
        publication=SimpleNamespace(adopt=lambda *args: adopted.append(args)))
    app = FastAPI(); mount_writers(app, service)
    @app.exception_handler(BackgroundFailure)
    async def failure(_request, error): return JSONResponse({'error': {'code': error.code}}, status_code=409)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://controlled.test') as client:
        from packages.resume_core.models.template_delta import TemplatePreparedEditDeltaV1
        prefix = '/v1/rich/projects/' + fixture.project + '/writer/'
        prepare_wire = canonical(intent)
        prepared_reply = await client.post(prefix + 'prepare-delta', content=prepare_wire, headers={'Content-Type': 'application/json'})
        assert prepared_reply.status_code == 200
        prepared = TemplatePreparedEditDeltaV1.model_validate_json(prepared_reply.content)
        command = compact_command(fixture, prepared)
        save_wire = canonical(command)
        result = await client.post(prefix + 'save', content=save_wire, headers={'Content-Type': 'application/json'})
        assert result.status_code == 200 and len(result.content) < 6000
        assert len(canonical(value)) > 2 * 1024 * 1024 and len(prepare_wire) < 2000
        assert len(prepared_reply.content) < 6000 and len(save_wire) < 6000
        saved = WriterPreparedSaveAckV2.model_validate_json(result.content)
        assert saved.kind == 'committed' and saved.current_equals_committed
        assert adopted[-1][1] == fixture.current() and adopted[-1][2] == digest_bytes(fixture.current())


@pytest.mark.asyncio
async def test_delayed_compact_reply_cannot_replace_a_newer_cache_or_saved_baseline(tmp_path, monkeypatch):
    from resume_api.jobs.writers import mount_writers
    from resume_api.rich_projects import RichProjectService
    fixture = setup(tmp_path); first_prepared = prepare(fixture); first_command = compact_command(fixture,first_prepared)
    before_adoption, release_first = threading.Event(), threading.Event()
    local = threading.local()
    class AdoptionLock:
        def __init__(self): self.lock,self.delayed = threading.RLock(),False
        def __enter__(self):
            if getattr(local,'first_reply',False) and not self.delayed:
                self.delayed=True; before_adoption.set()
                if not release_first.wait(10): raise RuntimeError('controlled adoption wait expired')
            self.lock.acquire()
            return self
        def __exit__(self,*_args): self.lock.release()
    projects = object.__new__(RichProjectService)
    projects.state_lock=AdoptionLock(); projects.originals=fixture.originals; projects.artifacts={}; projects.images={}
    projects.workspaces={fixture.project:fixture.current()}; projects.saved_baselines={fixture.project:fixture.current()}
    projects.saved_hashes={}; projects.saved_revisions={}; projects.save_errors={}; projects.storage=fixture.canonical
    original_save=fixture.writers.save
    def save(project,payload,**kwargs):
        result=original_save(project,payload,**kwargs)
        local.first_reply=payload.mutation.client_mutation_id==first_command.mutation.client_mutation_id
        return result
    monkeypatch.setattr(fixture.writers,'save',save)
    service=SimpleNamespace(enabled=True,writers=fixture.writers,projects=projects,
        publication=SimpleNamespace(adopt=projects.adopt_committed))
    app=FastAPI(); mount_writers(app,service)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://controlled.test') as client:
        path='/v1/rich/projects/'+fixture.project+'/writer/save'
        first_task=asyncio.create_task(client.post(path,json=first_command.model_dump(mode='json',by_alias=True)))
        try:
            assert await asyncio.to_thread(before_adoption.wait,10)
            second_prepared=prepare(fixture,identifier='concurrent-next',action='concurrent-action')
            second_command=compact_command(fixture,second_prepared,2)
            second=await client.post(path,json=second_command.model_dump(mode='json',by_alias=True))
            assert second.status_code==200
            current=fixture.current(); assert current.project_revision==3
            assert projects.saved_baselines[fixture.project].project_revision==3
        finally:
            release_first.set()
        first=await first_task
        assert first.status_code==200
    assert projects.workspaces[fixture.project]==current
    assert projects.saved_baselines[fixture.project]==current
    assert projects.storage.expected[fixture.project]==digest_bytes(current)
