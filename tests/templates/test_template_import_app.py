"""Strict template import through the app: upload -> V7 pre-draft -> v2 import task -> published V7 project."""

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from packages.resume_core.project_repository import decode_project
from packages.resume_core.reasoning import ModelReasoning
from packages.resume_core.templates.store import TemplateStore
from resume_api.connection import Metadata, Quota
from tests.templates.employment_fixtures import employment_package
from tests.templates.scripted_template_provider import ScriptedTemplateProvider

ORIGIN, SECRET = 'http://127.0.0.1:39291', 'synthetic-template-import-0123456789abcdef'


class CatalogAdapter:
    """Two models with a default effort; a native login is never run."""

    def inspect(self, _files, _cancel, *, full=True):
        return Metadata('fixture', ('assistant-model', 'processing-model'), 'plus', Quota('available', 10),
            {name: ModelReasoning(supported=['medium'], default='medium') for name in ('assistant-model', 'processing-model')})

    def login(self, _files, _cancel):
        raise AssertionError('native login')


def application(tmp_path, adapter, *, provider=None, call_cap, concurrency=1):
    from resume_api.app import create_app
    dist = tmp_path / 'dist'
    dist.mkdir(exist_ok=True)
    (dist / 'index.html').write_text('Synthetic template import boundary')
    wrapped = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / 'operations', dist=dist,
        data_root=tmp_path / 'data', connection_adapter=adapter, content_provider=provider,
        template_import_call_cap=call_cap, template_import_concurrency=concurrency)
    TemplateStore(wrapped.app.state.projects.repository.root).activate(employment_package())
    return wrapped


@asynccontextmanager
async def app_client(tmp_path, *, call_cap, provider, concurrency=1, adapter=None):
    """The wrapped app with the request guard (body limits, upload paths), as the browser sees it."""
    wrapped = application(tmp_path, adapter or CatalogAdapter(), provider=provider, call_cap=call_cap, concurrency=concurrency)
    app = wrapped.app
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url=ORIGIN, headers={'Origin': ORIGIN}) as client:
            assert (await client.post('/v1/session/exchange', json={'secret': SECRET})).status_code == 200
            assert (await client.post('/v1/host/status', json={})).status_code == 200
            assert (await client.post('/v1/host/select', json={'model': 'processing-model'})).status_code == 200
            yield client, app


async def upload(client, name='F01', template_id=None):
    raw = Path('tests/fixtures/synthetic/templates/' + name + '.txt').read_bytes()
    path = '/v1/rich/projects/template-input' + ('' if template_id is None else '/' + template_id)
    return await client.post(path, files={'file': (name + '.txt', raw, 'text/plain')})


async def run_import(client, app, project, request_id, *, allow_text_rewrite=True):
    """Start the import task, wait for it, and return its final status from GET /tasks."""
    started = await client.post('/v2/projects/' + project + '/import',
        json={'kind': 'start', 'clientRequestId': request_id, 'allowTextRewrite': allow_text_rewrite})
    assert started.status_code == 202, started.text
    task = started.json()
    runner = app.state.projects.imports.runners.get(task['id'])
    if runner is not None:
        await runner
    listed = (await client.get('/v2/projects/' + project + '/tasks')).json()['tasks']
    return next(value for value in listed if value['id'] == task['id'])


def saved(app, project):
    """The committed project with its import records (D104)."""
    directory = app.state.projects.repository.open(project).directory
    return decode_project(directory, (directory / 'workspace.json').read_bytes(), history=True)


def operation_of(app, project):
    workspace = saved(app, project)
    [operation] = (workspace.project or workspace.pre_draft).template_operations
    return operation


