"""Exact input binding leaves normalization and preparation memo identity in Python."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.template_writer import WriterPreparedDeltaV2
from packages.resume_core.templates.compiler import canonical, sha256
from tests.templates.test_preparation_store import request, setup


def bound_request(fixture, spelling='full'):
    intent = request(fixture)
    value = intent.preparation.model_dump(mode='json', by_alias=True)
    if spelling == 'omitted':
        value['operations'][0]['styles'] = {}
    raw = canonical(value).decode()
    if spelling in {'float', 'scientific'}:
        raw = raw.replace('"schemaVersion":1', '"schemaVersion":' + ('1.0' if spelling == 'float' else '1e0'), 1)
    if spelling == 'whitespace':
        raw = ' \n' + raw + '\n '
    intent.preparation_input_wire = raw
    return intent


@pytest.mark.parametrize('spelling', ['full', 'omitted', 'float', 'scientific', 'whitespace'])
def test_exact_input_spelling_is_bound_without_changing_canonical_preparation(tmp_path, spelling):
    fixture = setup(tmp_path)
    old = request(fixture)
    legacy = fixture.writers.prepare_edit_delta(fixture.project, old)
    opening = fixture.writers.preparations.openings[fixture.project]
    entry = opening.entries[old.preparation.client_mutation_id]
    usage = fixture.writers.preparations.usage()
    intent = bound_request(fixture, spelling)
    result = fixture.writers.prepare_edit_delta(fixture.project, intent)
    assert isinstance(result, WriterPreparedDeltaV2)
    assert result.preparation_input_sha256 == sha256(intent.preparation_input_wire.encode())
    assert result.request_hash == legacy.request_hash and canonical(result.delta) == canonical(legacy)
    assert fixture.writers.preparations.openings[fixture.project] is opening
    assert opening.entries[old.preparation.client_mutation_id] is entry
    assert fixture.writers.preparations.usage() == usage
    assert canonical(fixture.writers.prepare_edit_delta(fixture.project, intent)) == canonical(result)


@pytest.mark.parametrize('bad', ['duplicate', 'nan', 'infinity', 'overflow', 'surrogate', 'trailing', 'mismatch'])
def test_invalid_or_mismatched_bound_input_admits_nothing(tmp_path, bad):
    fixture = setup(tmp_path)
    intent = bound_request(fixture)
    raw = intent.preparation_input_wire
    if bad == 'duplicate':
        raw = raw[:-1] + ',"schemaVersion":1}'
    elif bad in {'nan', 'infinity', 'overflow'}:
        raw = raw.replace('"actionToken":1', '"actionToken":' + {'nan': 'NaN', 'infinity': 'Infinity', 'overflow': '1e999'}[bad])
    elif bad == 'surrogate':
        raw = raw.replace('"text":"Human"', '"text":"\\ud800"')
    elif bad == 'trailing':
        raw += '{}'
    else:
        raw = raw.replace('"text":"Human"', '"text":"Different"')
    assert raw != intent.preparation_input_wire
    intent.preparation_input_wire = raw
    before = canonical(fixture.current())
    with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
        fixture.writers.prepare_edit_delta(fixture.project, intent)
    assert not fixture.writers.preparations.openings
    assert canonical(fixture.current()) == before


def test_binding_does_not_change_old_callers_or_full_delta_memo_conflict(tmp_path):
    fixture = setup(tmp_path)
    legacy = request(fixture)
    assert 'preparationInputWire' not in legacy.model_dump(by_alias=True)
    prepared = fixture.writers.prepare_edit(fixture.project, bound_request(fixture, 'omitted'))
    assert prepared.request_hash
    with pytest.raises(BackgroundFailure, match='PREPARATION_RESPONSE_FORM_CONFLICT'):
        fixture.writers.prepare_edit_delta(fixture.project, bound_request(fixture, 'scientific'))


def test_wrapper_hash_must_match_the_unchanged_delta_request_identity(tmp_path):
    fixture = setup(tmp_path)
    result = fixture.writers.prepare_edit_delta(fixture.project, bound_request(fixture))
    value = result.model_dump(mode='json', by_alias=True)
    value['requestHash'] = '0' * 64
    with pytest.raises(ValueError, match='transport binding'):
        WriterPreparedDeltaV2.model_validate(value)


@pytest.mark.asyncio
async def test_actual_route_returns_current_input_binding_around_one_exact_memo(tmp_path):
    from resume_api.jobs.writers import mount_writers
    fixture = setup(tmp_path)
    app = FastAPI()
    mount_writers(app, SimpleNamespace(enabled=True, writers=fixture.writers))
    @app.exception_handler(BackgroundFailure)
    async def failure(_request, error):
        return JSONResponse({'error': {'code': error.code}}, status_code=409)
    results = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://controlled.test') as client:
        path = '/v1/rich/projects/' + fixture.project + '/writer/prepare-delta'
        for spelling in ['omitted', 'scientific', 'full']:
            intent = bound_request(fixture, spelling)
            reply = await client.post(path, json=intent.model_dump(mode='json', by_alias=True))
            assert reply.status_code == 200
            result = WriterPreparedDeltaV2.model_validate_json(reply.content)
            assert result.preparation_input_sha256 == sha256(intent.preparation_input_wire.encode())
            results.append(result)
        assert len({result.preparation_input_sha256 for result in results}) == 3
        assert len({result.request_hash for result in results}) == 1
        assert len({canonical(result.delta) for result in results}) == 1
        assert len(fixture.writers.preparations.openings[fixture.project].entries) == 1
        invalid = bound_request(fixture)
        invalid.preparation_input_wire = json.dumps({'schemaVersion': 1})
        rejected = await client.post(path, json=invalid.model_dump(mode='json', by_alias=True))
        assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'JOB_SCOPE_INVALID'
