"""«Написать заново по резюме» (F6a): what is sent, what code keeps of a reply, the second call, and the Apply through
the block reword. The document is a lite import of an invented CV whose contact line also holds a phone number."""

import json

import pytest

from packages.resume_core.importing.lite import prompts as P
from packages.resume_core.importing.lite.rules import block_rules
from packages.resume_core.repository import block_write as W
from tests.templates.test_lite_import import lite_run

CONTACT = 'nina@example.org, +7 900 555 01 02'
GOOD = ('Руководитель группы разработки биллинга в АО «Северная линия». Работаю с Java, Spring Boot, PostgreSQL и '
        'Kafka, планирую кварталы и распределяю задачи.')


def run(tmp_path):
    # Line 4 is the contact line the map hides; it gets a phone number, so a number stands only in a hidden line.
    return lite_run(tmp_path, 'promotions', lines={4: CONTACT})


@pytest.fixture(scope='module')
def imported(tmp_path_factory):
    fixture, operation = run(tmp_path_factory.mktemp('write'))
    workspace = fixture.current()
    hidden = W.hidden_lines([operation])
    # Since F6b the list block can be written again too; these cases are about the summary.
    block_id, = [block for block in W.writable(workspace, hidden) if W.write_source(workspace, block, hidden) is not None]
    return workspace, operation, hidden, block_id


def summary(offered):
    """The summary among the blocks the route offers to write again (the list block is offered too since F6b)."""
    found = [block for block in offered['write'] if offered['rules'][block].startswith('О себе')]
    assert len(found) == 1
    return found[0]


def source_of(imported):
    workspace, _operation, hidden, block_id = imported
    return W.write_source(workspace, block_id, hidden)


def sent(prompt):
    return json.loads(prompt)


def test_only_the_summary_is_offered_and_the_lines_sent_leave_out_the_hidden_ones(imported):
    workspace, operation, hidden, block_id = imported
    source = W.write_source(workspace, block_id, hidden)
    assert source.target.kind == 'text' and source.title == 'О СЕБЕ'
    assert CONTACT in hidden and 'Опыт работы' in hidden
    texts = [W.fold(line.text) for line in source.lines]
    assert CONTACT not in texts and 'Опыт работы' not in texts and 'Спроектировала сервис тарификации на Kafka' in texts
    # Every other top-level block, a job card too, has no such action.
    blocks = [block.id for region in workspace.project.document.regions for block in region.blocks]
    assert [block for block in blocks if W.write_source(workspace, block, hidden) is not None] == [block_id]
    # An import that hid no line (an import before 1.1.0 kept no such rows) gives no action.
    bare = operation.model_copy(update={'other_lines': [rows for rows in operation.other_lines if rows.reason != 'hidden']})
    assert W.hidden_lines([bare]) is None and W.writable(workspace, W.hidden_lines([bare])) == []
    assert W.hidden_lines([operation.model_copy(update={'state': 'failed'})]) is None and W.hidden_lines([]) is None


@pytest.mark.parametrize('envelope', [False, True])
def test_the_request_has_its_own_task_the_users_request_the_present_text_and_no_rule_of_wording_outside_it(imported, envelope):
    workspace = imported[0]
    source = source_of(imported)
    definition = workspace.project.template_package.definition
    rules = block_rules('summary', definition)
    token = P.ENVELOPE.set(envelope)
    try:
        first = sent(W.write_request(source, '  ' + rules[0] + '\n\n' + rules[1] + '  '))
        again = sent(W.write_request(source, 'Коротко.', 'it was too long.'))
    finally:
        P.ENVELOPE.reset(token)
    assert ('output' in first) is envelope and ('payload' in first['example']['reply']) is envelope
    assert 'has no text of its own' not in first['task'] and first['task'].startswith('Write the text of one block')
    assert first['request'] == rules[0] + '\n' + rules[1]
    assert first['present'] == source.target.text and any('not from present' in rule for rule in first['rules'])
    assert first['lines'] == P.pairs(source.lines) and 'refused' not in first
    # holds and the template's own instructions are not sent; a rule of wording stands only in the request.
    assert not {'holds', 'write', 'instructions'} & set(first)
    outside = json.dumps({key: value for key, value in first.items() if key != 'request'}, ensure_ascii=False)
    own = next(block for block in definition.blocks if block.id == 'summary').rewrite.instructions
    assert not [rule for rule in [*rules, *definition.model.rewrite, *own, P.WRITE['summary']['holds']] if rule in outside]
    assert again['request'] == 'Коротко.'
    assert again['refused'] == 'The text you wrote before was refused: it was too long. Write it again without that.'
    assert P.rewrite_schema() == P.WRITE_SHAPES['text']