@pytest.mark.asyncio
async def test_upload_import_task_publishes_a_v7_employment_project_with_two_calls(tmp_path):
    provider = ScriptedTemplateProvider()
    async with app_client(tmp_path, call_cap=4, provider=provider) as (client, app):
        status = (await client.get('/v1/rich/template-import')).json()
        [default] = [value for value in status['templates'] if value['id'] == status['defaultId']]
        assert status['available'] is True and default['name'] == 'Employment subset'
        created = await upload(client)
        assert created.status_code == 201, created.text
        workspace = created.json()['workspace']
        project = workspace['projectId']
        assert workspace['schemaVersion'] == 7 and workspace['project'] is None
        assert workspace['preDraft']['templatePackage']['packageHash'] == default['packageHash']
        done = await run_import(client, app, project, 'import-1')
        assert (done['kind'], done['state'], done['error']) == ('import', 'succeeded', None), done
        assert operation_of(app, project).capture.policy.call_cap == 4
        opened = (await client.post('/v2/projects/' + project + '/open', json={})).json()['response']
        texts = [''.join(part.get('text', '') for part in block.get('content', []))
            for region in opened['workspace']['project']['document']['regions'] for top in region['blocks']
            for block in [top, *top.get('children', [])]]
        assert 'Example Labs' in texts and 'Role: backend engineer' in texts
        assert [call['kind'] for call in provider.calls] == ['template_extraction', 'template_review']
        # A published project is not imported again and no model is called.
        repeated = await run_import(client, app, project, 'import-1')
        assert repeated['state'] == 'failed' and len(provider.calls) == 2


@pytest.mark.asyncio
async def test_import_captures_the_settings_time_limit_and_keeps_it_when_settings_change(tmp_path):
    from datetime import datetime
    provider = ScriptedTemplateProvider()
    async with app_client(tmp_path, call_cap=4, provider=provider) as (client, app):
        intake = app.state.intake
        assert (await client.put('/v1/settings/limits', json={'importMinutes': 90, 'projectMegabytes': 64})).status_code == 200
        project = (await upload(client)).json()['workspace']['projectId']
        done = await run_import(client, app, project, 'import-1')
        assert done['state'] == 'succeeded', done
        operation = operation_of(app, project)
        policy = operation.capture.policy
        assert (policy.processing_seconds, policy.finalization_seconds) == (90 * 60, 30 + 2 * 64)
        window = datetime.fromisoformat(operation.expires_at) - datetime.fromisoformat(operation.admitted_at)
        assert window.total_seconds() == 90 * 60
        assert (await client.put('/v1/settings/limits', json={'importMinutes': 30, 'projectMegabytes': 64})).status_code == 200
        workspace = saved(app, project)
        intake.validate(operation, workspace)
        assert operation.capture.policy.processing_seconds == 90 * 60
        assert intake.capture(workspace, True).policy.processing_seconds == 30 * 60
        assert (await client.put('/v1/settings/limits', json={'importMinutes': 30, 'projectMegabytes': 10})).status_code == 200
        intake.validate(operation, saved(app, project))
        assert intake.capture(workspace, True).policy.finalization_seconds == 30 + 2 * 10


@pytest.mark.asyncio
async def test_an_import_captures_the_configured_concurrency_and_a_stored_one_keeps_its_own(tmp_path):
    # CT10: the policy records how many blocks run at once; changing the setting later does not make it stale.
    provider = ScriptedTemplateProvider()
    async with app_client(tmp_path, call_cap=4, provider=provider, concurrency=3) as (client, app):
        intake = app.state.intake
        project = (await upload(client)).json()['workspace']['projectId']
        assert (await run_import(client, app, project, 'import-1'))['state'] == 'succeeded'
        operation, workspace = operation_of(app, project), saved(app, project)
        assert operation.capture.policy.concurrency == 3
        intake.concurrency = 1
        intake.validate(operation, workspace)
        assert intake.capture(workspace, True).policy.concurrency == 1
        with pytest.raises(ValueError, match='concurrency'):
            intake.configure(call_cap=4, model=None, concurrency=5)


