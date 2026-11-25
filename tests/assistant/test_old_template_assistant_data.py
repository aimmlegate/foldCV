"""D183: the template assistant is gone. A data root with its conversations, runs and proposals from an earlier version
still opens, the résumé assistant and the templates work, and the old files stay as they were. Synthetic data only."""

import json

from tests.assistant.support import assistant_app, base, conversation, finish, start

OLD = {
    'conversations/conversation-a.json': json.dumps({'id': 'conversation-a', 'title': 'Synthetic', 'messages': []}),
    'runs/run-a.jsonl': '{"sequence": 1}\nnot json\n',
    'proposals/proposal-a.json': json.dumps({'id': 'proposal-a', 'text': 'schema_version: 4\n', 'state': 'proposed'}),
    'samples/sample-a.json': '{"units": []}',
}


def test_a_root_with_old_template_assistant_files_opens_and_keeps_them(tmp_path):
    folder = tmp_path / 'data' / 'assistant-templates' / 'templates'
    for name, text in OLD.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding='utf-8')

    async def steps(_tools, _value, _cancel, emit):
        emit('message.delta', {'text': 'Ответ.'})
        return 'Ответ.'
    with assistant_app(tmp_path, steps) as (client, _application, _runtime):
        assert client.get('/v2/projects').status_code == 200
        assert client.get('/v1/settings/assistant').status_code == 200
        assert client.get('/v1/rich/template-config').status_code == 200
        # The routes of the removed assistant are gone (an unknown GET gets the page, not JSON); the résumé assistant runs.
        gone = client.get('/v2/templates/assistant/capabilities')
        assert 'json' not in gone.headers.get('content-type', '') and gone.text == 'v2 projects'
        assert client.post('/v2/templates/assistant/conversations', json={}).status_code in {404, 405}
        run, _events = finish(client, start(client, conversation(client)))
        assert run['state'] == 'completed'
        assert client.get(base() + '/capabilities').status_code == 200
    assert {name: (folder / name).read_text(encoding='utf-8') for name in OLD} == OLD