@pytest.mark.parametrize('reply, state, reason, words, again', [
    ({'text': GOOD, 'lines': ['S2', 'S8', 'S13']}, 'changed', None, [], False),
    ({'text': None, 'lines': []}, 'refused', 'empty', [], False),
    # The number stands in the CV, but only in a hidden line, which was not sent (coordinator's decision 5).
    ({'text': GOOD + ' На связи: 900.', 'lines': ['S2']}, 'refused', 'number', ['900'], True),
    ({'text': GOOD + ' Уровень Senior.', 'lines': ['S2']}, 'refused', 'name', ['senior'], True),
    ({'text': 'Руководитель группы разрабoтки.', 'lines': ['S2']}, 'refused', 'mixed', ['разрабoтки'], True),
    ({'text': 'Руководитель группы. ' * 90, 'lines': ['S2']}, 'refused', 'long', [], True),
    # A ref of a hidden line, or of no line, is no line to rest on.
    ({'text': GOOD, 'lines': ['S4', 'S900']}, 'refused', 'lines', [], True),
])
def test_code_keeps_a_text_by_the_imports_checks_against_the_lines_sent(imported, reply, state, reason, words, again):
    value, told = W.write_value(source_of(imported), reply)
    assert (value.state, value.reason, value.words, bool(told)) == (state, reason, words, again)
    assert value.before == source_of(imported).target.text
    assert value.after == (W.fold(reply['text']) if reply['text'] else None)


def test_the_present_text_given_back_is_no_change(imported):
    source = source_of(imported)
    value, told = W.write_value(source, {'text': source.target.text, 'lines': ['S2']})
    assert (value.state, value.after, told) == ('same', None, None)


class Writing:
    """A provider that answers each write request from a list of replies, in turn."""

    def __init__(self, *replies, on_call=None):
        self.replies, self.requests, self.on_call = list(replies), [], on_call

    def generate(self, request, _files, _cancel):
        from resume_api.providers.content import ContentResult, ReportedUsage
        from resume_api.providers.dynamic_result import PayloadEnvelope
        self.requests.append(request)
        if self.on_call is not None:
            self.on_call(len(self.requests))
        return ContentResult(PayloadEnvelope(payload=self.replies.pop(0)), ReportedUsage(), 'fixture', request.policy.model, .01, 1)


def app(tmp_path, provider):
    from tests.projects.support import Editor, v2_app
    fixture, _operation = run(tmp_path / 'import')
    workspace = fixture.current()
    return workspace, v2_app(tmp_path / 'app', [(workspace, fixture.originals)], content_provider=provider), Editor


