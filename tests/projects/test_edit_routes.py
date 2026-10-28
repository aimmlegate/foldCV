"""POST /v2/projects/{id}/edits: editor token, revision conflicts with the applied ids, read-only and too-large projects,
dependency stamps and retries (plan 2.3, 2.5)."""

import json

import pytest

from packages.resume_core import project_repository
from packages.resume_core.templates.presentation import snapshot_identity
from tests.projects.support import Editor, v2_app
from tests.templates.storage_fixtures import workspace as papers
from tests.templates.test_template_preparation import command

PROJECT = 'template-project'


def typing(editor, text, identifier, *, start=0, end=6, dependencies=()):
    value = command(editor.workspace(), start=start, end=end, text=text)
    value.client_mutation_id, value.capture.action_id = identifier, 'action-' + identifier
    from packages.resume_core.models.rich_mutations import DependencyStamp
    value.capture.dependencies = [DependencyStamp.model_validate(stamp) for stamp in dependencies]
    return value.model_dump(mode='json', by_alias=True)


@pytest.fixture
def app(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        yield client, application


def test_an_edit_commits_once_and_a_retry_returns_the_stored_outcome(app):
    client, _application = app
    editor = Editor(client, PROJECT)
    preparation = typing(editor, 'Human', 'edit-1')
    first = editor.edit(preparation)
    assert first['revision'] == 2 and not first['replayed'] and first['changedBlockIds'] == ['block-paper-a']
    assert ''.join(span['text'] for span in first['response']['workspace']['project']['document']['regions'][2]['blocks'][0]['content']) == 'Human title'
    assert first['history']['undo']['actionId'] == 'action-edit-1' and first['response']['durability'] == 'durable'
    again = editor.edit(preparation, base=1)
    assert again['replayed'] and again['revision'] == 2 and again['response']['workspace']['mutationReplay'][-1]['clientMutationId'] == 'edit-1'


def test_a_stale_base_returns_the_revision_and_the_applied_ids(app):
    client, _application = app
    editor = Editor(client, PROJECT)
    stale = typing(editor, 'Late', 'edit-late')
    editor.edit(typing(editor, 'Human', 'edit-1'))
    body = editor.edit(stale, base=1, status=409)
    assert body['error']['code'] == 'REVISION_CONFLICT'
    assert body['revision'] == 2 and body['appliedClientMutationIds'] == ['edit-1']


def test_replaced_and_unknown_tokens_are_refused_and_reopen_continues(app):
    client, _application = app
    first = Editor(client, PROJECT)
    second = Editor(client, PROJECT)
    preparation = typing(second, 'Human', 'edit-1')
    stale = dict(first.__dict__)
    first.token, first.response = stale['token'], second.response
    assert first.edit(preparation, status=409)['error']['code'] == 'EDITOR_REPLACED'
    first.token = 'editor_unknown_token_value'
    assert first.edit(preparation, status=409)['error']['code'] == 'EDITOR_TOKEN_UNKNOWN'
    assert second.edit(preparation)['revision'] == 2


def test_a_read_only_project_refuses_edits(app):
    client, application = app
    editor = Editor(client, PROJECT)
    application.state.projects.catalog.update(PROJECT, read_only=True)
    body = editor.edit(typing(editor, 'Human', 'edit-1'), status=409)
    assert body['error']['code'] == 'PROJECT_READ_ONLY' and editor.call('get', '')['workspace']['projectRevision'] == 1


def test_a_project_above_the_size_setting_refuses_the_edit_and_keeps_the_file(app, monkeypatch):
    client, application = app
    editor = Editor(client, PROJECT)
    monkeypatch.setattr(project_repository, 'project_file_bytes', lambda: 1024)
    body = editor.edit(typing(editor, 'Human', 'edit-1'), status=413)
    assert body['error']['code'] == 'PROJECT_TOO_LARGE' and editor.call('get', '')['workspace']['projectRevision'] == 1


def test_a_stale_dependency_stamp_or_snapshot_is_refused_without_a_change(app):
    client, _application = app
    editor = Editor(client, PROJECT)
    stamp = {'kind': 'block', 'id': 'block-paper-b', 'revision': 99, 'fingerprint': None}
    body = editor.edit(typing(editor, 'Human', 'edit-1', dependencies=[stamp]), status=422)
    assert body['error']['code'] == 'V7_INPUT_REJECTED'
    preparation = typing(editor, 'Human', 'edit-2')
    preparation['snapshot']['documentHash'] = '0' * 64
    assert editor.edit(preparation, status=422)['error']['code'] == 'V7_INPUT_REJECTED'
    assert editor.call('get', '')['workspace']['projectRevision'] == 1


def test_a_panel_refusal_keeps_its_code_and_changes_nothing(app):
    client, _application = app
    editor = Editor(client, PROJECT)
    value, workspace = typing(editor, 'x', 'panel-1'), editor.workspace()
    value['operations'] = [{'opId': 'panel', 'kind': 'builtin_panel', 'command': {'operation': 'add', 'recordKind': 'language',
        'recordId': None, 'jobId': None, 'periodId': None, 'values': {'language': 'French'}, 'capture': value['capture'],
        'factsRevision': workspace.project.facts.revision, 'documentRevision': workspace.document_revision}}]
    assert editor.edit(value, status=422)['error']['code'] == 'PANEL_ACTION_UNSUPPORTED'
    assert editor.call('get', '')['workspace']['projectRevision'] == 1


def test_a_split_reports_its_created_block(app):
    client, _application = app
    editor = Editor(client, PROJECT)
    value = typing(editor, 'x', 'split-1')
    block = editor.workspace().project.document.regions[2].blocks[0]
    value['operations'] = [{'opId': 'split', 'kind': 'split_block', 'blockId': block.id, 'beforeRevision': block.revision, 'offset': 7}]
    result = editor.edit(value)
    blocks = [item['id'] for item in result['response']['workspace']['project']['document']['regions'][2]['blocks']]
    assert result['createdBlocks'] == {'split': [blocks[1]]} and blocks[0] == block.id and len(blocks) == 3


def test_every_code_the_routes_return_has_a_readable_message():
    catalog = json.loads(open('contracts/error-messages.ru.json').read())
    for code in ['REVISION_CONFLICT', 'EDITOR_TOKEN_UNKNOWN', 'EDITOR_REPLACED', 'PROJECT_READ_ONLY', 'PROJECT_TOO_LARGE',
            'HISTORY_STALE', 'MUTATION_ID_REUSED', 'V7_INPUT_REJECTED', 'DEPENDENCY_CHANGED', 'REQUEST_EXPIRED']:
        assert catalog['messages'][catalog['codes'][code]]


def test_v2_routes_need_the_session_and_the_origin(tmp_path):
    from fastapi.testclient import TestClient
    from tests.projects.support import ORIGIN
    with v2_app(tmp_path, [papers()]) as (_client, application):
        wrapped = application.state.projects
        assert wrapped is not None
    from resume_api.app import create_app
    dist = tmp_path / 'dist-plain'
    dist.mkdir()
    (dist / 'index.html').write_text('x')
    boundary = create_app(origin=ORIGIN, secret='s' * 40, temp_root=tmp_path / 'ops2', dist=dist, data_root=tmp_path / 'data2')
    with TestClient(boundary, base_url=ORIGIN, headers={'Origin': ORIGIN}) as anonymous:
        assert anonymous.get('/v2/projects').status_code == 401
    with TestClient(boundary, base_url=ORIGIN, headers={'Origin': 'http://127.0.0.1:1'}) as foreign:
        assert foreign.post('/v2/projects/x/open', json={}).status_code == 403
