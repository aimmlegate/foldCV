"""Project actions: one per proposal, a preview, Apply through the same service calls the project buttons use."""

from tests.assistant.support import PROJECT, Editor, apply, assistant_app, base, proposals, proposing, run_once


def action(name, value=None, target=None):
    op = {'op': 'action', 'action': name}
    if value is not None:
        op['value'] = value
    if target is not None:
        op['targetId'] = target
    return op


def test_rename_shows_the_old_and_new_title_and_applies_through_the_service(tmp_path):
    with assistant_app(tmp_path) as (client, application, runtime):
        old = application.state.projects.repository.read(PROJECT).title
        run_once(client, proposing(action('rename', '  Backend CV  ')), runtime)
        proposal = proposals(client)[0]
        assert proposal['kind'] == 'action' and proposal['preview'][0]['before'] == old
        assert proposal['preview'][0]['after'] == 'Backend CV'
        result = apply(client, Editor(client, PROJECT), proposal['id'])
        assert result['action'] == {'action': 'rename', 'title': 'Backend CV', 'archived': None, 'deleted': False}
        listing = client.get('/v2/projects').json()
        assert next(item for item in listing['entries'] if item['projectId'] == PROJECT)['title'] == 'Backend CV'


def test_formatting_date_archive_and_restore_apply_one_action_each(tmp_path):
    with assistant_app(tmp_path) as (client, application, runtime):
        run_once(client, proposing(action('formatting_date', '2026-03')), runtime)
        run_once(client, proposing(action('archive')), runtime, request_id='request-2')
        run_once(client, proposing(action('restore')), runtime, request_id='request-3')
        dated, archived, restored = proposals(client)
        editor = Editor(client, PROJECT)
        apply(client, editor, dated['id'], mutation='apply-1')
        date = application.state.projects.repository.read(PROJECT).formatting_as_of
        assert (date.precision, date.year, date.month) == ('month', 2026, 3)
        assert apply(client, editor, archived['id'], mutation='apply-2')['action']['archived'] is True
        assert application.state.projects.catalog.get(PROJECT).archived
        assert apply(client, editor, restored['id'], mutation='apply-3')['action']['archived'] is False
        assert not application.state.projects.catalog.get(PROJECT).archived


def test_delete_needs_the_project_id_and_removes_the_project_and_its_assistant_files(tmp_path):
    async def wrong(tools, _value, _cancel, _emit):
        result = await tools.call('propose_changes', {'request': {'summary': 'Удалить', 'ops': [action('delete', target='other')]}})
        assert result['error']['code'] == 'ASSISTANT_OP_INVALID'
        return 'Не удалено.'
    with assistant_app(tmp_path) as (client, application, runtime):
        run_once(client, wrong, runtime)
        assert proposals(client) == []
        run_once(client, proposing(action('delete', target=PROJECT)), runtime, request_id='request-2')
        proposal = proposals(client)[0]
        folder = application.state.assistant.store.directory(PROJECT)
        assert folder.exists()
        assert apply(client, Editor(client, PROJECT), proposal['id'])['action']['deleted'] is True
        assert client.get('/v2/projects/' + PROJECT).status_code in {404, 410}
        assert not folder.exists()


def test_apply_without_a_stored_proposal_is_refused(tmp_path):
    with assistant_app(tmp_path) as (client, _application, _runtime):
        editor = Editor(client, PROJECT)
        reply = client.post(base() + '/proposals/proposal_unknown/apply', json={'editorToken': editor.token,
            'clientMutationId': 'apply-1', 'allowEdits': True})
        assert reply.status_code == 404 and reply.json()['error']['code'] == 'ASSISTANT_PROPOSAL_NOT_FOUND'