def test_a_refused_text_gets_one_more_call_in_the_same_task_and_apply_unchanged_stays_green_until_accepted(tmp_path):
    provider = Writing({'text': 'Руководитель группы разрабoтки.', 'lines': ['S2']}, {'text': GOOD, 'lines': ['S2', 'S8', 'S13']})
    workspace, context, Editor = app(tmp_path, provider)
    with context as (client, application):
        project = workspace.project_id
        editor = Editor(client, project)
        # The import records are in the history files only (D104): the route reads the hidden lines from them.
        assert not application.state.projects.repository.open(project).workspace.project.template_operations
        offered = client.get('/v2/projects/' + project + '/reword/blocks').json()
        block_id = summary(offered)
        assert block_id in offered['blockIds']
        before = application.state.projects.repository.read(project)
        shown = editor.call('post', '/reword/preview', {'editorToken': editor.token, 'requestId': 'write-1',
            'blockId': block_id, 'instruction': offered['rules'][block_id], 'mode': 'write'})
        first, second = (json.loads(request.text).get('payload', json.loads(request.text)) for request in provider.requests)
        assert 'refused' not in first and 'two alphabets' in second['refused']
        assert CONTACT not in json.dumps(first, ensure_ascii=False)
        assert shown['mode'] == 'write' and [(value['state'], value['after']) for value in shown['values']] == [('changed', GOOD)]
        tasks = [task for task in application.state.projects.tasks.list(project) if task['kind'] == 'rewrite']
        assert len(tasks) == 1 and tasks[0]['state'] == 'succeeded'
        assert application.state.projects.repository.read(project) == before
        value = shown['values'][0]
        diff = lambda: client.get('/v2/projects/' + project + '/source-diff').json()['added']
        body = {'editorToken': editor.token, 'clientMutationId': 'write-apply-1', 'blockId': block_id, 'touched': shown['touched'],
            'changes': [{'recordId': value['recordId'], 'field': value['field'], 'value': GOOD, 'edited': False}]}
        applied = editor.adopt(editor.call('post', '/reword/apply', body))
        record = next(item for item in applied['response']['workspace']['project']['facts']['extensions']
                      if item['id'] == value['recordId'])
        assert record['cells'][0]['rawInput'] == GOOD
        cell = record['cells'][0]['id']
        # The value keeps its old source lines: the words they lack are green, the model's (G2b), until «Принять».
        green = diff()[cell]
        assert 'планирую' in green and 'Java' not in green
        stale = editor.refused('post', '/reword/apply', {**body, 'clientMutationId': 'write-apply-2'}, 409)
        assert 'ASSISTANT_PROPOSAL_STALE' in json.dumps(stale)
        editor.adopt(editor.call('post', '/accept', {'editorToken': editor.token, 'clientMutationId': 'accept-1', 'cellId': cell}))
        assert cell not in diff()
        editor.step('undo', 'undo-accept')
        assert diff()[cell] == green
        undone = editor.step('undo', 'undo-write', expected=applied['history']['undo']['actionId'])
        record = next(item for item in undone['response']['workspace']['project']['facts']['extensions']
                      if item['id'] == value['recordId'])
        assert record['cells'][0]['rawInput'] == value['before']


def test_an_edited_preview_is_the_users_text_and_no_text_gets_no_second_call(tmp_path):
    provider = Writing({'text': None, 'lines': []}, {'text': GOOD, 'lines': ['S2']})
    workspace, context, Editor = app(tmp_path, provider)
    with context as (client, _application):
        project = workspace.project_id
        editor = Editor(client, project)
        block_id = summary(client.get('/v2/projects/' + project + '/reword/blocks').json())
        ask = lambda identifier: editor.call('post', '/reword/preview', {'editorToken': editor.token, 'requestId': identifier,
            'blockId': block_id, 'instruction': 'Коротко.', 'mode': 'write'})
        empty = ask('write-empty')
        assert len(provider.requests) == 1
        assert [(value['state'], value['reason'], value['after']) for value in empty['values']] == [('refused', 'empty', None)]
        shown = ask('write-2')
        value = shown['values'][0]
        editor.adopt(editor.call('post', '/reword/apply', {'editorToken': editor.token, 'clientMutationId': 'write-apply',
            'blockId': block_id, 'touched': shown['touched'],
            'changes': [{'recordId': value['recordId'], 'field': value['field'], 'value': GOOD + ' Сама.', 'edited': True}]}))
        cell = next(item for item in editor.workspace().project.facts.extensions if item.id == value['recordId']).cells[0].id
        assert cell not in client.get('/v2/projects/' + project + '/source-diff').json()['added'], 'G2a'


