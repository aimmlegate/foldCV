"""Export refusals: a stale snapshot never reaches the renderer and a failed render records nothing (plan SR04)."""

from packages.resume_core.models.template_render import TemplateRendererIdentity
from resume_api.projects.errors import ProjectFailure
from tests.projects.support import Editor, v2_app
from tests.templates.storage_fixtures import workspace as papers


PROJECT = 'template-project'
RENDERER = TemplateRendererIdentity(id='captured-docx', version='test', sha256='a' * 64)


def test_a_stale_snapshot_is_refused_before_rendering_and_records_nothing(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        exports = application.state.projects.exports
        exports._renderer = RENDERER
        rendered = []
        async def render(request):
            rendered.append(request)
            return b'PK\x03\x04unexpected'
        exports.render = render
        editor = Editor(client, PROJECT)
        stale = {**editor.response['snapshot'], 'documentHash': '0' * 64}
        reply = client.post('/v2/projects/' + PROJECT + '/export', json={'schemaVersion': 1, 'editorToken': editor.token,
            'snapshot': stale})
        assert reply.status_code == 409 and reply.json()['error']['code'] == 'IMPORT_EXPORT_SNAPSHOT_STALE'
        saved = application.state.projects.repository.read(PROJECT)
        assert rendered == [] and saved.project.exports == [] and saved.project.renders == []
        assert saved.project_revision == editor.revision


def test_a_failed_render_records_no_attempt_and_its_task_names_the_failure(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        service.exports._renderer = RENDERER
        async def render(_request):
            raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503)
        service.exports.render = render
        editor = Editor(client, PROJECT)
        reply = client.post('/v2/projects/' + PROJECT + '/export', json={'schemaVersion': 1, 'editorToken': editor.token,
            'snapshot': editor.response['snapshot']})
        assert reply.status_code == 503 and reply.json()['error']['code'] == 'PROCESS_CLEANUP_FAILED'
        saved = service.repository.read(PROJECT)
        assert saved.project.exports == [] and saved.project.renders == [] and saved.project_revision == editor.revision
        [task] = service.tasks.list(PROJECT)
        assert (task['kind'], task['state'], task['error']) == ('export', 'failed', 'PROCESS_CLEANUP_FAILED')
