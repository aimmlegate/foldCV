"""Scripted Generic F10 through the v2 import route matches the composition of a direct coordinator run (plan S12).

Revisions, timestamps and mutation-replay rows are the repository's commit record. Fact text, source text and the
composition report of everything else must match. A semantic difference stops the slice; the golden is not updated.
"""

from itertools import count
import re

import pytest

from packages.resume_core.project_repository import decode_project
from resume_api.importer.template_pipeline import TemplatePipeline
from tests.projects.support import ORIGIN, v2_app
from tools.save_bench.composition import analyze

HEX = re.compile(r'^[0-9a-f]{64}$')
TEXT_KEYS = {'text', 'rawInput'}


def prepare(root, name='F10'):
    from packages.resume_core.project_limits import finalization_seconds, import_seconds
    from packages.resume_core.templates.operations import derive_task
    from tests.templates.generic_fixtures import REVIEWS, TABLES, generic_package, generic_script, source_fixture
    from tests.templates.template_runtime_fixtures import EmploymentFixture
    src, raw = source_fixture(name)
    fixture = EmploymentFixture(root, captured=generic_package(), src=src, original_bytes=raw, cap=60, fallback=False)
    fixture.command.capture.allow_text_rewrite = True
    fixture.command.capture.policy.processing_seconds = import_seconds()
    fixture.command.capture.policy.finalization_seconds = finalization_seconds()
    fixture.pipeline.derive = derive_task
    fixture.transport.scripted = generic_script(src, TABLES[name](True), REVIEWS.get(name))
    return fixture, raw, derive_task


def dumped(workspace):
    return workspace.model_dump(mode='json', by_alias=True)


def collect_text(value, key=None, found=None):
    found = [] if found is None else found
    if isinstance(value, dict):
        for child_key, child in value.items():
            collect_text(child, child_key, found)
    elif isinstance(value, list):
        for child in value:
            collect_text(child, key, found)
    elif isinstance(value, str) and key in TEXT_KEYS and HEX.fullmatch(value) is None:
        found.append(value)
    return found


def normalize(value, key=None):
    """Blank the commit bookkeeping composition.py is allowed to differ on."""
    if isinstance(value, dict):
        return {child_key: normalize(child, child_key) for child_key, child in value.items() if child_key != 'mutationReplay'}
    if isinstance(value, list):
        return [normalize(child) for child in value]
    if key in {'revision', 'projectRevision', 'documentRevision'} and isinstance(value, int):
        return 0
    if isinstance(value, str) and len(value) >= 20 and value[4:5] == '-' and value[7:8] == '-' and 'T' in value:
        return 'TIME'
    return value


def differing(left, right, path=''):
    if type(left) is not type(right):
        return [path + ': ' + type(left).__name__ + ' != ' + type(right).__name__]
    if isinstance(left, dict):
        rows = []
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                rows.append(path + '.' + key + ': missing')
            else:
                rows.extend(differing(left[key], right[key], path + '.' + key))
        return rows
    if isinstance(left, list):
        if len(left) != len(right):
            return [path + ': len ' + str(len(left)) + ' != ' + str(len(right))]
        rows = []
        for index, (item, other) in enumerate(zip(left, right)):
            rows.extend(differing(item, other, path + '[' + str(index) + ']'))
        return rows
    if left != right:
        return [path + ': ' + repr(left) + ' != ' + repr(right)]
    return []


@pytest.mark.slow
@pytest.mark.asyncio
async def test_f10_through_the_repository_matches_the_scripted_composition(tmp_path):
    def ids():
        serial = count(1)
        return lambda prefix: prefix + '-' + str(next(serial))
    old_fixture, _raw, _derive = prepare(tmp_path / 'direct', 'F10')
    old_fixture.pipeline.id_factory = ids()
    old_result = await old_fixture.pipeline.run(old_fixture.project, old_fixture.command, admitted=old_fixture.admitted)
    assert old_result.publication.state == 'saved'
    baseline = old_fixture.current()
    fixture, raw, derive_task = prepare(tmp_path / 'route', 'F10')
    import httpx
    with v2_app(tmp_path / 'http', [(fixture.before, {fixture.source.id: raw})]) as (client, app):
        service = app.state.projects
        pipeline = TemplatePipeline(fixture.transport, repository=service.repository,
            authority=fixture.pipeline.authority, assemble=fixture.assemble,
            derive=derive_task, wall=lambda: fixture.now, id_factory=ids())
        service.imports.pipeline = pipeline
        service.imports.commands = lambda *_args: fixture.command
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url=ORIGIN,
                headers={'Origin': ORIGIN}, cookies=client.cookies) as http:
            response = await http.post('/v2/projects/' + fixture.project + '/import',
                json={'kind': 'start', 'clientRequestId': fixture.command.client_request_id, 'allowTextRewrite': True})
            assert response.status_code == 202, response.text
            task_id = response.json()['id']
            runner = service.imports.runners.get(task_id)
            if runner is not None:
                await runner
            status = (await http.get('/v2/projects/' + fixture.project + '/tasks')).json()['tasks'][0]
            assert status['state'] == 'succeeded', status
        directory = service.repository.open(fixture.project).directory
        saved = decode_project(directory, (directory / 'workspace.json').read_bytes(), history=True)

    old, new = dumped(baseline), dumped(saved)
    assert collect_text(old['project']['sources']) == collect_text(new['project']['sources'])
    assert collect_text(old['project']) == collect_text(new['project'])
    report_gap = differing(analyze(normalize(old)), analyze(normalize(new)))
    assert not report_gap, '\n'.join(report_gap[:40])