def test_a_text_refused_twice_has_no_apply_and_a_cancel_between_the_calls_stops_the_second(tmp_path):
    wrong = {'text': GOOD + ' Уровень Senior.', 'lines': ['S2']}
    holder = {}

    def cancel_after_first(count):
        # The third call is the first one of the request that is cancelled.
        if count == 3 and holder.get('cancel'):
            holder['cancel']()
    provider = Writing(wrong, wrong, wrong, on_call=cancel_after_first)
    workspace, context, Editor = app(tmp_path, provider)
    with context as (client, application):
        project = workspace.project_id
        editor = Editor(client, project)
        block_id = summary(client.get('/v2/projects/' + project + '/reword/blocks').json())
        body = {'editorToken': editor.token, 'blockId': block_id, 'instruction': 'Коротко.', 'mode': 'write'}
        twice = editor.call('post', '/reword/preview', {**body, 'requestId': 'write-twice'})
        assert len(provider.requests) == 2
        assert [(value['state'], value['reason'], value['words']) for value in twice['values']] == [('refused', 'name', ['senior'])]
        # A cancel that comes while the first call ends is kept for the request and stops its second call.
        rewrite = application.state.projects
        holder['cancel'] = lambda: rewrite.rewrite_cancel(project, 'write-cancel')
        refused = editor.refused('post', '/reword/preview', {**body, 'requestId': 'write-cancel'}, 409)
        assert 'CANCELLED' in json.dumps(refused) and len(provider.requests) == 3
        states = [task['state'] for task in rewrite.tasks.list(project) if task['kind'] == 'rewrite']
        assert states.count('cancelled') == 1


def test_a_project_with_no_hidden_rows_gets_no_action_and_its_write_preview_is_refused(tmp_path):
    from tests.projects.support import Editor, v2_app
    fixture, _operation = run(tmp_path / 'import')
    workspace = fixture.current()
    operations = [operation.model_copy(update={'other_lines': [rows for rows in operation.other_lines if rows.reason != 'hidden']})
                  for operation in workspace.project.template_operations]
    workspace = workspace.model_copy(update={'project': workspace.project.model_copy(update={'template_operations': operations})})
    with v2_app(tmp_path / 'app', [(workspace, fixture.originals)], content_provider=Writing()) as (client, _application):
        project = workspace.project_id
        editor = Editor(client, project)
        offered = client.get('/v2/projects/' + project + '/reword/blocks').json()
        assert offered['write'] == [] and offered['blockIds']
        summary = next(block for block in offered['blockIds'] if offered['rules'][block].startswith('О себе'))
        editor.refused('post', '/reword/preview', {'editorToken': editor.token, 'requestId': 'write-no', 'blockId': summary,
            'instruction': 'Коротко.', 'mode': 'write'}, 422)


@pytest.mark.parametrize('instruction, state, reason', [('Коротко.', 'changed', None), ('Коротко. [отказ]', 'refused', 'name'),
                                                        ('[пусто]', 'refused', 'empty')])
def test_the_stand_answers_the_write_request_with_a_text_code_keeps_or_refuses_on_request(imported, instruction, state, reason):
    from argparse import Namespace
    from resume_api.providers.dynamic_result import dynamic_result
    from tools import serve_synthetic
    source = source_of(imported)
    request = Namespace(text=W.write_request(source, instruction), result_type=dynamic_result(P.rewrite_schema()),
                        policy=Namespace(model='synthetic'))
    result = serve_synthetic.ScriptedContent().write_again(request, None)
    value, _told = W.write_value(source, result.value.payload)
    assert (value.state, value.reason) == (state, reason)


# The language check (stop 5 addition): one rule by script for every model, the editor's call only.
ENGLISH_LINES = ['Maya Collins', 'Data Engineer', 'Python, Apache Airflow, Spark, dbt, BigQuery',
                 'Harbor Analytics Ltd', 'Built daily ingestion pipelines in Airflow for retail data sources',
                 'Moved transformation jobs from stored procedures to dbt']
ENGLISH_TEXT = 'Data Engineer who builds ingestion pipelines in Airflow and moves transformation jobs to dbt.'
RUSSIAN_FOR_ENGLISH = 'Инженер данных, строю конвейеры загрузки в Airflow и переношу преобразования в dbt.'


