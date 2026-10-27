"""Import tasks: start, progress, cancel, sidecar resume, and a revision conflict (plan SR04)."""

import asyncio
from types import SimpleNamespace

import pytest

from packages.resume_core.project_repository import RepositoryFailure, decode_project
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


def test_import_reports_progress_and_cancel_stops_it(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        service.imports.pipeline = HoldingPipeline()
        service.imports.commands = None
        started = client.post('/v2/projects/' + PROJECT + '/import', json={'kind': 'start', 'clientRequestId': 'request-1'})
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
        assert resumed.json()['state'] == 'succeeded'
        current = saved(application.state.projects.repository, PROJECT)
        assert current.project_revision == 3
        assert current.project.template_operations[0].last_observed_at == '2026-10-21T00:20:00+00:00'
        assert 'Human' in current.project.document.regions[2].blocks[0].content[0].text
        assert not (application.state.projects.repository.open(PROJECT).directory / 'imports' / (operation.id + '.json')).is_file()


def test_publication_at_an_old_revision_fails_the_import(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        editor = Editor(client, PROJECT)
        editor.edit(typing(editor, 'Human', 'edit-1'))
        task = service.tasks.start(PROJECT, 'import')
        stale = service.repository.read(PROJECT).model_copy(deep=True)
        with pytest.raises(RepositoryFailure) as error:
            service.imports.publish_at(PROJECT, task.id, stale, 1)
        assert error.value.code == 'REVISION_CONFLICT'
        assert service.tasks.list(PROJECT)[0]['state'] == 'failed'
        assert service.tasks.list(PROJECT)[0]['error'] == 'REVISION_CONFLICT'


def test_import_read_cache_hits_verify_the_committed_value(tmp_path, monkeypatch):
    from resume_api.importer.template_pipeline import TemplatePipeline
    monkeypatch.setenv('FOLDCV_VERIFY', '1')
    with v2_app(tmp_path, [papers()]) as (_client, application):
        pipeline = TemplatePipeline(None, repository=application.state.projects.repository,
            authority=None, assemble=None, derive=None, wall=lambda: '2026-10-21T00:00:00+00:00')
        pipeline.read(PROJECT).title = 'mutated cached value'
        with pytest.raises(RuntimeError, match='Import read cache changed'):
            pipeline.read(PROJECT)
