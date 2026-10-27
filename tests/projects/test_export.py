"""An export is one completed attempt, a retry, and no undo barrier (plan SR04)."""

import hashlib

from packages.resume_core.models.template_render import TemplateRendererIdentity
from packages.resume_core.template_import import digest
from tests.projects.support import Editor, v2_app
from tests.templates.storage_fixtures import workspace as papers


PROJECT = 'template-project'
RENDERER = TemplateRendererIdentity(id='captured-docx', version='test', sha256='a' * 64)
DOCX = b'PK\x03\x04synthetic-export'


async def render(_request):
    return DOCX


def test_export_records_one_completed_attempt_and_retry_returns_the_same_bytes(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        exports = application.state.projects.exports
        exports._renderer = RENDERER
        exports.render = render
        editor = Editor(client, PROJECT)
        journal = application.state.projects.repository.open(PROJECT).directory / 'history.jsonl'
        before = journal.read_bytes() if journal.is_file() else None
        reply = client.post('/v2/projects/' + PROJECT + '/export', json={'schemaVersion': 1, 'editorToken': editor.token,
            'snapshot': editor.response['snapshot']})
        assert reply.status_code == 200, reply.text[:400]
        attempt = reply.headers['X-FoldCV-Export-Attempt']
        assert reply.content == DOCX
        assert reply.headers['X-FoldCV-Sha256'] == hashlib.sha256(DOCX).hexdigest()
        assert reply.headers['content-type'].startswith('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        saved = application.state.projects.repository.read(PROJECT)
        assert [item.id for item in saved.project.exports] == [attempt]
        assert saved.project.exports[0].state == 'completed'
        assert saved.project.exports[0].artifact_hash == hashlib.sha256(DOCX).hexdigest()
        assert saved.project.exports[0].renderer_hash == digest(RENDERER)
        assert len(saved.project.renders) == 1 and saved.project.renders[0].docx_sha256 == saved.project.exports[0].artifact_hash
        again = client.post('/v2/projects/' + PROJECT + '/exports/' + attempt + '/retry', json={'editorToken': editor.token})
        assert again.status_code == 200, again.text[:400]
        assert again.content == DOCX and again.headers['X-FoldCV-Export-Attempt'] != attempt
        saved = application.state.projects.repository.read(PROJECT)
        assert [item.state for item in saved.project.exports] == ['completed', 'completed']
        assert (journal.read_bytes() if journal.is_file() else None) == before
        assert b'barrier' not in (journal.read_bytes() if journal.is_file() else b'')


def test_an_edit_during_render_refuses_the_export_record(tmp_path):
    from tests.projects.test_edit_routes import typing
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        editor = Editor(client, PROJECT)
        service.exports._renderer = RENDERER

        async def render_after_edit(_request):
            from resume_api.projects.editing import edit
            from packages.resume_core.models.projects import EditRequestV1
            preparation = typing(editor, 'Human', 'concurrent-edit')
            edit(service, PROJECT, EditRequestV1(editorToken=editor.token, baseRevision=editor.revision,
                preparation=preparation))
            return DOCX

        service.exports.render = render_after_edit
        reply = client.post('/v2/projects/' + PROJECT + '/export', json={'schemaVersion': 1,
            'editorToken': editor.token, 'snapshot': editor.response['snapshot']})
        assert reply.status_code == 409 and reply.json()['error']['code'] == 'REVISION_CONFLICT'
        saved = service.repository.read(PROJECT)
        assert saved.project.exports == [] and saved.project.renders == []
        assert ''.join(span.text for span in saved.project.document.regions[2].blocks[0].content) == 'Human title'
        assert service.tasks.list(PROJECT)[0]['state'] == 'failed'
