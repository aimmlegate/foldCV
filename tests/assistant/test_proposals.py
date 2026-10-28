"""Proposals: stale by the pinned hashes, history by the stack top, Apply only with edits on, discard, persistence."""

import threading

from packages.resume_core.models.assistant import AssistantApplyRequestV1
from resume_api.assistant import proposals as proposal_service
from resume_api.projects.errors import ProjectFailure
from tests.assistant.support import (PROJECT, Editor, apply, assistant_app, base, manual_edit, proposals, proposing,
    run_once)
from tests.projects.support import v2_app

REPLACE = {'op': 'replace_text', 'blockId': 'block-paper-a', 'find': 'Shared', 'replace': 'Common'}
# Inserting after a block leaves its hash unchanged, so only the proposal state can refuse a second Apply.
INSERT = {'op': 'insert_blocks', 'afterBlockId': 'block-paper-a',
    'blocks': [{'kind': 'paragraph', 'text': 'Вставка'}]}


def overlapped(monkeypatch, repository, first, second):
    """`first` holds its commit until `second` has asked for the project or ended; returns both outcomes or codes."""
    committing, asked, outcomes = threading.Event(), threading.Event(), {}
    real_open, real_mutate = repository.open, repository.mutate

    def open_(project_id):
        if threading.current_thread().name == 'second':
            asked.set()
        return real_open(project_id)

    def mutate(*args, **kwargs):
        if threading.current_thread().name == 'first':
            committing.set()
            assert asked.wait(5)
        return real_mutate(*args, **kwargs)
    monkeypatch.setattr(repository, 'open', open_)
    monkeypatch.setattr(repository, 'mutate', mutate)

    def run(name, work):
        try:
            outcomes[name] = work(name)
        except ProjectFailure as error:
            outcomes[name] = error.code
        finally:
            if name == 'second':
                asked.set()
    threads = {name: threading.Thread(target=run, args=(name, work), name=name)
        for name, work in (('first', first), ('second', second))}
    threads['first'].start()
    assert committing.wait(5)
    threads['second'].start()
    for thread in threads.values():
        thread.join(10)
    return outcomes


def applying(service, proposal_id, editor):
    return lambda name: proposal_service.apply(service, PROJECT, proposal_id, AssistantApplyRequestV1.model_validate(
        {'editorToken': editor.token, 'clientMutationId': 'apply-' + name, 'allowEdits': True}))


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


def test_a_second_apply_during_an_apply_is_closed_and_the_proposal_commits_once(tmp_path, monkeypatch):
    with assistant_app(tmp_path) as (client, application, runtime):
        run_once(client, proposing(INSERT), runtime)
        proposal = proposals(client)[0]
        editor = Editor(client, PROJECT)
        service, repository = application.state.assistant, application.state.projects.repository
        revision = repository.read(PROJECT).project_revision
        outcomes = overlapped(monkeypatch, repository, applying(service, proposal['id'], editor),
            applying(service, proposal['id'], editor))
        assert outcomes['first'].proposal.state == 'applied' and outcomes['second'] == 'ASSISTANT_PROPOSAL_CLOSED'
        workspace = repository.read(PROJECT)
        texts = [block.content[0].text for block in workspace.project.document.regions[2].blocks if block.content]
        assert workspace.project_revision == revision + 1 and texts.count('Вставка') == 1


def test_a_discard_during_an_apply_is_closed_and_the_proposal_stays_applied(tmp_path, monkeypatch):
    with assistant_app(tmp_path) as (client, application, runtime):
        run_once(client, proposing(INSERT), runtime)
        proposal = proposals(client)[0]
        service = application.state.assistant
        outcomes = overlapped(monkeypatch, application.state.projects.repository,
            applying(service, proposal['id'], Editor(client, PROJECT)),
            lambda _name: proposal_service.discard(service, PROJECT, proposal['id']))
        assert outcomes['first'].proposal.state == 'applied' and outcomes['second'] == 'ASSISTANT_PROPOSAL_CLOSED'
        assert proposals(client)[0]['state'] == 'applied'


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
