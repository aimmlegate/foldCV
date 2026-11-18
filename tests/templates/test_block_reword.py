"""A block reworded on the user's request: what is read from the block, what the model is told, what code keeps of a
reply, and that only the user's Apply changes a fact. The document is a lite import of an invented CV."""

import json

import pytest

from packages.resume_core.repository import block_reword as R
from packages.resume_core.repository.assistant_compiler import compile_ops
from resume_api.projects.service import response_for_workspace
from tests.templates.test_lite_import import Unwritten, lite_run


@pytest.fixture(scope='module')
def workspace(tmp_path_factory):
    fixture, _operation = lite_run(tmp_path_factory.mktemp('reword'), 'promotions', calls=Unwritten('promotions'))
    return fixture.current()


def sources(workspace):
    return [R.reword_source(workspace, block_id) for block_id in R.rewordable(workspace)]


def card(workspace, text):
    """The id and the source of the document block that holds a value with this text."""
    for block_id in R.rewordable(workspace):
        source = R.reword_source(workspace, block_id)
        if any(target.text == text for target in source.targets):
            return block_id, source
    raise AssertionError(text)


def test_the_blocks_to_reword_are_the_summary_and_each_job_with_only_the_templates_rewrite_fields(workspace):
    found = sources(workspace)
    assert [source.block.id for source in found] == ['summary', 'projects', 'projects', 'projects', 'projects']
    kinds = {target.kind for source in found for target in source.targets}
    assert kinds == {'text', 'tasks', 'results', 'role_details.scope'}
    # An employer, a role, a period and a technology are context, never a value to reword.
    _block, source = card(workspace, 'Перевела расчёты с Oracle на PostgreSQL')
    assert {'АО «Северная линия»', 'Oracle', 'Kafka'} <= set(source.context)
    assert not {'АО «Северная линия»', 'Oracle'} & {target.text for target in source.targets}
    # A value comes with the source line it rests on.
    assert all(target.source for target in source.targets)
    # A block the template gives no rewrite field is not offered.
    other = next(block.id for region in workspace.project.document.regions for block in region.blocks
                 if getattr(block.presentation, 'view_key', None) == 'education')
    assert R.reword_source(workspace, other) is None


def test_the_request_tells_the_model_only_what_the_user_saw_and_takes_a_reply_of_the_listed_values_only(workspace):
    from packages.resume_core.importing.lite.rules import BLOCKS, STYLE
    block_id, source = card(workspace, 'Перевела расчёты с Oracle на PostgreSQL')
    # Each block is offered with the unified rules of its kind: the text the panel puts into the request field.
    offered = R.rewordable(workspace)
    assert offered[block_id] == '\n'.join([*BLOCKS['projects'], *STYLE])
    summary = next(key for key in offered if R.reword_source(workspace, key).block.id == 'summary')
    assert offered[summary].startswith(BLOCKS['summary'][0]) and BLOCKS['projects'][0] not in offered[summary]
    payload = json.loads(R.reword_request(source, '  Сократи  текст \n\n Без вводных слов'))
    payload = payload.get('payload', payload)
    assert payload['request'] == 'Сократи текст\nБез вводных слов'
    assert [value['id'] for value in payload['values']] == ['V1', 'V2', 'V3']
    # No instruction the user did not see: nothing of the template's own prompts is sent.
    definition = workspace.project.template_package.definition
    assert 'instructions' not in payload
    assert not [rule for rule in [*definition.model.rewrite, *source.block.rewrite.instructions] if rule in json.dumps(payload, ensure_ascii=False)]
    schema = R.reword_schema(source.targets)
    item = schema['properties']['values']
    assert item['minItems'] == item['maxItems'] == 3
    assert item['items']['properties']['id']['enum'] == ['V1', 'V2', 'V3'] and set(item['items']['properties']) == {'id', 'text'}


