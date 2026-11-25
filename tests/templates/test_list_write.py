"""«Написать заново по резюме» for the list «Ключевые достижения» (F6b, D181): what is sent, what code keeps of each
item, and the Apply that replaces the list as one action. The document is a lite import of an invented CV whose
contact line holds a phone number (test_block_write.run). Cases L1–L14 of the brief."""

import json

import pytest

from packages.resume_core.repository import block_write as W
from tests.templates.test_block_write import CONTACT, Writing, imported, run  # noqa: F401 (imported: a fixture)

ROLE = 'Руковожу группой разработчиков биллинга и планирую кварталы'     # «планирую кварталы» is not in S12
GATEWAY = 'Писала интеграцию с платёжным шлюзом'                          # S23 word for word
CABINET = 'Разрабатывала модули личного кабинета абонента'                # S22 word for word
TYPED = 'Свой пункт про наставничество'


def section_of(workspace):
    return next(block for region in workspace.project.document.regions for block in region.blocks
                if block.type == 'section' and getattr(block.presentation, 'view_key', None) == 'career_highlights')


def texts(section):
    return [''.join(getattr(span, 'text', '') for span in child.content) for child in section.children]


def with_typed_bullet(workspace):
    """The list with a bullet the user typed (a literal, no record) after its second item."""
    value = workspace.model_copy(deep=True)
    section = section_of(value)
    form = section.children[0].model_dump(mode='json', by_alias=True)
    styles = form['content'][0]['styles']
    typed = type(section.children[0]).model_validate({**form, 'id': 'block-typed-1',
        'content': [{'type': 'text', 'text': TYPED, 'styles': styles}]})
    section.children.insert(2, typed)
    return value


def corrected(workspace, index):
    """The list's item at `index` as the user's own value (they typed in it)."""
    value = workspace.model_copy(deep=True)
    record_id = section_of(value).children[index].content[0].record_id
    record = next(item for item in value.project.facts.extensions if item.id == record_id)
    cell = record.cells[0]
    record.cells[0] = cell.model_copy(update={'state': 'human_raw', 'origin': 'human', 'user_corrected': True,
        'typed_value': None, 'admission_receipt_ids': []})
    return value


class Stand:
    def __init__(self, tmp_path, provider, change=None):
        from tests.projects.support import Editor, v2_app
        fixture, _operation = run(tmp_path / 'import')
        self.workspace = change(fixture.current()) if change else fixture.current()
        self.provider = provider
        self.context = v2_app(tmp_path / 'app', [(self.workspace, fixture.originals)], content_provider=provider)
        self.Editor = Editor

    def __enter__(self):
        self.client, self.application = self.context.__enter__()
        self.project = self.workspace.project_id
        self.editor = self.Editor(self.client, self.project)
        self.block = section_of(self.workspace).id
        return self

    def __exit__(self, *args):
        return self.context.__exit__(*args)

    def preview(self, identifier='list-1', instruction='Достижения: эффект.'):
        return self.editor.call('post', '/reword/preview', {'editorToken': self.editor.token, 'requestId': identifier,
            'blockId': self.block, 'instruction': instruction, 'mode': 'write'})

    def body(self, shown, removed, added, identifier='list-apply', touched=None):
        return {'editorToken': self.editor.token, 'clientMutationId': identifier, 'blockId': self.block,
            'touched': shown['touched'] if touched is None else touched, 'removed': removed, 'added': added}

    def apply(self, shown, removed, added, identifier='list-apply'):
        return self.editor.adopt(self.editor.call('post', '/reword/apply', self.body(shown, removed, added, identifier)))

    def section(self):
        return section_of(self.editor.workspace())

    def asked(self, number=0):
        value = json.loads(self.provider.requests[number].text)
        return value.get('payload', value)

    def added(self):
        return self.client.get('/v2/projects/' + self.project + '/source-diff').json()['added']


def items(*values):
    return {'items': [{'text': text, 'lines': lines} for text, lines in values]}


def take(shown, *, edited=(), skip=()):
    return [{'text': item['text'] + (' сама' if item['id'] in edited else ''), 'lines': item['lines'],
             'edited': item['id'] in edited} for item in shown['added'] if item['state'] == 'added' and item['id'] not in skip]


