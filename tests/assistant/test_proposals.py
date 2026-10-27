"""Proposals: stale by the pinned hashes, history by the stack top, Apply only with edits on, discard, persistence."""

from tests.assistant.support import (PROJECT, Editor, apply, assistant_app, base, manual_edit, proposals, proposing,
    run_once)
from tests.projects.support import v2_app

REPLACE = {'op': 'replace_text', 'blockId': 'block-paper-a', 'find': 'Shared', 'replace': 'Common'}


def test_a_manual_edit_of_a_touched_block_makes_the_proposal_stale_and_an_unrelated_one_does_not(tmp_path):
    with assistant_app(tmp_path) as (client, _app, runtime):
        run_once(client, proposing(REPLACE), runtime)
        run_once(client, proposing({'op': 'format_block', 'blockId': 'block-paper-b', 'alignment': 'right'}), runtime,
            request_id='request-2')
        touched, other = proposals(client)
        editor = Editor(client, PROJECT)
        manual_edit(editor, index=0, text='Human')
        refused = apply(client, editor, touched['id'], status=409)
        assert refused['error']['code'] == 'ASSISTANT_PROPOSAL_STALE' and refused['targets'] == ['block-paper-a']
        assert apply(client, editor, other['id'], mutation='apply-2')['proposal']['state'] == 'applied'
        assert editor.history['undo']['actionId'] == other['id']


def test_a_history_proposal_is_stale_once_the_stack_top_changed(tmp_path):
    with assistant_app(tmp_path) as (client, _app, runtime):
        editor = Editor(client, PROJECT)
        manual_edit(editor, text='First', mutation='manual-1')
        run_once(client, proposing({'op': 'history', 'direction': 'undo'}), runtime)
        proposal = proposals(client)[0]
        assert proposal['kind'] == 'history' and proposal['expectedActionId'] == 'manual-1'
        manual_edit(editor, index=1, text='Second', mutation='manual-2')
        refused = apply(client, editor, proposal['id'], status=409)
        assert refused['error']['code'] == 'ASSISTANT_PROPOSAL_STALE'
        assert editor.history['undo']['actionId'] == 'manual-2'


def test_apply_is_refused_while_edits_are_off_and_the_draft_stays(tmp_path):
    with assistant_app(tmp_path) as (client, _app, runtime):
        run_once(client, proposing(REPLACE), runtime)
        proposal = proposals(client)[0]
        editor = Editor(client, PROJECT)
        revision = editor.revision
        assert apply(client, editor, proposal['id'], edits=False, status=409)['error']['code'] == 'ASSISTANT_EDITS_OFF'
        assert proposals(client)[0]['state'] == 'draft' and Editor(client, PROJECT).revision == revision


def test_a_discarded_proposal_cannot_be_applied(tmp_path):
    with assistant_app(tmp_path) as (client, _app, runtime):
        run_once(client, proposing(REPLACE), runtime)
        proposal = proposals(client)[0]
        assert client.post(base() + f"/proposals/{proposal['id']}/discard", json={}).json()['state'] == 'discarded'
        editor = Editor(client, PROJECT)
        assert apply(client, editor, proposal['id'], status=409)['error']['code'] == 'ASSISTANT_PROPOSAL_CLOSED'


def test_apply_twice_with_one_mutation_id_saves_once(tmp_path):
    with assistant_app(tmp_path) as (client, _app, runtime):
        run_once(client, proposing(REPLACE), runtime)
        proposal = proposals(client)[0]
        editor = Editor(client, PROJECT)
        first = apply(client, editor, proposal['id'])
        again = apply(client, editor, proposal['id'])
        assert again['edit']['replayed'] and again['edit']['revision'] == first['edit']['revision']


def test_a_retried_apply_after_a_crash_before_the_proposal_file_replays_and_marks_it_applied(tmp_path, monkeypatch):
    with assistant_app(tmp_path) as (client, application, runtime):
        run_once(client, proposing(REPLACE), runtime)
        proposal = proposals(client)[0]
        editor = Editor(client, PROJECT)
        store = application.state.assistant.store
        saved = store.save_proposal

        def crash(_value):
            raise OSError('crash after the project commit')
        monkeypatch.setattr(store, 'save_proposal', crash)
        reply = client.post(base() + f"/proposals/{proposal['id']}/apply", json={'editorToken': editor.token,
            'clientMutationId': 'apply-1', 'allowEdits': True})
        assert reply.status_code >= 500 or reply.status_code == 409
        assert proposals(client)[0]['state'] == 'draft'
        monkeypatch.setattr(store, 'save_proposal', saved)
        again = apply(client, editor, proposal['id'])
        assert again['edit']['replayed'] and again['proposal']['state'] == 'applied'
        assert editor.history['undo']['actionId'] == proposal['id']


def test_proposals_and_findings_survive_a_service_restart(tmp_path):
    async def steps(tools, _value, _cancel, _emit):
        await tools.call('read_resume', {'page': 0})
        await tools.call('propose_changes', {'request': {'summary': 'Правка', 'ops': [REPLACE]}})
        await tools.call('publish_findings', {'request': {'findings': [{'message': 'Проверьте год',
            'targets': [{'blockId': 'block-paper-a'}]}]}})
        return 'Готово.'
    with assistant_app(tmp_path) as (client, _app, runtime):
        run_once(client, steps, runtime)
        conversation_id = client.get(base() + '/conversations').json()['items'][0]['id']
    with v2_app(tmp_path) as (client, _app):
        assert [item['state'] for item in proposals(client)] == ['draft']
        messages = client.get(base() + f'/conversations/{conversation_id}/messages').json()
        assert [finding['message'] for finding in messages['findings']] == ['Проверьте год']
        assert messages['messages'][-1]['findings'][0]['label'] == 'Проверьте год'
