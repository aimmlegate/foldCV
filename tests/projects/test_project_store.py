"""Project files on disk (project_store primitives under the repository): private modes across a restart, an isolated
corrupt project, tombstones that never come back, linked files that fail closed, and private text kept out of errors."""

import json
import os
import stat

import pytest

from packages.resume_core import project_repository
from packages.resume_core.project_repository import RepositoryFailure, blob_path
from packages.resume_core.project_store import encoded
from packages.resume_core.storage import atomic_write
from tests.projects.support import Editor, v2_app
from tests.projects.test_edit_routes import typing
from tests.templates.storage_fixtures import workspace as papers

FIRST, OTHER = 'template-project', 'other-project'


def projects():
    first, sources = papers()
    data = first.model_dump(by_alias=True)
    data['projectId'] = data['project']['projectId'] = OTHER
    return [(first, sources), (type(first).model_validate(data), sources)]


def test_a_restart_serves_the_committed_project_and_every_stored_file_stays_private(tmp_path):
    with v2_app(tmp_path, projects()) as (client, _application):
        editor = Editor(client, FIRST)
        editor.edit(typing(editor, 'Kept', 'edit-1'))
        before = editor.call('get', '')['workspace']
    with v2_app(tmp_path) as (client, _application):
        after = client.get('/v2/projects/' + FIRST).json()['workspace']
        assert after == before and after['projectRevision'] == 2
    data = tmp_path / 'data'
    assert stat.S_IMODE(data.stat().st_mode) == 0o700
    for path in data.rglob('*'):
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600), path


def test_a_corrupt_project_is_isolated_and_a_tombstone_never_resurrects_or_saves(tmp_path):
    with v2_app(tmp_path, projects()) as (client, application):
        repository = application.state.projects.repository
        target = repository.open(FIRST).directory / 'workspace.json'
        repository.close(FIRST)
        target.write_text('{broken')
        refused = client.post('/v2/projects/' + FIRST + '/open', json={})
        assert refused.status_code == 503 and refused.json()['error']['code'] == 'PROJECT_LOAD_FAILED'
        assert client.get('/v2/projects').json()['errors'] == [{'projectId': FIRST, 'errorCode': 'PROJECT_LOAD_FAILED'}]
        retained = repository.read(OTHER).model_copy(deep=True)
        repository.close(OTHER)
        registry = repository.store.registry()
        next(entry for entry in registry.entries if entry.project_id == OTHER).tombstoned = True
        atomic_write(repository.store.registry_path, encoded(registry.model_dump(mode='json', by_alias=True)))
        assert client.get('/v2/projects/' + OTHER).json()['error']['code'] == 'PROJECT_DELETED'
        assert OTHER not in {entry['projectId'] for entry in client.get('/v2/projects').json()['entries']}
        with pytest.raises(RepositoryFailure, match='PROJECT_EXISTS'):
            repository.create(retained)
        with pytest.raises(RepositoryFailure, match='PROJECT_DELETED'):
            repository.replace(OTHER, base_revision=retained.project_revision, workspace=retained)


@pytest.mark.parametrize('target', ['workspace', 'source', 'identity'])
def test_linked_project_files_fail_closed_without_touching_the_external_file(tmp_path, target):
    workspace, sources = papers()
    with v2_app(tmp_path, [(workspace, sources)]) as (_client, application):
        directory = application.state.projects.repository.open(FIRST).directory
    selected = {'workspace': directory / 'workspace.json', 'identity': directory / '.project-identity.json',
        'source': blob_path(directory, 'sources', 'source-papers')}[target]
    external = tmp_path / 'external'
    external.write_bytes(selected.read_bytes())
    external.chmod(0o600)
    before = external.read_bytes()
    selected.unlink()
    if target == 'source':
        os.link(external, selected)
    else:
        selected.symlink_to(external)
    with v2_app(tmp_path) as (client, _application):
        reply = client.get('/v2/projects/' + FIRST + ('/sources/source-papers/original' if target == 'source' else ''))
        assert reply.status_code == 503 and reply.json()['error']['code'] == 'PROJECT_UNSAFE_STORAGE'
    assert external.read_bytes() == before and stat.S_IMODE(external.stat().st_mode) == 0o600


def test_a_failed_project_write_keeps_the_edited_text_out_of_the_console_and_the_reply(tmp_path, monkeypatch, capsys, caplog):
    with v2_app(tmp_path, projects()) as (client, application):
        editor = Editor(client, FIRST)
        file = application.state.projects.repository.open(FIRST).directory / 'workspace.json'
        before = file.read_bytes()
        write = project_repository.atomic_write

        def failing(path, data):
            if path.name == 'workspace.json':
                raise OSError('synthetic error PRIVATE_STORAGE_EVIDENCE')
            write(path, data)
        monkeypatch.setattr(project_repository, 'atomic_write', failing)
        body = editor.edit(typing(editor, 'PRIVATE_STORAGE_EVIDENCE', 'edit-1'), status=503)
        assert body['error']['code'] == 'PROJECT_SAVE_FAILED' and 'PRIVATE_STORAGE_EVIDENCE' not in json.dumps(body)
        assert file.read_bytes() == before and editor.call('get', '')['workspace']['projectRevision'] == 1
    output = capsys.readouterr()
    assert 'PRIVATE_STORAGE_EVIDENCE' not in output.out + output.err + caplog.text