def english(tmp_ref='S'):
    from types import SimpleNamespace
    from packages.resume_core.repository.block_reword import Target
    lines = [SimpleNamespace(ref=tmp_ref + str(number), text=text) for number, text in enumerate(ENGLISH_LINES, 1)]
    return W.WriteSource('ABOUT', Target('V1', 'record-1', 'text', 'text', 'Data engineer.'), lines)


@pytest.mark.parametrize('reply, state, reason', [
    ({'text': GOOD, 'lines': ['S2']}, 'changed', None),
    # Technology names in Latin letters inside a Russian text are normal.
    ({'text': 'Руководитель группы разработки: Java, Spring Boot, PostgreSQL, Kafka, Kubernetes.', 'lines': ['S2', 'S6']},
     'changed', None),
    ({'text': 'Development team lead in billing, working with Java, Spring Boot, PostgreSQL and Kafka.', 'lines': ['S2']},
     'refused', 'language'),
])
def test_a_written_text_in_the_script_of_a_russian_cv_is_kept_and_one_in_latin_letters_is_refused(imported, reply, state, reason):
    value, told = W.write_value(source_of(imported), reply)
    assert (value.state, value.reason) == (state, reason)
    if reason:
        assert told == ('it is written in Latin letters, but the lines are in Cyrillic letters: write it in the language '
                        'of the lines.')


def test_an_english_cv_takes_an_english_text_and_refuses_a_russian_one_with_a_reason_the_model_can_act_on():
    kept, _told = W.write_value(english(), {'text': ENGLISH_TEXT, 'lines': ['S2', 'S5']})
    assert kept.state == 'changed'
    refused, told = W.write_value(english(), {'text': RUSSIAN_FOR_ENGLISH, 'lines': ['S2', 'S5']})
    assert (refused.state, refused.reason) == ('refused', 'language')
    assert 'Cyrillic letters, but the lines are in Latin letters' in told


def test_too_few_letters_to_decide_give_no_refusal():
    from packages.resume_core.importing.lite.scheme import script, written_check
    assert script('Java, SQL.') is None and script('') is None
    assert written_check('Python, Spark, dbt.', ['S1'], ENGLISH_LINES, language=True)[0] is None
    # Lines with too few letters: a Russian text is not refused for them.
    assert written_check('строю конвейеры загрузки данных в Airflow и dbt.', ['S1'], ['Airflow', 'dbt'], language=True)[0] is None
    # Between the two bounds (a few Cyrillic words in a Latin text) the script is undecided.
    assert script('Data Engineer at Harbor Analytics, Лиссабон') is None


def test_the_import_does_not_check_the_language():
    from packages.resume_core.importing.lite.scheme import written_check
    assert written_check(RUSSIAN_FOR_ENGLISH, ['S1'], ENGLISH_LINES)[0] is None
    assert written_check(RUSSIAN_FOR_ENGLISH, ['S1'], ENGLISH_LINES, language=True)[0] == 'another language'


def test_a_text_in_another_language_gets_the_second_call_and_one_refused_twice_has_no_apply(tmp_path):
    wrong = {'text': 'Development team lead in billing, working with Java, Spring Boot and Kafka.', 'lines': ['S2']}
    provider = Writing(wrong, {'text': GOOD, 'lines': ['S2', 'S8', 'S13']}, wrong, wrong)
    workspace, context, Editor = app(tmp_path, provider)
    with context as (client, _application):
        project = workspace.project_id
        editor = Editor(client, project)
        block_id = summary(client.get('/v2/projects/' + project + '/reword/blocks').json())
        body = {'editorToken': editor.token, 'blockId': block_id, 'instruction': 'Коротко.', 'mode': 'write'}
        again = editor.call('post', '/reword/preview', {**body, 'requestId': 'write-language-1'})
        second = json.loads(provider.requests[1].text)
        second = second.get('payload', second)
        assert 'Latin letters, but the lines are in Cyrillic letters' in second['refused']
        assert [(value['state'], value['after']) for value in again['values']] == [('changed', GOOD)]
        twice = editor.call('post', '/reword/preview', {**body, 'requestId': 'write-language-2'})
        assert len(provider.requests) == 4
        assert [(value['state'], value['reason']) for value in twice['values']] == [('refused', 'language')]
