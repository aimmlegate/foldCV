"""Strict template import through the app: upload -> V7 pre-draft -> template_import_v1 job -> published V7 project."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from packages.resume_core.reasoning import ModelReasoning
from packages.resume_core.templates.store import TemplateStore
from tests.recovery.test_agent_lifecycle import MetadataAdapter, Tools
from tests.templates.employment_fixtures import employment_package
from tests.templates.scripted_template_provider import ScriptedTemplateProvider

ORIGIN, SECRET = 'http://127.0.0.1:39291', 'synthetic-template-import-0123456789abcdef'


class CatalogAdapter(MetadataAdapter):
    def inspect(self, files, cancel, *, full=True):
        metadata = super().inspect(files, cancel, full=full)
        return replace(metadata, reasoning={name: ModelReasoning(supported=['medium'], default='medium') for name in metadata.models})


def refuse_execution(*_args, **_kwargs):
    raise AssertionError('template imports run no agent or fixed job runtime')


@asynccontextmanager
async def app_client(tmp_path, *, call_cap, provider, concurrency=1):
    from resume_api.agent.runtime import ScriptedAgentRuntime
    from resume_api.app import create_app
    dist = tmp_path / 'dist'; dist.mkdir()
    (dist / 'index.html').write_text('Synthetic template import boundary')
    data = tmp_path / 'data'
    wrapped = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / 'operations', dist=dist, data_root=data,
        connection_adapter=CatalogAdapter(), agent_runtime=ScriptedAgentRuntime(None), agent_tools=Tools(), gui_provider=provider,
        background_enabled=True, background_factory=refuse_execution, template_import_call_cap=call_cap,
        template_import_concurrency=concurrency)
    app, service, jobs = wrapped.app, wrapped.app.state.rich_projects, wrapped.app.state.jobs
    TemplateStore(service.storage.root).activate(employment_package())
    async with app.router.lifespan_context(app):
        # The wrapped app includes the request guard (body limits, upload paths), as the browser sees it.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url=ORIGIN, headers={'Origin': ORIGIN}) as client:
            assert (await client.post('/v1/session/exchange', json={'secret': SECRET})).status_code == 200
            assert (await client.post('/v1/host/status', json={})).status_code == 200
            assert (await client.post('/v1/host/select', json={'model': 'processing-model'})).status_code == 200
            try:
                yield client, service, jobs
            finally:
                await jobs.shutdown()
                service.request_shutdown()
                await service.shutdown()


async def upload(client, name='F01'):
    raw = Path('tests/fixtures/synthetic/templates/' + name + '.txt').read_bytes()
    return await client.post('/v1/rich/projects/template-input', files={'file': (name + '.txt', raw, 'text/plain')})


@pytest.mark.asyncio
async def test_upload_import_job_publishes_a_v7_employment_project_with_two_calls(tmp_path):
    provider = ScriptedTemplateProvider()
    async with app_client(tmp_path, call_cap=4, provider=provider) as (client, _service, _jobs):
        status = (await client.get('/v1/rich/template-import')).json()
        assert status['available'] is True and status['package']['name'] == 'Employment subset'
        created = await upload(client)
        assert created.status_code == 201, created.text
        workspace = created.json()['workspace']
        project = workspace['projectId']
        assert workspace['schemaVersion'] == 7 and workspace['project'] is None
        assert workspace['preDraft']['templatePackage']['packageHash'] == status['package']['packageHash']
        started = await client.post(f'/v1/rich/projects/{project}/template-import', json={'clientRequestId': 'import-1', 'allowTextRewrite': True})
        assert started.status_code == 202, started.text
        job = started.json()
        assert job['submission']['protocol'] == 'template_import_v1'
        assert job['submission']['templateCommand']['capture']['policy']['callCap'] == 4
        async def finished():
            while True:
                current = (await client.post(f'/v1/rich/projects/{project}/jobs/{job["id"]}/read', json={})).json()
                if current.get('templateOutcome') is not None:
                    return current
                await asyncio.sleep(0.05)
        current = await asyncio.wait_for(finished(), 60)
        assert current['templateOutcome']['state'] == 'saved', current
        opened = (await client.get(f'/v1/rich/projects/{project}')).json()
        texts = [''.join(part.get('text', '') for part in block.get('content', []))
            for region in opened['workspace']['project']['document']['regions'] for top in region['blocks']
            for block in [top, *top.get('children', [])]]
        assert 'Example Labs' in texts and 'Role: backend engineer' in texts
        assert [call['kind'] for call in provider.calls] == ['template_extraction', 'template_review']
        repeated = await client.post(f'/v1/rich/projects/{project}/template-import', json={'clientRequestId': 'import-1', 'allowTextRewrite': True})
        assert repeated.status_code in {200, 409} and len(provider.calls) == 2


@pytest.mark.asyncio
async def test_import_captures_the_settings_time_limit_and_keeps_it_when_settings_change(tmp_path):
    from datetime import datetime
    provider = ScriptedTemplateProvider()
    async with app_client(tmp_path, call_cap=4, provider=provider) as (client, service, _jobs):
        assert (await client.put('/v1/settings/limits', json={'importMinutes': 90, 'projectMegabytes': 64})).status_code == 200
        project = (await upload(client)).json()['workspace']['projectId']
        job = (await client.post(f'/v1/rich/projects/{project}/template-import', json={'clientRequestId': 'import-1', 'allowTextRewrite': True})).json()
        policy = job['submission']['templateCommand']['capture']['policy']
        assert (policy['processingSeconds'], policy['finalizationSeconds']) == (90 * 60, 30 + 2 * 64)
        async def finished():
            while True:
                current = (await client.post(f'/v1/rich/projects/{project}/jobs/{job["id"]}/read', json={})).json()
                if current.get('templateOutcome') is not None:
                    return current
                await asyncio.sleep(0.05)
        current = await asyncio.wait_for(finished(), 60)
        assert current['templateOutcome']['state'] == 'saved', current
        attempt = current['attempts'][-1]
        window = datetime.fromisoformat(attempt['activeDeadline']) - datetime.fromisoformat(attempt['dispatchedAt'])
        assert 90 * 60 <= window.total_seconds() < 90 * 60 + 30
        assert (await client.put('/v1/settings/limits', json={'importMinutes': 30, 'projectMegabytes': 64})).status_code == 200
        workspace = service.read(project)
        [operation] = workspace.project.template_operations
        service.validate_template_capture(operation, workspace)
        assert operation.capture.policy.processing_seconds == 90 * 60
        assert service.template_import_capture(workspace, True).policy.processing_seconds == 30 * 60
        assert (await client.put('/v1/settings/limits', json={'importMinutes': 30, 'projectMegabytes': 10})).status_code == 200
        service.validate_template_capture(operation, service.read(project))
        assert service.template_import_capture(workspace, True).policy.finalization_seconds == 30 + 2 * 10


@pytest.mark.asyncio
async def test_an_import_captures_the_configured_concurrency_and_a_stored_one_keeps_its_own(tmp_path):
    # CT10: the policy records how many blocks run at once; changing the setting later does not make it stale.
    provider = ScriptedTemplateProvider()
    async with app_client(tmp_path, call_cap=4, provider=provider, concurrency=3) as (client, service, _jobs):
        project = (await upload(client)).json()['workspace']['projectId']
        job = (await client.post(f'/v1/rich/projects/{project}/template-import', json={'clientRequestId': 'import-1', 'allowTextRewrite': True})).json()
        assert job['submission']['templateCommand']['capture']['policy']['concurrency'] == 3
        async def finished():
            while True:
                current = (await client.post(f'/v1/rich/projects/{project}/jobs/{job["id"]}/read', json={})).json()
                if current.get('templateOutcome') is not None:
                    return current
                await asyncio.sleep(0.05)
        assert (await asyncio.wait_for(finished(), 60))['templateOutcome']['state'] == 'saved'
        workspace = service.read(project)
        [operation] = workspace.project.template_operations
        service.template_import_concurrency = 1
        service.validate_template_capture(operation, workspace)
        assert operation.capture.policy.concurrency == 3 and service.template_import_capture(workspace, True).policy.concurrency == 1
    with pytest.raises(ValueError, match='concurrency'):
        service.configure_template_imports(call_cap=4, model=None, concurrency=5)


@pytest.mark.asyncio
async def test_without_an_explicit_call_cap_strict_import_is_unavailable(tmp_path):
    provider = ScriptedTemplateProvider()
    async with app_client(tmp_path, call_cap=None, provider=provider) as (client, _service, _jobs):
        assert (await client.get('/v1/rich/template-import')).json() == {'schemaVersion': 1, 'available': False, 'package': None}
        refused = await upload(client)
        assert refused.status_code == 409 and refused.json()['error']['code'] == 'JOB_DISABLED'
        assert provider.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('callCap', 99), ('configurationHash', '1' * 64),
    ('authorityHash', '2' * 64), ('dependencyHash', '3' * 64), ('effort', 'high'), ('processingSeconds', 200),
    ('processingSeconds', 600), ('finalizationSeconds', 20), ('finalizationSeconds', 60)])
async def test_generic_route_refuses_forged_capture_before_persistence(tmp_path, field, value):
    from tests.templates.employment_fixtures import employment_source
    provider = ScriptedTemplateProvider()
    async with app_client(tmp_path, call_cap=1, provider=provider) as (client, service, jobs):
        source, raw = employment_source('F01')
        project = service.allocate_template('Synthetic', service.template_import_package())
        service.workspaces[project].pre_draft.sources = [source]
        service.workspaces[project].pre_draft.selected_source_id = source.id
        service.originals[(project, source.id)] = raw
        service.persist(project)
        jobs.store.open(project)
        command = service.template_import_command(project, 'forged', True).model_dump(mode='json', by_alias=True)
        target = command['capture']['policy'] if field in {'callCap', 'processingSeconds', 'finalizationSeconds'} else (
            command['capture']['primary'] if field in {'configurationHash', 'effort'} else command['capture'])
        target[field] = value
        reply = await client.post(f'/v1/rich/projects/{project}/jobs/fixed', json=command)
        # Below the contract range is malformed; an in-range value other than the Settings limit is a stale capture.
        malformed = field == 'processingSeconds' and value < 300 or field == 'finalizationSeconds' and value < 30
        assert reply.status_code == (422 if malformed else 409), reply.text
        assert provider.calls == []
        assert service.read(project).pre_draft.template_operations == []