def test_a_block_the_import_wrote_as_a_list_is_offered_with_its_items_as_values(tmp_path):
    fixture, _operation = lite_run(tmp_path, 'promotions')
    written = fixture.current()
    blocks = [R.reword_source(written, block_id) for block_id in R.rewordable(written)]
    highlights = next(source for source in blocks if source.block.id == 'career_highlights')
    assert {target.kind for target in highlights.targets} == {'items'} and len(highlights.targets) >= 2
    assert all(target.source for target in highlights.targets)


def test_code_keeps_a_rewording_and_refuses_a_new_number_a_new_name_and_a_page_of_text(workspace):
    _block, source = card(workspace, 'Перевела расчёты с Oracle на PostgreSQL')
    first, second, third = source.targets
    values = R.reword_values(source, {'values': [
        {'id': first.id, 'text': 'Проектирование сервиса тарификации на Kafka'},
        {'id': second.id, 'text': 'Перевод расчётов с Oracle на PostgreSQL 14 и Redis'},
        {'id': third.id, 'text': third.text}]})
    assert [(value.state, value.reason) for value in values] == [('changed', None), ('refused', 'number'), ('same', None)]
    assert values[1].words == ['14']
    named = R.reword_values(source, {'values': [{'id': second.id, 'text': 'Перевод расчётов с Oracle на PostgreSQL и Redis'}]})
    assert (named[1].state, named[1].reason, named[1].words) == ('refused', 'name', ['redis'])
    # A technology the catalog knows is a name however it is written.
    lower = R.reword_values(source, {'values': [{'id': second.id, 'text': 'Перевод расчётов с Oracle на PostgreSQL и redis'}]})
    assert (lower[1].state, lower[1].reason, lower[1].words) == ('refused', 'name', ['redis'])
    long = R.reword_values(source, {'values': [{'id': second.id, 'text': 'Перевод расчётов ' * 40}]})
    assert (long[1].state, long[1].reason) == ('refused', 'long')
    # A value the reply leaves out stays as it is; an id the block does not have is ignored.
    assert [value.state for value in R.reword_values(source, {'values': [{'id': 'V9', 'text': 'Другое'}]})] == ['same'] * 3


def test_apply_changes_the_fact_as_the_users_own_value_and_keeps_its_source_line(workspace):
    block_id, source = card(workspace, 'Перевела расчёты с Oracle на PostgreSQL')
    target = source.targets[1]
    ops = R.reword_ops(workspace, block_id, [R.RewordChange(recordId=target.record_id, field=target.field,
        value='Перевод расчётов с Oracle на PostgreSQL')])
    after, _created = compile_ops(workspace, ops, action_id='reword_test', occupied=set(), response_for=response_for_workspace)
    before = next(record for record in workspace.project.facts.records if record.id == target.record_id)
    record = next(record for record in after.project.facts.records if record.id == target.record_id)
    assert record.value.value == 'Перевод расчётов с Oracle на PostgreSQL' and record.user_corrected
    assert record.evidence == before.evidence and not before.user_corrected
    # The page shows the new text; the other values of the job are as they were.
    _block, shown = card(after, 'Перевод расчётов с Oracle на PostgreSQL')
    assert [value.text for value in shown.targets] == [source.targets[0].text, 'Перевод расчётов с Oracle на PostgreSQL',
        source.targets[2].text]


def test_apply_refuses_a_change_of_a_field_the_template_does_not_let_a_model_reword(workspace):
    block_id, source = card(workspace, 'Перевела расчёты с Oracle на PostgreSQL')
    job = next(record for record in workspace.project.facts.records if record.kind == 'employment')
    with pytest.raises(ValueError):
        R.reword_ops(workspace, block_id, [R.RewordChange(recordId=job.id, field='employer', value='ООО «Другое»')])
    # A value of another block is refused too.
    _other, summary = card(workspace, sources(workspace)[0].targets[0].text)
    with pytest.raises(ValueError):
        R.reword_ops(workspace, block_id, [R.RewordChange(recordId=summary.targets[0].record_id, field='text', value='Текст')])
    with pytest.raises(ValueError):
        R.reword_ops(workspace, block_id, [])


