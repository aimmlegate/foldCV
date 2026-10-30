"""An export is one completed attempt, a retry, and no undo barrier (plan SR04); edits made during the render stay,
and the export waits for the project lock off the event loop."""

import asyncio
import hashlib
import json
import threading

import pytest

from packages.resume_core.models.template_render import TemplateRendererIdentity, TemplateSnapshotIdentity
from packages.resume_core.project_repository import EXPORT_ATTEMPTS, ProjectRepository, blob_path
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


def test_an_edit_during_render_stays_and_the_export_is_recorded_with_its_own_snapshot(tmp_path):
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
        assert reply.status_code == 200, reply.text[:400]
        assert reply.content == DOCX and json.loads(reply.headers['X-FoldCV-Snapshot']) == editor.response['snapshot']
        saved = service.repository.read(PROJECT)
        assert [item.id for item in saved.project.exports] == [reply.headers['X-FoldCV-Export-Attempt']]
        assert saved.project.export_inputs[0].snapshot.model_dump(mode='json', by_alias=True) == editor.response['snapshot']
        assert ''.join(span.text for span in saved.project.document.regions[2].blocks[0].content) == 'Human title'
        assert saved.project_revision == editor.revision + 2
        assert service.tasks.list(PROJECT)[0]['state'] == 'succeeded'
        assert Editor(client, PROJECT).history['undo']['actionId'] == 'action-concurrent-edit'


def test_an_export_waits_for_the_project_lock_off_the_event_loop_and_a_cancelled_one_leaves_no_pin(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        service.exports._renderer, service.exports.render = RENDERER, render
        editor = Editor(client, PROJECT)
        snapshot = TemplateSnapshotIdentity.model_validate(editor.response['snapshot'])
        session = service.repository.open(PROJECT)
        held, release, freed = threading.Event(), threading.Event(), []

        def hold():
            # Another holder doing slow I/O under the project lock, as a large commit does.
            with session.lock:
                held.set()
                freed.append(release.wait(5))

        async def scenario():
            holder = threading.Thread(target=hold)
            holder.start()
            held.wait(5)
            waiting = asyncio.create_task(service.exports.export(PROJECT, snapshot, editor.token))
            for _tick in range(5):
                await asyncio.sleep(0.01)
            waiting.cancel()
            release.set()
            await asyncio.to_thread(holder.join)
            with pytest.raises(asyncio.CancelledError):
                await waiting
            for _tick in range(200):
                if not session.pins:
                    break
                await asyncio.sleep(0.01)
            pins = session.pins
            return pins, await service.exports.export(PROJECT, snapshot, editor.token)

        pins, result = asyncio.run(scenario())
        assert freed == [True] and pins == 0 and result.artifact == DOCX
        assert [task['state'] for task in service.tasks.list(PROJECT)] == ['failed', 'succeeded']


def exported(client, editor):
    # A recorded export moves the project revision, so each export names the current snapshot.
    snapshot = client.get('/v2/projects/' + PROJECT).json()['snapshot']
    reply = client.post('/v2/projects/' + PROJECT + '/export', json={'schemaVersion': 1, 'editorToken': editor.token,
        'snapshot': snapshot})
    assert reply.status_code == 200, reply.text[:400]
    return reply.headers['X-FoldCV-Export-Attempt']


def test_repeated_exports_keep_one_capture_and_one_docx_so_the_project_file_stops_growing(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        service.exports._renderer, service.exports.render = RENDERER, render
        editor = Editor(client, PROJECT)
        directory = service.repository.open(PROJECT).directory
        attempts = [exported(client, editor)]
        once = (directory / 'workspace.json').stat().st_size
        attempts += [exported(client, editor) for _index in range(EXPORT_ATTEMPTS + 4)]
        saved = service.repository.read(PROJECT)
        assert [value.attempt_id for value in saved.project.export_inputs] == [attempts[-1]]
        assert [value.id for value in saved.project.renders] == [attempts[-1]]
        assert [value.id for value in saved.project.exports] == attempts[-EXPORT_ATTEMPTS:]
        assert [path.name for path in (directory / 'renders').iterdir()] == [blob_path(directory, 'renders', attempts[-1]).name]
        # Only the ids of the kept records, and the bounded attempt and replay lists, can change the size.
        assert (directory / 'workspace.json').stat().st_size < once + 2 * 1024 * (EXPORT_ATTEMPTS + 4)
        again = client.post('/v2/projects/' + PROJECT + '/exports/' + attempts[-1] + '/retry', json={'editorToken': editor.token})
        assert again.status_code == 200 and again.content == DOCX
        gone = client.post('/v2/projects/' + PROJECT + '/exports/' + attempts[0] + '/retry', json={'editorToken': editor.token})
        assert gone.status_code == 409 and gone.json()['error']['code'] == 'IMPORT_EXPORT_ATTEMPT_UNKNOWN'


def test_validation_cost_does_not_depend_on_past_exports_and_a_saved_backlog_is_trimmed(tmp_path, monkeypatch):
    from packages.resume_core.models import template_workspace
    from tests.projects.test_edit_routes import typing
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        service.exports._renderer, service.exports.render = RENDERER, render
        editor = Editor(client, PROJECT)
        exported(client, editor)
        repository = service.repository
        directory = repository.open(PROJECT).directory
        current = repository.read(PROJECT)
        # A project saved before the limit: many captures, render records and DOCX files.
        backlog = current.model_copy(deep=True)
        project = backlog.project
        for index in range(5):
            identifier = 'export-old-' + str(index)
            project.exports.insert(0, project.exports[-1].model_copy(update={'id': identifier}))
            capture = project.export_inputs[-1].model_copy(update={'attempt_id': identifier})
            project.export_inputs.insert(0, capture)
            project.renders.insert(0, project.renders[-1].model_copy(update={'id': identifier}))
            path = blob_path(directory, 'renders', identifier)
            path.write_bytes(DOCX)
            path.chmod(0o600)
        target = directory / 'workspace.json'
        target.write_bytes(backlog.model_dump_json(by_alias=True).encode())
        target.chmod(0o600)
        assert len(repository.read(PROJECT).project.export_inputs) == 6
        validated, seen = template_workspace.validated_with_history, []

        def counting(workspace):
            seen.append(len(workspace.project.export_inputs))
            return validated(workspace)

        monkeypatch.setattr(template_workspace, 'validated_with_history', counting)
        editor = Editor(client, PROJECT)
        editor.edit(typing(editor, 'Human', 'after-backlog'))
        assert seen == [1] and len(repository.read(PROJECT).project.renders) == 1
        repository.close(PROJECT)
        assert len(list((directory / 'renders').iterdir())) == 1
        assert len(ProjectRepository(tmp_path / 'data').read(PROJECT).project.export_inputs) == 1
