"""What the document says beyond the original: every shown field is compared with the source lines its value rests
on, whoever gave it its text. The document is a lite import of an invented CV."""

import pytest

from packages.resume_core.fields import field_key
from packages.resume_core.repository.source_diff import additions, beyond, removals
from tests.templates.test_block_reword import Rewording, card
from tests.templates.test_lite_import import Unwritten, lite_run


def test_a_source_span_is_read_by_code_points():
    from types import SimpleNamespace
    from packages.resume_core.repository.source_diff import source_lines
    # A span counts code points (sources.source_slice): a character outside the basic plane is one, not two.
    record = SimpleNamespace(evidence=[SimpleNamespace(unit_id='unit', start=0, end=3), SimpleNamespace(unit_id='unit', start=2, end=9)])
    assert source_lines(None, record, False, 'value', {'unit': 'a😀b'}) == ['a😀b']


def test_the_words_a_text_has_and_its_lines_lack_are_found_whole_case_and_punctuation_aside():
    assert beyond('5 лет', ['Java — около 5 лет, Spring Boot']) == []
    assert beyond('Spring boot', ['Java — около 5 лет, Spring Boot']) == []
    assert beyond('Ещё раз', ['еще раз.']) == []
    # A word the lines do not state is given once, as the text writes it; a part of a longer word is no match.
    assert beyond('5 years, 5 years', ['Java — около 5 лет']) == ['years']
    assert beyond('Kafka и отчёт', ['kafka, отчёты']) == ['и', 'отчёт']
    # The way a word is set apart is form: one word for two and two for one state the same.
    assert beyond('Node.js, WinForms', ['nodejs и Win Forms']) == []


@pytest.fixture(scope='module')
def imported(tmp_path_factory):
    return lite_run(tmp_path_factory.mktemp('diff'), 'promotions', calls=Unwritten('promotions'))[0]


def test_a_copied_cv_differs_only_where_the_import_wrote_text_of_its_own(imported):
    workspace = imported.current()
    found = additions(workspace)
    # Every value the import copied states only words of its lines; the summary it wrote has words of its own.
    assert len(found) == 1 and 'специализируюсь' in next(iter(found.values()))
    # The key is the cell id the editor has on the field: an extension's cell has an id of its own.
    from packages.resume_core.editing.template_preparation_text import _fields
    from packages.resume_core.fields import inline_groups
    cells = {span.cell_id for block in workspace.project.document.blocks() for _key, content in inline_groups(block)
             for span, _start, _end in _fields(content)}
    assert set(found) <= cells and not next(iter(found)).startswith('["fact"')
    # Of the lines its values rest on, the document leaves out two words of the skills line and nothing else.
    assert removals(workspace) == [{'text': 'Java, Spring Boot, PostgreSQL, Kafka, Kubernetes, управление командой',
                                    'words': ['командой', 'управление']}]


def test_a_value_the_user_changed_is_compared_too_and_the_route_gives_its_new_words(tmp_path):
    from tests.projects.support import Editor, v2_app
    fixture, _operation = lite_run(tmp_path / 'import', 'promotions', calls=Unwritten('promotions'))
    workspace = fixture.current()
    block_id, source = card(workspace, 'Перевела расчёты с Oracle на PostgreSQL')
    target = source.targets[1]
    with v2_app(tmp_path / 'app', [(workspace, fixture.originals)], content_provider=Rewording()) as (client, _application):
        project = workspace.project_id
        editor = Editor(client, project)
        cell = field_key(target.record_id, target.field)     # a claim: a builtin record, named by record and field
        before = client.get('/v2/projects/' + project + '/source-diff').json()
        assert cell not in before['added'] and not [row for row in before['removed'] if 'Oracle' in row['text']]
        shown = editor.call('post', '/reword/preview', {'editorToken': editor.token, 'requestId': 'reword-1', 'blockId': block_id,
            'instruction': 'Задачи — существительным'})
        editor.adopt(editor.call('post', '/reword/apply', {'editorToken': editor.token, 'clientMutationId': 'apply-1',
            'blockId': block_id, 'touched': shown['touched'],
            'changes': [{'recordId': target.record_id, 'field': target.field, 'value': shown['values'][1]['after']}]}))
        # The value keeps its source line, so its new words show as beyond the original.
        after = client.get('/v2/projects/' + project + '/source-diff').json()
        assert after['added'][cell] == ['Перевод', 'расчётов']
        # And the words of that line the document no longer shows are the line's removals.
        assert {'text': 'Перевела расчёты с Oracle на PostgreSQL', 'words': ['перевела', 'расчеты']} in after['removed']