def test_l1_the_whole_list_is_replaced_in_one_action_and_one_undo_brings_it_back_exactly(tmp_path):
    with Stand(tmp_path, Writing(items((ROLE, ['S12']), (GATEWAY, ['S23']), (CABINET, ['S22'])))) as stand:
        offered = stand.client.get('/v2/projects/' + stand.project + '/reword/blocks').json()
        assert stand.block in offered['write']
        shown = stand.preview()
        assert shown['shape'] == 'items' and [value['state'] for value in shown['values']] == ['present'] * 5
        assert [item['state'] for item in shown['added']] == ['added'] * 3 and stand.block in shown['touched']
        asked = stand.asked()
        assert asked['present'] == texts(section_of(stand.workspace)) and asked['kept'] == []
        assert asked['request'] == 'Достижения: эффект.' and not {'holds', 'write', 'instructions'} & set(asked)
        assert CONTACT not in json.dumps(asked, ensure_ascii=False)
        # The live round: a rule against copying `present` made both models leave out the weightiest results.
        assert any('leave out no weighty result' in rule for rule in asked['rules']) and asked['most'] == 5
        before = stand.editor.workspace()
        applied = stand.apply(shown, [value['recordId'] for value in shown['values']], take(shown))
        assert texts(stand.section()) == [ROLE, GATEWAY, CABINET]
        kinds = [record for record in stand.editor.workspace().project.facts.extensions
                 if record.semantic_type == 'foldcv:career_highlights' and record.active]
        assert len(kinds) == 3 and all(record.cells[0].state == 'human_raw' for record in kinds)
        stand.editor.step('undo', 'list-undo', expected=applied['history']['undo']['actionId'])
        back = stand.editor.workspace()
        assert section_of(back).model_dump(mode='json') == section_of(before).model_dump(mode='json')
        assert back.project.facts.extensions == before.project.facts.extensions


def test_l2_a_kept_item_stays_in_place_and_an_unticked_new_item_does_not_come(tmp_path):
    with Stand(tmp_path, Writing(items((ROLE, ['S12']), (GATEWAY, ['S23']), (CABINET, ['S22'])))) as stand:
        shown = stand.preview()
        old = texts(section_of(stand.workspace))
        removed = [value['recordId'] for index, value in enumerate(shown['values']) if index != 1]
        stand.apply(shown, removed, take(shown, skip=('N3',)))
        assert texts(stand.section()) == [ROLE, GATEWAY, old[1]]


def test_l3_a_typed_bullet_stays_in_place_the_model_sees_it_and_a_repeat_of_it_is_refused(tmp_path):
    reply = items((ROLE, ['S12']), (TYPED, ['S19']))
    with Stand(tmp_path, Writing(reply), with_typed_bullet) as stand:
        shown = stand.preview()
        assert stand.asked()['kept'] == [TYPED] and len(shown['values']) == 5
        assert [(item['state'], item['reason']) for item in shown['added']] == [('added', None), ('refused', 'duplicate')]
        stand.apply(shown, [value['recordId'] for value in shown['values']], take(shown))
        assert texts(stand.section()) == [ROLE, TYPED]


def test_l4_an_item_the_user_corrected_starts_with_keep_on(tmp_path):
    with Stand(tmp_path, Writing(items((ROLE, ['S12']))), lambda workspace: corrected(workspace, 2)) as stand:
        shown = stand.preview()
        assert [value.get('keep', False) for value in shown['values']] == [False, False, True, False, False]


@pytest.mark.parametrize('reply, expected', [
    (items((ROLE, ['S12']), ('Сократила расходы на 45 процентов', ['S14']), (GATEWAY, ['S4']),
           ('Built the billing service on Kafka', ['S17'])),
     [('added', None), ('refused', 'number'), ('refused', 'lines'), ('refused', 'language')]),
    (items((GATEWAY, ['S23']), (GATEWAY.upper(), ['S23'])), [('added', None), ('refused', 'duplicate')]),
])
def test_l5_items_are_refused_alone_by_the_imports_checks_the_language_and_repeats(imported, reply, expected):
    workspace, _operation, hidden, _block = imported
    source = W.list_source(workspace, section_of(workspace).id, hidden)
    present, added = W.list_values(source, reply)
    assert [(item.state, item.reason) for item in added] == expected
    assert [value.state for value in present] == ['present'] * 5


def test_l6_l7_no_item_kept_has_nothing_to_apply_and_an_apply_that_empties_the_list_is_refused(tmp_path):
    with Stand(tmp_path, Writing({'items': []}, items(('Built the billing service on Kafka', ['S17'])))) as stand:
        empty = stand.preview('list-empty')
        assert empty['added'] == []
        refused = stand.preview('list-refused')
        assert [item['state'] for item in refused['added']] == ['refused']
        everything = [value['recordId'] for value in refused['values']]
        stand.editor.refused('post', '/reword/apply', stand.body(refused, everything, []), 422)
        stand.editor.refused('post', '/reword/apply', stand.body(refused, [], [], 'list-nothing'), 422)