@pytest.mark.asyncio
async def test_a_stored_import_keeps_its_call_cap_when_the_configured_cap_changes(tmp_path):
    # Parallel review (2026-10-29): D117 raised the launcher's cap from 60 to 150, and an import saved with 60 failed
    # IMPORT_CAPTURE_STALE on resume. A stored import keeps its cap as it keeps its limits and concurrency (E07).
    provider = ScriptedTemplateProvider()
    async with app_client(tmp_path, call_cap=4, provider=provider) as (client, app):
        intake = app.state.intake
        project = (await upload(client)).json()['workspace']['projectId']
        assert (await run_import(client, app, project, 'import-1'))['state'] == 'succeeded'
        operation, workspace = operation_of(app, project), saved(app, project)
        intake.call_cap = 150
        intake.validate(operation, workspace)
        assert operation.capture.policy.call_cap == 4 and intake.capture(workspace, True).policy.call_cap == 150


@pytest.mark.asyncio
async def test_an_upload_captures_the_chosen_template_and_the_old_path_the_default(tmp_path, monkeypatch):
    from packages.resume_core.templates.compiler import compile_template
    from tests.templates.test_template_store import SECOND, second_bundled
    second = compile_template(second_bundled(tmp_path, monkeypatch))
    async with app_client(tmp_path, call_cap=4, provider=ScriptedTemplateProvider()) as (client, _app):
        chosen = await upload(client, template_id=SECOND)
        assert chosen.status_code == 201, chosen.text
        assert chosen.json()['workspace']['preDraft']['templatePackage']['packageHash'] == second.package_hash
        default = (await upload(client)).json()['workspace']['preDraft']['templatePackage']
        assert default['packageHash'] == employment_package().package_hash
        missing = await upload(client, template_id='missing')
        assert (missing.status_code, missing.json()['error']['code']) == (404, 'TEMPLATE_NOT_FOUND')
        # An unknown template answers before the body is parsed: a body that is not an upload still gets 404, not 422.
        unparsed = await client.post('/v1/rich/projects/template-input/missing', json={})
        assert (unparsed.status_code, unparsed.json()['error']['code']) == (404, 'TEMPLATE_NOT_FOUND')
        assert len((await client.get('/v2/projects')).json()['entries']) == 2


@pytest.mark.asyncio
async def test_without_an_explicit_call_cap_strict_import_is_unavailable(tmp_path):
    provider = ScriptedTemplateProvider()
    async with app_client(tmp_path, call_cap=None, provider=provider) as (client, _app):
        status = (await client.get('/v1/rich/template-import')).json()
        assert status['available'] is False and status['defaultId'] == employment_package().id
        refused = await upload(client)
        assert refused.status_code == 409 and refused.json()['error']['code'] == 'JOB_DISABLED'
        assert provider.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('quota,code', [('exhausted', 'QUOTA_EXHAUSTED'), ('available', 'CONNECTION_REQUIRED')])
async def test_an_import_start_names_an_exhausted_plan_instead_of_asking_to_connect(tmp_path, quota, code):
    # D104: with the plan used up the start said "connect a model in Settings", where nothing could be fixed.
    class Exhausted(CatalogAdapter):
        def inspect(self, files, cancel, *, full=True):
            return replace(super().inspect(files, cancel, full=full), quota=Quota(quota, 100 if quota == 'exhausted' else 10))
    wrapped = application(tmp_path, Exhausted(), call_cap=4)
    app = wrapped.app
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url=ORIGIN, headers={'Origin': ORIGIN}) as client:
            assert (await client.post('/v1/session/exchange', json={'secret': SECRET})).status_code == 200
            status = (await client.post('/v1/host/status', json={})).json()
            assert status['quota']['state'] == quota
            project = (await upload(client)).json()['workspace']['projectId']
            done = await run_import(client, app, project, 'start')
            assert (done['state'], done['error']) == ('failed', code)
            assert saved(app, project).pre_draft.template_operations == []
