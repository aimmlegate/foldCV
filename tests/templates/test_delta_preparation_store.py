"""Full and delta preparations share immutable request identity and capacity."""

from dataclasses import replace
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from packages.resume_core import background_store
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.template_delta import TemplatePreparedEditDeltaV1
from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.models.template_writer import WriterMutationV2
from packages.resume_core.templates.compiler import canonical
from tests.templates.test_bounded_history import large_workspace
from tests.templates.test_preparation_store import request, setup
from tests.templates.test_template_writers import TemplateWriterFixture


def save_delta(fixture, delta):
    mutation = TemplateMutationV1.model_validate_json(delta.mutation_wire)
    return WriterMutationV2(**fixture.advance_request(1, [{'cursor': 1, 'mutation': mutation}]).model_dump(by_alias=True),
        mutation=mutation, preparation={'requestHash': delta.request_hash})


@pytest.mark.parametrize('first', ['full', 'delta'])
def test_response_form_is_immutable_but_not_part_of_the_request_hash(tmp_path, first):
    fixture = setup(tmp_path); intent = request(fixture)
    primary = fixture.writers.prepare_edit if first == 'full' else fixture.writers.prepare_edit_delta
    alternate = fixture.writers.prepare_edit_delta if first == 'full' else fixture.writers.prepare_edit
    prepared = primary(fixture.project, intent)
    old = fixture.writers.preparations.openings[fixture.project]
    assert canonical(primary(fixture.project, intent)) == canonical(prepared)
    with pytest.raises(BackgroundFailure, match='PREPARATION_RESPONSE_FORM_CONFLICT'):
        alternate(fixture.project, intent)
    assert fixture.writers.preparations.openings[fixture.project] is old
    intent.preparation.operations[0].text = 'Another request under the same ID'
    with pytest.raises(BackgroundFailure, match='JOB_IDEMPOTENCY_CONFLICT'):
        alternate(fixture.project, intent)


def test_delta_memo_needs_no_package_backing_and_replays_without_current_facts(tmp_path, monkeypatch):
    value, sources = large_workspace(); fixture = TemplateWriterFixture(tmp_path, value, sources)
    intent = request(fixture, start=2, end=2, text='!', target={'kind': 'literal'})
    prepared = fixture.writers.prepare_edit_delta(fixture.project, intent)
    registry = fixture.writers.preparations
    opening = registry.openings[fixture.project]
    assert opening.backing is None and len(canonical(prepared)) < 6000
    assert registry.usage()[fixture.project].draft_bytes < 6000
    assert registry.usage()[fixture.project].records == 2
    state = fixture.jobs.load(fixture.project)
    entry = registry.find(state, intent.preparation, response_form='delta')
    # Reading an immutable delta never reconstructs a preview from newer facts.
    current = fixture.current(); current.project = None
    def forbidden(*_args):
        pytest.fail('delta replay must not resolve captured package backing')
    monkeypatch.setattr(registry, 'backing', forbidden)
    assert canonical(registry.read(state, current, entry)) == canonical(prepared)


@pytest.mark.parametrize('limit', ['draft_project_bytes', 'draft_global_bytes', 'metadata_project_records', 'metadata_global_records'])
def test_failed_delta_admission_reserves_no_response_form_or_id(tmp_path, monkeypatch, limit):
    fixture = setup(tmp_path); intent = request(fixture)
    registry = fixture.writers.preparations
    state = fixture.jobs.load(fixture.project)
    bound = 1 if limit.startswith('draft') else background_store.records(state)
    with monkeypatch.context() as limited:
        limited.setattr(background_store, 'LIMITS', replace(background_store.LIMITS, **{limit: bound}))
        with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
            fixture.writers.prepare_edit_delta(fixture.project, intent)
    assert not registry.openings and not registry.usage()
    prepared = fixture.writers.prepare_edit(fixture.project, intent)
    assert prepared.client_mutation_id == intent.preparation.client_mutation_id


def test_delta_save_uses_exact_registered_mutation_and_keeps_terminal_form_guard(tmp_path):
    fixture = setup(tmp_path); intent = request(fixture)
    prepared = fixture.writers.prepare_edit_delta(fixture.project, intent)
    command = save_delta(fixture, prepared)
    saved = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert saved.local_history_ack is not None
    registry = fixture.writers.preparations
    entry = registry.openings[fixture.project].entries[prepared.client_mutation_id]
    assert entry.payload is None and entry.response_form == 'delta'
    assert fixture.writers.save(fixture.project, command, originals=fixture.originals).replayed
    with pytest.raises(BackgroundFailure, match='REQUEST_EXPIRED'):
        fixture.writers.prepare_edit_delta(fixture.project, intent)
    with pytest.raises(BackgroundFailure, match='PREPARATION_RESPONSE_FORM_CONFLICT'):
        fixture.writers.prepare_edit(fixture.project, intent)


@pytest.mark.asyncio
async def test_delta_route_returns_compact_typed_result_and_explicit_form_conflict(tmp_path):
    from resume_api.jobs.writers import mount_writers
    fixture = setup(tmp_path)
    service = SimpleNamespace(enabled=True, writers=fixture.writers)
    app = FastAPI(); mount_writers(app, service)
    @app.exception_handler(BackgroundFailure)
    async def failure(_request, error):
        return JSONResponse({'error': {'code': error.code}}, status_code=409)
    intent = request(fixture)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://controlled.test') as client:
        path = '/v1/rich/projects/' + fixture.project + '/writer/'
        result = await client.post(path + 'prepare-delta', json=intent.model_dump(mode='json', by_alias=True))
        assert result.status_code == 200
        prepared = TemplatePreparedEditDeltaV1.model_validate_json(result.content)
        assert len(result.content) < 12000 and 'preview' not in json.loads(result.content)
        conflict = await client.post(path + 'prepare', json=intent.model_dump(mode='json', by_alias=True))
        assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'PREPARATION_RESPONSE_FORM_CONFLICT'
        assert prepared.capture == intent.preparation.capture