def test_l8_a_list_changed_after_the_preview_is_refused_as_stale_by_its_structure_too(tmp_path):
    with Stand(tmp_path, Writing(items((ROLE, ['S12'])))) as stand:
        shown = stand.preview()
        last, first = shown['values'][-1]['recordId'], shown['values'][0]['recordId']
        stand.apply(shown, [last], [], 'list-first')
        # Only the list block changed for the second Apply: its first item's record is the same.
        touched = {stand.block: shown['touched'][stand.block], first: shown['touched'][first]}
        stale = stand.editor.refused('post', '/reword/apply', stand.body(shown, [first], [], 'list-second', touched), 409)
        assert 'ASSISTANT_PROPOSAL_STALE' in json.dumps(stale) and stand.block in json.dumps(stale)
        # An Apply whose hashes do not name the list block is refused.
        stand.editor.refused('post', '/reword/apply', stand.body(shown, [first], [], 'list-third',
            {first: shown['touched'][first]}), 422)


def test_l9_l10_a_new_item_is_green_until_accepted_and_one_edited_in_the_preview_is_the_users(tmp_path):
    with Stand(tmp_path, Writing(items((ROLE, ['S12']), (CABINET, ['S22'])))) as stand:
        shown = stand.preview()
        stand.apply(shown, [value['recordId'] for value in shown['values']], take(shown, edited=('N2',)))
        records = {record.cells[0].raw_input: record.cells[0].id for record in stand.editor.workspace().project.facts.extensions
                   if record.semantic_type == 'foldcv:career_highlights' and record.active}
        role, cabinet = records[ROLE], records[CABINET + ' сама']
        added = stand.added()
        assert added[role] == ['и', 'планирую', 'кварталы'] and cabinet not in added
        stand.editor.adopt(stand.editor.call('post', '/accept', {'editorToken': stand.editor.token,
            'clientMutationId': 'accept-1', 'cellId': role}))
        assert role not in stand.added()
        stand.editor.step('undo', 'undo-accept')
        assert stand.added()[role] == ['и', 'планирую', 'кварталы']


def test_l11_removed_items_leave_no_empty_bullet_and_no_record(tmp_path):
    with Stand(tmp_path, Writing(items((ROLE, ['S12'])))) as stand:
        shown = stand.preview()
        removed = [value['recordId'] for value in shown['values']]
        stand.apply(shown, removed, take(shown))
        section = stand.section()
        assert all(texts(section)) and len(section.children) == 1
        active = {record.id for record in stand.editor.workspace().project.facts.extensions if record.active}
        assert not set(removed) & active


def test_l12_a_project_with_no_hidden_rows_has_no_list_action(tmp_path):
    def bare(workspace):
        operations = [operation.model_copy(update={'other_lines': [rows for rows in operation.other_lines
                      if rows.reason != 'hidden']}) for operation in workspace.project.template_operations]
        return workspace.model_copy(update={'project': workspace.project.model_copy(update={'template_operations': operations})})
    with Stand(tmp_path, Writing(), bare) as stand:
        assert stand.client.get('/v2/projects/' + stand.project + '/reword/blocks').json()['write'] == []
        stand.editor.refused('post', '/reword/preview', {'editorToken': stand.editor.token, 'requestId': 'list-no',
            'blockId': stand.block, 'instruction': 'Коротко.', 'mode': 'write'}, 422)


def test_l14_the_reply_holds_at_most_five_items_or_the_present_count_up_to_eight(imported):
    workspace, _operation, hidden, _block = imported
    source = W.list_source(workspace, section_of(workspace).id, hidden)
    # The request names the limit; the schema has none, so a reply with more items is not lost: code keeps the first.
    assert W.list_most(source) == 5 and 'maxItems' not in W.list_schema(source)['properties']['items']
    assert json.loads(W.list_request(source, 'Коротко.')).get('most') == 5
    many = items(*[(GATEWAY + ' ' + str(number), ['S23']) for number in range(9)])
    _present, added = W.list_values(source, many)
    assert len(added) == 5
    source.items = source.items * 2
    assert W.list_most(source) == 8


@pytest.mark.parametrize('instruction, states', [('Коротко.', ['added'] * 3), ('Коротко. [отказ]', ['added'] * 3 + ['refused']),
                                                ('[пусто]', [])])
def test_the_stand_answers_the_list_request(imported, instruction, states):
    from argparse import Namespace
    from resume_api.providers.dynamic_result import dynamic_result
    from tools import serve_synthetic
    workspace, _operation, hidden, _block = imported
    source = W.list_source(workspace, section_of(workspace).id, hidden)
    request = Namespace(text=W.list_request(source, instruction), result_type=dynamic_result(W.list_schema(source)),
                        policy=Namespace(model='synthetic'))
    result = serve_synthetic.ScriptedContent().write_again(request, None)
    _present, added = W.list_values(source, result.value.payload)
    assert [item.state for item in added] == states
