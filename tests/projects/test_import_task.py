"""Import tasks: start, progress, cancel, sidecar resume, and a revision conflict (plan SR04)."""

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.project_repository import decode_project
from resume_api.inference_admission import InferenceAdmission
from tests.projects.support import Editor, v2_app
from tests.projects.test_edit_routes import typing
from tests.templates.pipeline_fixtures import setup_operation
from tests.templates.storage_fixtures import workspace as papers


PROJECT = 'template-project'
FIELDS = {'id', 'projectId', 'kind', 'state', 'stage', 'startedAt', 'elapsed', 'detail', 'error'}


class HoldingPipeline:
    async def run(self, _project, _command, *, admitted, cancel_event=None):
        await admitted()
        while cancel_event is not None and not cancel_event.is_set():
            await asyncio.sleep(0.01)
        return SimpleNamespace(id='operation-hold', state='cancelled', publication=None)


class StubbornPipeline:
    """Admitted, then a model call that ends only when released, whatever the cancel says."""

    def __init__(self):
        self.release = threading.Event()

    async def run(self, _project, _command, *, admitted, cancel_event=None):
        await admitted()
        await asyncio.to_thread(self.release.wait, 10)
        return SimpleNamespace(id='operation-hold', state='processing', publication=None)


def with_operation():
    workspace, sources = papers()
    operation, *_rest = setup_operation(captured=workspace.project.template_package, src=workspace.project.sources[0])
    operation = operation.model_copy(update={'project_id': workspace.project_id})
    project = workspace.project.model_copy(deep=True)
    project.template_operations = [operation]
    workspace = workspace.model_copy(update={'project': project})
    return workspace, sources, operation


def saved(repository, project_id):
    session = repository.open(project_id)
    return decode_project(session.directory, (session.directory / 'workspace.json').read_bytes(), history=True)


def sidecar(repository, project_id, operation, facts, revision):
    from resume_api.projects.fold import sidecar_store
    session = repository.open(project_id)
    sidecar_store(session.directory).write(project_id, revision, operation, facts)
    return session.directory / 'imports' / (operation.id + '.json')


def start(client, request_id):
    return client.post('/v2/projects/' + PROJECT + '/import', json={'kind': 'start', 'clientRequestId': request_id})


def status(client, task_id):
    return next(item for item in client.get('/v2/projects/' + PROJECT + '/tasks').json()['tasks'] if item['id'] == task_id)


def finished(client, task_id):
    for _ in range(500):
        found = status(client, task_id)
        if found['state'] != 'running':
            return found
        time.sleep(0.01)
    raise AssertionError('the task is still running')