class Rewording:
    """A provider that rewords the second value of a block and returns the others as they are."""

    def __init__(self):
        self.requests = []

    def generate(self, request, _files, _cancel):
        from resume_api.providers.content import ContentResult, ReportedUsage
        from resume_api.providers.dynamic_result import PayloadEnvelope
        self.requests.append(request)
        asked = json.loads(request.text)['values']
        reply = {'values': [{'id': value['id'], 'text': 'Перевод расчётов с Oracle на PostgreSQL' if index == 1 else value['text']}
                            for index, value in enumerate(asked)]}
        return ContentResult(PayloadEnvelope(payload=reply), ReportedUsage(), 'fixture', request.policy.model, .01, 1)


def test_the_routes_preview_without_a_write_and_apply_as_one_action_that_undo_takes_back(tmp_path):
    from tests.projects.support import Editor, v2_app
    fixture, _operation = lite_run(tmp_path / 'import', 'promotions', calls=Unwritten('promotions'))
    imported, provider = fixture.current(), Rewording()
    block_id, source = card(imported, 'Перевела расчёты с Oracle на PostgreSQL')
    target = source.targets[1]
    with v2_app(tmp_path / 'app', [(imported, fixture.originals)], content_provider=provider) as (client, application):
        project = imported.project_id
        editor = Editor(client, project)
        offered = client.get('/v2/projects/' + project + '/reword/blocks').json()
        assert block_id in offered['blockIds'] and offered['rules'][block_id]
        # A preview with no request is refused: the model is never asked by rules the user did not see.
        editor.refused('post', '/reword/preview', {'editorToken': editor.token, 'requestId': 'reword-0', 'blockId': block_id,
            'instruction': '  '}, 422)
        before = application.state.projects.repository.read(project)
        shown = editor.call('post', '/reword/preview', {'editorToken': editor.token, 'requestId': 'reword-1', 'blockId': block_id,
            'instruction': 'Сократи'})
        assert json.loads(provider.requests[0].text)['request'] == 'Сократи'
        assert [value['state'] for value in shown['values']] == ['same', 'changed', 'same']
        assert shown['values'][1]['after'] == 'Перевод расчётов с Oracle на PostgreSQL'
        # The preview is one model call and writes nothing.
        assert len(provider.requests) == 1 and application.state.projects.repository.read(project) == before
        body = {'editorToken': editor.token, 'clientMutationId': 'reword-apply-1', 'blockId': block_id, 'touched': shown['touched'],
            'changes': [{'recordId': target.record_id, 'field': target.field, 'value': shown['values'][1]['after']}]}
        # A change of a field outside the block's rewrite fields is refused whatever the request says.
        job = next(record for record in imported.project.facts.records if record.kind == 'employment')
        editor.refused('post', '/reword/apply', {**body, 'clientMutationId': 'reword-apply-0',
            'changes': [{'recordId': job.id, 'field': 'employer', 'value': 'ООО «Другое»'}]}, 422)
        # An Apply that sends no hash of a record it changes is refused: the stale check reads only what was sent.
        editor.refused('post', '/reword/apply', {**body, 'clientMutationId': 'reword-apply-00', 'touched': {}}, 422)
        applied = editor.adopt(editor.call('post', '/reword/apply', body))
        record = next(value for value in applied['response']['workspace']['project']['facts']['records'] if value['id'] == target.record_id)
        assert record['value']['value'] == 'Перевод расчётов с Oracle на PostgreSQL' and record['userCorrected']
        # The same preview applied again is stale: its record changed since.
        stale = editor.refused('post', '/reword/apply', {**body, 'clientMutationId': 'reword-apply-2'}, 409)
        assert 'ASSISTANT_PROPOSAL_STALE' in json.dumps(stale)
        # One undo takes the Apply back.
        undone = editor.step('undo', 'reword-undo-1', expected=applied['history']['undo']['actionId'])
        record = next(value for value in undone['response']['workspace']['project']['facts']['records'] if value['id'] == target.record_id)
        assert record['value']['value'] == 'Перевела расчёты с Oracle на PostgreSQL'