def test_import_reports_progress_and_cancel_stops_it(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        service.imports.pipeline = HoldingPipeline()
        service.imports.commands = None
        started = start(client, 'request-1')
        assert started.status_code == 202, started.text
        body = started.json()
        assert FIELDS <= set(body) and body['kind'] == 'import' and body['state'] == 'running'
        assert body['stage'] == 'processing' and body['detail']['operationId'] == 'request-1'
        assert isinstance(body['elapsed'], (int, float)) and body['error'] is None
        listed = client.get('/v2/projects/' + PROJECT + '/tasks')
        assert listed.status_code == 200 and listed.json()['tasks'][0]['id'] == body['id']
        cancelled = client.post('/v2/projects/' + PROJECT + '/import', json={'kind': 'cancel', 'taskId': body['id']})
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()['state'] == 'cancelled'


def test_a_cancelled_import_keeps_its_task_until_its_runner_ends(tmp_path):
    # A cancel marked the task cancelled after 2 s while the runner still held the permit; a new start then waited
    # for that permit forever.
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        pipeline = service.imports.pipeline = StubbornPipeline()
        service.imports.commands = None
        admission = service.imports.admission = InferenceAdmission()
        first = start(client, 'request-1').json()
        cancelled = client.post('/v2/projects/' + PROJECT + '/import', json={'kind': 'cancel', 'taskId': first['id']})
        assert cancelled.status_code == 200 and cancelled.json()['state'] == 'running'
        refused = start(client, 'request-2')
        assert refused.status_code == 409 and refused.json()['error']['code'] == 'REQUEST_IN_PROGRESS'
        pipeline.release.set()
        assert finished(client, first['id'])['state'] == 'cancelled' and not admission.locked()
        again = start(client, 'request-3')
        assert again.status_code == 202, again.text
        assert finished(client, again.json()['id'])['state'] == 'succeeded'


def test_a_queued_import_is_answered_at_once_and_shows_that_it_waits(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        pipeline = HoldingPipeline()
        pipeline.read = service.repository.read
        service.imports.pipeline, service.imports.commands = pipeline, None
        admission = service.imports.admission = InferenceAdmission()
        # An assistant turn has the permit; the start used to wait for it 30 s and then fail with 408.
        assert admission.acquire(blocking=False)
        started = start(client, 'request-1')
        assert started.status_code == 202, started.text
        assert (started.json()['state'], started.json()['stage']) == ('running', 'queued')
        assert status(client, started.json()['id'])['stage'] == 'queued'
        admission.release()
        for _ in range(500):
            if status(client, started.json()['id'])['stage'] == 'processing':
                break
            time.sleep(0.01)
        assert status(client, started.json()['id'])['stage'] == 'processing'
        client.post('/v2/projects/' + PROJECT + '/import', json={'kind': 'cancel', 'taskId': started.json()['id']})
        assert finished(client, started.json()['id'])['state'] == 'cancelled'


def test_the_import_cancel_refuses_a_task_of_another_kind(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        export = service.tasks.start(PROJECT, 'export', stage='rendering')
        reply = client.post('/v2/projects/' + PROJECT + '/import', json={'kind': 'cancel', 'taskId': export.id})
        assert reply.status_code == 404 and reply.json()['error']['code'] == 'JOB_NOT_FOUND'
        assert not export.cancel.is_set() and status(client, export.id)['state'] == 'running'


@pytest.mark.parametrize('stop', ['shutdown', 'sign-out'])
def test_shutdown_and_sign_out_stop_a_running_import(tmp_path, stop):
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        service.imports.pipeline = HoldingPipeline()
        service.imports.commands = None
        task_id = start(client, 'request-1').json()['id']
        if stop == 'sign-out':
            assert client.post('/v1/host/detach', json={}).status_code == 200
            assert status(client, task_id)['state'] == 'cancelled'
    assert service.tasks.list(PROJECT)[0]['state'] == 'cancelled' and not service.imports.runners


def test_a_sidecar_resumes_after_a_crash_and_a_manual_edit_keeps_its_text(tmp_path):
    workspace, sources, operation = with_operation()
    observed = operation.model_copy(update={'last_observed_at': '2026-10-21T00:10:00+00:00'})
    with v2_app(tmp_path, [(workspace, sources)]) as (client, application):
        repository = application.state.projects.repository
        path = sidecar(repository, PROJECT, observed, workspace.project.facts, 1)
        assert path.is_file()
        editor = Editor(client, PROJECT)
        editor.edit(typing(editor, 'Human', 'edit-1'))
        folded = saved(repository, PROJECT)
        assert folded.project_revision == 2
        assert folded.project.template_operations[0].last_observed_at == observed.last_observed_at
        assert 'Human' in folded.project.document.regions[2].blocks[0].content[0].text
        assert not path.is_file()
        later = observed.model_copy(update={'last_observed_at': '2026-10-21T00:20:00+00:00'})
        path = sidecar(repository, PROJECT, later, folded.project.facts, 2)
        assert path.is_file()
    with v2_app(tmp_path, ()) as (client, application):
        class ResumePipeline:
            def read(self, project):
                return saved(application.state.projects.repository, project)

            async def run(self, project, command, *, admitted, cancel_event=None):
                assert command.kind == 'resume_import' and command.operation_id == operation.id
                await admitted()
                return SimpleNamespace(id=operation.id, state='published', publication=SimpleNamespace(state='saved'))

        application.state.projects.imports.pipeline = ResumePipeline()
        resumed = client.post('/v2/projects/' + PROJECT + '/import', json={'kind': 'resume', 'operationId': operation.id})
        assert resumed.status_code == 202, resumed.text
        assert finished(client, resumed.json()['id'])['state'] == 'succeeded'
        current = saved(application.state.projects.repository, PROJECT)
        assert current.project_revision == 3
        assert current.project.template_operations[0].last_observed_at == '2026-10-21T00:20:00+00:00'
        assert 'Human' in current.project.document.regions[2].blocks[0].content[0].text
        assert not (application.state.projects.repository.open(PROJECT).directory / 'imports' / (operation.id + '.json')).is_file()


def test_an_edit_that_conflicts_with_an_import_sidecar_reports_the_applied_ids(tmp_path):
    workspace, sources, operation = with_operation()
    with v2_app(tmp_path, [(workspace, sources)]) as (client, application):
        repository = application.state.projects.repository
        editor = Editor(client, PROJECT)
        editor.edit(typing(editor, 'Human', 'edit-1'))
        # The import changed the facts in its sidecar; the next edit changes them another way.
        facts = saved(repository, PROJECT).project.facts
        sidecar(repository, PROJECT, operation, facts.model_copy(update={'revision': facts.revision + 1}), 2)
        body = editor.edit(typing(editor, 'Other', 'edit-2'), status=409)
        assert body['error']['code'] == 'REVISION_CONFLICT'
        assert body['revision'] == 2 and body['appliedClientMutationIds'] == ['edit-1']


def test_import_read_cache_hits_verify_the_committed_value(tmp_path, monkeypatch):
    from resume_api.importer.template_pipeline import TemplatePipeline
    monkeypatch.setenv('FOLDCV_VERIFY', '1')
    with v2_app(tmp_path, [papers()]) as (_client, application):
        pipeline = TemplatePipeline(None, repository=application.state.projects.repository,
            authority=None, assemble=None, derive=None, wall=lambda: '2026-10-21T00:00:00+00:00')
        pipeline.read(PROJECT).title = 'mutated cached value'
        with pytest.raises(RuntimeError, match='Import read cache changed'):
            pipeline.read(PROJECT)


def test_the_import_read_cache_never_returns_a_replaced_workspace(tmp_path, monkeypatch):
    from resume_api.importer import template_pipeline
    monkeypatch.delenv('FOLDCV_VERIFY', raising=False)
    # Every object at one address: the reuse CPython may make once a commit frees the previous workspace.
    monkeypatch.setattr(template_pipeline, 'id', lambda _value: 1, raising=False)
    with v2_app(tmp_path, [papers()]) as (_client, application):
        repository = application.state.projects.repository
        pipeline = template_pipeline.TemplatePipeline(None, repository=repository, authority=None, assemble=None,
            derive=None, wall=lambda: '2026-10-21T00:00:00+00:00')
        assert pipeline.read(PROJECT).title == 'Synthetic papers'
        renamed = repository.read(PROJECT).model_copy(update={'title': 'Renamed'})
        repository.replace(PROJECT, base_revision=1, workspace=renamed, reason='rename')
        assert pipeline.read(PROJECT).title == 'Renamed'


def test_the_import_read_cache_keeps_a_few_projects(tmp_path):
    from resume_api.importer.template_pipeline import CACHED_READS, TemplatePipeline
    workspace, sources = papers()
    projects = []
    for index in range(CACHED_READS + 2):
        data = workspace.model_dump(by_alias=True)
        data['projectId'] = data['project']['projectId'] = 'project-' + str(index)
        projects.append((WorkspaceV7.model_validate(data), sources))
    with v2_app(tmp_path, projects) as (_client, application):
        pipeline = TemplatePipeline(None, repository=application.state.projects.repository, authority=None,
            assemble=None, derive=None, wall=lambda: '2026-10-21T00:00:00+00:00')
        for value, _sources in projects:
            pipeline.read(value.project_id)
        assert list(pipeline.read_cache) == [value.project_id for value, _sources in projects[-CACHED_READS:]]
