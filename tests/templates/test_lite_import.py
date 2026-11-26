"""The lite import through the pipeline: its scheme reads the CV with its own calls, and code answers every request
the pipeline would send to a model. The scheme's calls are replayed from one live run on an invented CV."""

import asyncio
import json
from pathlib import Path

import pytest

from packages.resume_core.extraction.parser import extract
from packages.resume_core.project_limits import finalization_seconds, import_seconds
from packages.resume_core.sources import canonical_source
from packages.resume_core.templates.operations import derive_task
from packages.resume_core.import_failure import TemplateImportFailure
from resume_api.importer import lite_import
from resume_api.projects.errors import ProjectFailure
from resume_api.providers.content import ContentFailure, ReportedUsage
from tests.templates.generic_fixtures import generic_package, two_column_1_6
from tests.templates.scripted_template_provider import ScriptedTemplateProvider
from tests.templates.template_runtime_fixtures import ControlledTransport, EmploymentFixture
from tests.templates.test_template_import_app import app_client, operation_of, saved, upload

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'synthetic' / 'lite'


class StoredCalls:
    """The scheme's calls answered from a stored run, by kind and block, in call order."""
    envelope = False     # the run was Claude's: its replies have no {"payload"} envelope

    def __init__(self, name, fail=()):
        self.rows, self.replies, self.fail = [], {}, set(fail)
        for call in json.loads((FIXTURES / (name + '.json')).read_text()):
            self.replies.setdefault((call['kind'], call['block']), []).append(call)

    def call(self, kind, block, _prompt, _schema):
        held = self.replies.get((kind, block)) or []
        if not held or kind in self.fail:
            row = {'kind': kind, 'block': block, 'errorCode': 'INVALID_RESULT', 'usage': None}
            self.rows.append(row)
            return None, row
        call = held.pop(0)
        row = {'kind': kind, 'block': block, 'errorCode': None, 'usage': ReportedUsage(*call['usage'], True)}
        self.rows.append(row)
        return call['reply'], row


class LiteTransport(ControlledTransport):
    """The controlled transport with the two things a lite import asks of a transport."""

    def __init__(self, fixture, stored):
        super().__init__(fixture)
        self.stored, self.model_calls = stored, 0

    def lite_calls(self, _model, _cancel, _remaining, _cap=None):
        return self.stored

    def generate(self, request, cancel):
        lite = lite_import.LITE.get()
        if lite is not None:
            self.calls.append(request.request_value)
            return lite_import.generate(request, lite)
        self.model_calls += 1
        return super().generate(request, cancel)


class Unwritten(StoredCalls):
    """The stored run with no career highlights written: the list repeats lines the jobs show, and a test of what the
    document shows of one line wants that line shown once."""

    def call(self, kind, block, prompt, schema):
        reply, row = super().call(kind, block, prompt, schema)
        if kind == 'write' and reply is not None:
            reply = {**reply, 'career_highlights': {'items': []}}
        return reply, row


def lite_run(tmp_path, name, fail=(), calls=None, lines=None, package=None):
    """lines: {line number: text} replaces lines of the CV as the parser read them; calls: the scheme's calls;
    package: the template, the two-column one when none is given."""
    data = (FIXTURES / (name + '.docx')).read_bytes()
    extracted = extract(data, name + '.docx')
    for number, text in (lines or {}).items():
        extracted.units[number - 1].text = text
    source = canonical_source(extracted)
    fixture = EmploymentFixture(tmp_path, captured=package or generic_package(), src=source, original_bytes=data, cap=80,
                                fallback=False, concurrency=1)
    fixture.transport = LiteTransport(fixture, calls or StoredCalls(name, fail))
    fixture.pipeline = fixture.fresh_pipeline()
    fixture.pipeline.derive = derive_task
    capture = fixture.command.capture
    capture.allow_text_rewrite, capture.policy.lite = False, True
    capture.policy.processing_seconds, capture.policy.finalization_seconds = import_seconds(), finalization_seconds()
    operation = asyncio.run(fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted))
    return fixture, operation


def jobs(fixture):
    return [(record.employer.raw_text, record.role.raw_text) for record in fixture.current().project.facts.records
            if record.kind == 'employment']


def document_text(fixture):
    found = []

    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get('text'), str):
                found.append(value['text'])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(fixture.current().project.model_dump(mode='json', by_alias=True)['document'])
    return ' '.join(found)


@pytest.fixture(scope='module')
def promotions(tmp_path_factory):
    return lite_run(tmp_path_factory.mktemp('promotions'), 'promotions')


@pytest.fixture(scope='module')
def highlights(tmp_path_factory):
    """The same run with «Две колонки» 1.6.0, the last revision with career highlights (D184)."""
    return lite_run(tmp_path_factory.mktemp('highlights'), 'promotions', package=two_column_1_6())


def test_a_lite_import_publishes_the_schemes_result_with_no_model_call_of_the_pipeline(promotions):
    fixture, operation = promotions
    assert operation.state == 'published'
    # Every request of the pipeline was answered by code: extractions and reviews, no repair, no fallback.
    assert fixture.transport.model_calls == 0
    assert {attempt.slot for attempt in operation.attempts} == {'initial', 'review'}
    assert {attempt.outcome for attempt in operation.attempts} == {'completed'}
    assert not [issue for issue in operation.issues if issue.code == 'IMPORT_SOURCE_FALLBACK']
    # Three roles at one employer are three jobs, each with its own role (the narrow question cut the entry).
    assert jobs(fixture) == [('АО «Северная линия»', 'Руководитель группы разработки'),
                             ('АО «Северная линия»', 'Ведущий разработчик'), ('АО «Северная линия»', 'Разработчик'),
                             ('Томский технический лицей', 'Преподаватель курса по Java (по совместительству)')]
    # The record carries the tokens the scheme's own calls spent.
    spent = [row['usage'] for row in fixture.transport.stored.rows]
    assert sum(attempt.usage.input_tokens for attempt in operation.attempts) == sum(usage.input_tokens for usage in spent)
    assert sum(attempt.usage.output_tokens for attempt in operation.attempts) == sum(usage.output_tokens for usage in spent)


def test_a_block_the_cv_has_no_text_for_is_written_from_its_lines_and_marked_as_added(highlights):
    fixture, operation = highlights
    # The CV has no summary and no career highlights. One call beside the others wrote both (the general rule for a
    # block the CV left empty and the template lets a model word), and each shows as written, not as its cited lines.
    assert [(row['kind'], row['block']) for row in fixture.transport.stored.rows].count(('write', 'write')) == 1
    written = StoredCalls('promotions').replies[('write', 'write')][0]['reply']
    assert written['summary']['text'] in document_text(fixture)
    assert all(item['text'] in document_text(fixture) for item in written['career_highlights']['items'])
    notices = [issue for issue in fixture.current().project.import_issues if issue.code == 'IMPORT_TEXT_GENERATED']
    blocks = {task.id: task.block_id for task in operation.tasks}
    assert sorted(blocks[notice.task_id] for notice in notices) == ['career_highlights', 'summary']
    # Each notice stands on its block's own lines, so the editor marks that text as added.
    assert all(notice.state == 'active' and notice.block_ids and notice.message == lite_import.WRITTEN_MESSAGE for notice in notices)
    # What the CV states is still copied word for word.
    assert 'Спроектировала сервис тарификации на Kafka' in document_text(fixture)


@pytest.mark.parametrize('reply, problem', [
    ({'text': None, 'lines': []}, 'no text'),
    ({'text': 'Руководитель группы разработки.', 'lines': ['S900']}, 'no lines'),
    ({'text': 'Руководитель группы разработки, 12 лет в биллинге.', 'lines': ['S2']}, 'a number the CV lacks'),
    ({'text': 'Руководитель группы разрабoтки на Java.', 'lines': ['S2']}, 'a word of two alphabets'),
    # A level, a product or a technology the CV does not write is refused as a new number is.
    ({'text': 'Руководитель группы разработки уровня Senior, работаю с Terraform.', 'lines': ['S2']}, 'a name the CV lacks'),
])
def test_a_written_block_code_refuses_stays_empty(promotions, reply, problem):
    from packages.resume_core.importing.lite.scheme import Import
    calls = StoredCalls('promotions')
    calls.replies[('write', 'write')] = [{'reply': {'summary': reply}, 'usage': [10, 0, 5]}]
    result = Import(promotions[0].current().project.sources, calls, envelope=False, writing={'summary': ['Write it.']}).run()
    assert result.state == 'succeeded' and 'summary' not in result.table and not result.written
    assert {'kind': 'write', 'block': 'summary', 'problem': problem} in result.notes['invalid']
    # A refused text is asked for once more (the stored run has no second reply); no text at all is not.
    asked = [(row['kind'], row['block']) for row in calls.rows].count(('write', 'write'))
    assert asked == (1 if problem == 'no text' else 2)


def test_a_written_list_keeps_the_items_code_takes_and_leaves_the_others_out(promotions):
    from packages.resume_core.importing.lite.scheme import Import
    calls = StoredCalls('promotions')
    calls.replies[('write', 'write')] = [{'usage': [10, 0, 5], 'reply': {'career_highlights': {'items': [
        {'text': 'Провела переход группы на трёхнедельные релизы', 'lines': ['S14']},
        {'text': 'Сократила расходы на 40 %', 'lines': ['S14']},              # a number the CV does not state
        {'text': 'Внедрила Terraform в группе', 'lines': ['S14']},            # a name the CV does not write
        {'text': 'Перевела расчёты на новую базу', 'lines': ['S900']}]}}}]    # no line of the CV to rest on
    result = Import(promotions[0].current().project.sources, calls, envelope=False,
                    writing={'career_highlights': ['Write them.']}).run()
    content, evidence = result.table['career_highlights']
    assert content == {'items': ['Провела переход группы на трёхнедельные релизы']} and list(evidence) == ['/items/0']
    assert result.written == {'career_highlights': ['/items/*']}
    assert sorted(note['problem'] for note in result.notes['invalid']) == ['a name the CV lacks', 'a number the CV lacks', 'no lines']
    # A list item is not asked for again; a list with no item kept leaves the block empty.
    assert [(row['kind'], row['block']) for row in calls.rows].count(('write', 'write')) == 1
    none = StoredCalls('promotions')
    none.replies[('write', 'write')] = [{'usage': [10, 0, 5], 'reply': {'career_highlights': {'items': []}}}]
    empty = Import(promotions[0].current().project.sources, none, envelope=False, writing={'career_highlights': ['Write them.']}).run()
    assert 'career_highlights' not in empty.table and not empty.written


def test_a_refused_written_block_is_asked_for_again_and_the_second_text_is_kept(promotions):
    from packages.resume_core.importing.lite.scheme import Import
    class Seen(StoredCalls):
        asked = []
        def call(self, kind, block, prompt, schema):
            if kind == 'write':
                self.asked.append(json.loads(prompt))
            return super().call(kind, block, prompt, schema)
    calls = Seen('promotions')
    good = calls.replies[('write', 'write')][0]
    calls.replies[('write', 'write')] = [
        {'reply': {'summary': {'text': 'Руководитель группы разрабoтки.', 'lines': ['S2']}, 'career_highlights': good['reply']['career_highlights']},
         'usage': [10, 0, 5]},
        {'reply': {'summary': good['reply']['summary']}, 'usage': [10, 0, 5]}]

    result = Import(promotions[0].current().project.sources, calls, envelope=False,
                    writing={'summary': ['Write it.'], 'career_highlights': ['Write them.']}).run()
    assert result.table['summary'][0] == {'text': good['reply']['summary']['text']}
    assert result.written == {'summary': ['/text'], 'career_highlights': ['/items/*']}
    # The second call asks for the refused block alone and says why; the list the first reply gave stands.
    first, second = Seen.asked
    assert [item['block'] for item in first['write']] == ['summary', 'career_highlights']
    assert [item['block'] for item in second['write']] == ['summary'] and 'two alphabets' in second['refused']['summary']


def test_a_written_block_is_asked_for_by_the_templates_rules_of_wording_not_the_legacy_prompts(highlights):
    from packages.resume_core.importing.lite.rules import BLOCKS, STYLE
    from packages.resume_core.importing.lite.scheme import Import
    promotions = highlights
    package = promotions[0].current().project.template_package
    rules = lite_import.writing_rules(package)
    # The bundled template carries the unified rules as its own copy.
    summary = next(block for block in package.definition.blocks if block.id == 'summary')
    highlights = next(block for block in package.definition.blocks if block.id == 'career_highlights')
    assert rules == {'summary': [*summary.rules, *package.definition.model.rules],
                     'career_highlights': [*highlights.rules, *package.definition.model.rules]}
    assert rules == {block: [*BLOCKS[block], *STYLE] for block in ('summary', 'career_highlights')}
    # A template words its blocks its own way; one with no rules at all gets the unified ones.
    own = package.definition.model_copy(update={'model': package.definition.model.model_copy(update={'rules': ['Коротко.']}),
        'blocks': [block.model_copy(update={'rules': ['О себе: одно предложение.'] if block.id == 'summary' else []})
                   for block in package.definition.blocks]})
    assert lite_import.writing_rules(package.model_copy(update={'definition': own})) == {
        'summary': ['О себе: одно предложение.', 'Коротко.'], 'career_highlights': ['Коротко.']}
    bare = package.definition.model_copy(update={'model': package.definition.model.model_copy(update={'rules': []}),
        'blocks': [block.model_copy(update={'rules': []}) for block in package.definition.blocks]})
    assert lite_import.writing_rules(package.model_copy(update={'definition': bare})) == {
        block: [*BLOCKS[block], *STYLE] for block in ('summary', 'career_highlights')}

    class Seen(StoredCalls):
        prompts = {}
        def call(self, kind, block, prompt, schema):
            self.prompts[(kind, block)] = json.loads(prompt)
            return super().call(kind, block, prompt, schema)
    calls = Seen('promotions')
    Import(promotions[0].current().project.sources, calls, envelope=False, writing=rules).run()
    # One call lists every empty block with what it holds and its own instructions.
    asked = calls.prompts[('write', 'write')]['write']
    assert [(item['block'], item['instructions']) for item in asked] == [(block, rules[block]) for block in ('summary', 'career_highlights')]
    assert all(item['holds'] for item in asked)
    # No rules for a block: it is not written; no rules at all: no call.
    plain = Seen('promotions')
    plain.prompts = {}
    result = Import(promotions[0].current().project.sources, plain, envelope=False).run()
    assert ('write', 'write') not in plain.prompts and not result.written


def test_a_stated_length_of_work_has_one_form_whatever_words_stand_around_it():
    from packages.resume_core.importing.lite.scheme import same_tool, years
    forms = {'около 5 лет': '5 лет', '5+ лет': '5 лет', 'более 10 лет опыта': '10 лет', '1 год': '1 год', '21 год': '21 год',
             '3 г.': '3 года', '12 лет': '12 лет', '1,5 года': '1,5 года', 'over 3 years': '3 years', '1 yr': '1 year'}
    assert {text: (years(text) or [None, None])[1] for text in forms} == forms
    # The unit is written in the résumé's language when it is given.
    assert years('3 years', russian=True)[1] == '3 года' and years('1,5 года', russian=False)[1] == '1.5 years'
    # Months alone, a calendar year and a bare number are no length in years.
    assert [years(text) for text in ('8 месяцев', '2015 г.', '22', 'давно')] == [None] * 4
    # One tool, whatever its spelling; C, C++ and C# are three.
    assert same_tool('Postgres') == same_tool('PostgreSQL') and same_tool('Win Forms') == same_tool('WinForms')
    assert len({same_tool(name) for name in ('C', 'C++', 'C#')}) == 3


def test_the_experience_of_a_technology_is_given_as_years_alone_and_the_words_left_out_are_marked_in_the_original(tmp_path):
    line = 'Java — около 5 лет, Spring Boot, PostgreSQL — 3 years, Kafka, Kubernetes, управление командой'

    class Copied(StoredCalls):
        """The stored run with a model that copied the whole phrase, translated a unit and gave a length no line states."""
        def call(self, kind, block, prompt, schema):
            reply, row = super().call(kind, block, prompt, schema)
            if (kind, block) == ('fill', 'focus'):
                given = {'Java': 'около 5 лет', 'PostgreSQL': '3 года', 'Kafka': '7 лет'}
                reply = {'items': [{**item, 'experience': given.get(item['technology'])} for item in reply['items']]}
            return reply, row
    fixture, operation = lite_run(tmp_path, 'promotions', calls=Copied('promotions'), lines={6: line})
    assert operation.state == 'published'
    stated = {record.display.raw_text: record.experience.raw_text for record in fixture.current().project.facts.records
              if record.kind == 'technology' and record.experience.raw_text}
    # The number of years with its unit in the résumé's language; a length no line states is not taken.
    assert stated == {'Java': '5 лет', 'PostgreSQL': '3 года'}
    # The original marks the words left out; the résumé marks the word the form added.
    marked = [issue.message for issue in fixture.current().project.import_issues if issue.code == 'IMPORT_LINES_NO_FIELD']
    assert line + '\tyears командой около управление' in marked
    from packages.resume_core.repository.source_diff import additions
    assert ['года'] in additions(fixture.current()).values() and ['лет'] not in additions(fixture.current()).values()


def test_a_cv_with_its_own_summary_is_copied_and_nothing_is_written():
    from packages.resume_core.importing.lite import prompts
    from packages.resume_core.importing.lite.scheme import Import

    class Mapped(StoredCalls):
        """The stored run, with the map giving the job title line to the summary as the CV's own text."""
        def call(self, kind, block, prompt, schema):
            reply, row = super().call(kind, block, prompt, schema)
            if kind == 'map' and reply is not None:
                reply = {**reply, 'blocks': [*reply['blocks'], {'block': 'summary', 'ranges': [{'first': 'S12', 'last': 'S12'}]}]}
            return reply, row
    data = (FIXTURES / 'promotions.docx').read_bytes()
    calls = Mapped('promotions')
    result = Import([canonical_source(extract(data, 'promotions.docx'))], calls, envelope=False,
                    writing={'summary': ['Write it.']}).run()
    assert result.state == 'succeeded' and not result.written and 'summary' in prompts.WRITE
    assert ('write', 'write') not in [(row['kind'], row['block']) for row in calls.rows]
    assert result.table['summary'][0] == {'text': 'Руковожу группой из семи разработчиков биллинга'}


def test_a_lite_import_gives_the_editor_the_lines_its_document_does_not_show(promotions):
    fixture, operation = promotions
    codes = {'IMPORT_LINES_NO_FIELD': 'no_field', 'IMPORT_LINES_DROPPED': 'dropped', 'IMPORT_LINES_HIDDEN': 'hidden'}
    blocks = {task.id: task.block_id for task in operation.tasks}
    marked = {(blocks[issue.task_id], codes[issue.code]): issue.message.split('\n')
              for issue in fixture.current().project.import_issues if issue.code in codes}
    assert marked == {
        # The document shows the technologies of the skills line; after the tab stand the words it does not show.
        ('focus', 'no_field'): ['Java, Spring Boot, PostgreSQL, Kafka, Kubernetes, управление командой\tкомандой управление'],
        # Nothing of the employer's whole period is shown: the line is marked whole.
        ('projects', 'no_field'): ['Сентябрь 2017 — по настоящее время'],
        # The e-mail is hidden on purpose. The CV's section headings are hidden too, and are form: not marked.
        ('identity', 'hidden'): ['nina@example.org'],
    }


def test_a_lite_import_keeps_the_lines_its_document_does_not_show(promotions):
    _fixture, operation = promotions
    kept = sorted((value.owner, value.reason, len(value.lines)) for value in operation.other_lines)
    # A line no field took is kept with its block. A line the map hid is kept with the block it stands in (identity
    # when it stands in none).
    assert kept == [('focus', 'no_field', 1), ('identity', 'hidden', 4), ('projects', 'no_field', 1)]


def test_the_lines_of_a_value_the_admission_drops_are_kept(promotions):
    from packages.resume_core.importing.lite.words import line_words
    project = promotions[0].current().project
    result = lite_import.run(project.sources, project.template_package, StoredCalls('promotions'))
    payload, _evidence = result.table['projects']
    assert result.dropped_of('projects', payload) == []
    # Without one task of the first job the content no longer shows that task's lines: they are kept, and no other.
    cut = json.loads(json.dumps(payload))
    task = cut[0]['tasks'].pop()
    lines = result.dropped_of('projects', cut)
    assert lines and set().union(*(line_words(text) for text, _words in lines)) <= lite_import.shown_words(task)


def test_a_project_with_no_employer_role_or_period_is_still_a_card(tmp_path):
    fixture, operation = lite_run(tmp_path, 'junior')
    assert operation.state == 'published'
    # One job and two study projects: the projects state no employer, no role and no dates.
    assert jobs(fixture) == [('ООО «Первый шаг»', 'Стажёр-разработчик'), ('', ''), ('', '')]
    text = document_text(fixture)
    assert 'Бот «Расписание»' in text and 'Сайт «Книжная полка»' in text


def test_a_lite_import_whose_map_fails_stops_and_publishes_nothing(tmp_path):
    # With no map there is nothing to fill a block from: the import fails (and can be started again), it does not
    # publish an empty résumé as a success.
    with pytest.raises(TemplateImportFailure, match='IMPORT_INVALID_RESULT'):
        lite_run(tmp_path, 'promotions', fail={'map'})


class Partly(StoredCalls):
    """The stored run with some calls failing: {(kind, block): error code}."""

    def __init__(self, name, errors):
        super().__init__(name)
        self.errors = errors

    def call(self, kind, block, prompt, schema):
        code = self.errors.get((kind, block))
        if code is None:
            return super().call(kind, block, prompt, schema)
        row = {'kind': kind, 'block': block, 'errorCode': code, 'usage': None}
        self.rows.append(row)
        return None, row


def test_a_block_whose_call_fails_is_asked_once_more_and_then_keeps_and_marks_its_lines(tmp_path):
    calls = Partly('promotions', {('fill', 'education'): 'INVALID_RESULT'})
    fixture, operation = lite_run(tmp_path, 'promotions', calls=calls)
    assert operation.state == 'published'
    assert [(row['kind'], row['block']) for row in calls.rows].count(('fill', 'education')) == 2
    assert 'Томский институт' not in document_text(fixture)
    # No line of the CV is lost without a trace: the block's line is kept with the import and marked in the original.
    assert ('education', 'no_field', 1) in [(value.owner, value.reason, len(value.lines)) for value in operation.other_lines]
    marked = [issue.message for issue in fixture.current().project.import_issues if issue.code == 'IMPORT_LINES_NO_FIELD']
    assert 'Томский институт радиоэлектроники, 2017, программная инженерия' in marked
    # The other blocks are as in a run with no failure.
    assert jobs(fixture)[0] == ('АО «Северная линия»', 'Руководитель группы разработки')


def test_an_account_stop_in_any_call_of_the_scheme_stops_the_import_unpublished(tmp_path):
    from resume_api.importer.template_pipeline import AccountStop
    # The quota ends after the map: nothing is published from a part of the CV, and the call is not asked again.
    calls = Partly('promotions', {('entry', 'projects.1'): 'QUOTA_EXHAUSTED'})
    with pytest.raises(AccountStop, match='QUOTA_EXHAUSTED'):
        lite_run(tmp_path, 'promotions', calls=calls)
    assert [(row['kind'], row['block']) for row in calls.rows].count(('entry', 'projects.1')) == 1


def test_the_schemes_calls_are_the_imports_calls_and_keep_its_cap(tmp_path, promotions):
    import threading
    from packages.resume_core.importing.template_import import model_calls, spent_calls
    from resume_api.projects.imports import usage_detail
    fixture, operation = promotions
    # The notice counts the calls the scheme made; the tasks, answered by code, spend none of the cap.
    made = len(fixture.transport.stored.rows)
    assert operation.lite_calls == made == model_calls(operation) and spent_calls(operation) == 0 and operation.attempts
    assert usage_detail(operation)['usage']['calls'] == made
    # A call past the cap is not made, and it is not asked for again.

    class Failing:
        def generate(self, _request, _files, _cancel):
            raise ContentFailure('INVALID_RESULT', logical_attempts=1, cleanup_verified=True, dispatch_witness={})
    calls = lite_import.LiteCalls(Failing(), 'codex_cli', 'model', 'low', tmp_path, threading.Event(), lambda: 60.0, None, cap=2)
    codes = [calls.call('fill', 'focus', '{}', {'type': 'object', 'properties': {}})[1]['errorCode'] for _ in range(3)]
    assert codes[2] == 'IMPORT_CALL_CAP' and 'IMPORT_CALL_CAP' not in codes[:2] and calls.started == 2
    # An import whose scheme ran into the cap stops with that and publishes nothing.
    capped = Partly('promotions', {('entry', 'projects.2'): 'IMPORT_CALL_CAP'})
    with pytest.raises(TemplateImportFailure, match='IMPORT_CALL_CAP'):
        lite_run(tmp_path / 'capped', 'promotions', calls=capped)
    assert [(row['kind'], row['block']) for row in capped.rows].count(('entry', 'projects.2')) == 1


def test_the_task_steps_of_a_lite_import_stay_in_memory_and_are_saved_with_the_steps_that_keep_the_reading(tmp_path, monkeypatch):
    from resume_api.importer.template_sidecar import OperationSidecar
    written, write = [], OperationSidecar.write
    monkeypatch.setattr(OperationSidecar, 'write',
        lambda self, *args, **options: written.append(len(args[2].task_results)) or write(self, *args, **options))
    fixture, operation = lite_run(tmp_path, 'promotions')
    assert operation.state == 'published' and len(operation.task_results) == len(operation.tasks) > 10
    # Code answers the tasks, so no step of theirs is a file: the reading is saved before them, and the step that
    # drops it saves every task's result at once.
    assert written == [0, len(operation.tasks)]


def test_a_value_that_breaks_the_templates_schema_is_left_out_alone(tmp_path):
    line = 'Java; Spring Boot, PostgreSQL, Kafka, Kubernetes, управление командой'

    class Listed(StoredCalls):
        """The stored run with a focus item that is a list of two names, as the CV's line writes them."""
        def call(self, kind, block, prompt, schema):
            reply, row = super().call(kind, block, prompt, schema)
            if (kind, block) == ('fill', 'focus'):
                reply = {'items': [{'technology': 'Java; Spring Boot', 'experience': None}, *reply['items'][2:]]}
            return reply, row
    fixture, operation = lite_run(tmp_path, 'promotions', calls=Listed('promotions'), lines={6: line})
    assert operation.state == 'published'
    shown = document_text(fixture)
    # The template takes one name per item: the bad item is dropped, the block and its other items stay.
    assert 'Java; Spring Boot' not in shown and 'Kubernetes' in shown
    focus = next(task.id for task in operation.tasks if task.block_id == 'focus')
    assert not [issue for issue in operation.issues if issue.code == 'IMPORT_SOURCE_FALLBACK' and issue.task_id == focus]


def test_a_task_that_names_a_technology_is_still_a_task_when_the_reply_leaves_it_out(tmp_path):
    task = 'Спроектировала сервис тарификации на Kafka'

    class Short(StoredCalls):
        def call(self, kind, block, prompt, schema):
            reply, row = super().call(kind, block, prompt, schema)
            if (kind, block) == ('entry', 'projects.1'):
                reply = {**reply, 'tasks': [value for value in reply['tasks'] if value != task]}
            return reply, row
    fixture, _operation = lite_run(tmp_path, 'promotions', calls=Short('promotions'))
    # The line is cited only by the technology it names; it is a sentence, not a stack line, so it goes in as a bullet.
    assert task in document_text(fixture)


AWARDS_BLOCK = """- id: awards
  region: main
  order: 45
  schema:
  - title: text
    year: date
  extract:
  - Extract each award, prize or contest place with its title and the stated year.
  view:
    title:
      ru: НАГРАДЫ
      en: AWARDS
    item_gap: 8
    nodes:
    - type: join_fields
      fields: [/title, /year]
      separator: ', '
      style: body
"""
AWARDS_FACT = """- id: awards
  fields:
    title: text
    year: date
"""


def awards_package():
    """The two-column template with one block of its author's own."""
    from packages.resume_core.templates import store
    from packages.resume_core.templates.compiler import compile_bytes
    text = store.bundled_source('generic-two-column').decode()
    at = text.index('\n- id: location\n') + 1
    text = text[:at] + AWARDS_BLOCK + text[at:]
    at = text.index('\nfact_types:\n') + len('\nfact_types:\n')
    text = (text[:at] + AWARDS_FACT + text[at:]).replace('  id: generic-two-column\n', '  id: own-awards\n', 1)
    return compile_bytes(text.encode(), store.BUNDLED_TEMPLATES['generic-two-column'].parent, original_format='yaml')


def test_a_block_of_the_templates_own_is_mapped_read_by_its_schema_and_shown(tmp_path):
    class Awarded(StoredCalls):
        """The stored run of a CV whose fourth line states an award: the map gives the line to the template's own
        block, and the block's call copies one award and makes up another."""
        prompts = {}

        def call(self, kind, block, prompt, schema):
            self.prompts[(kind, block)] = (json.loads(prompt), schema)
            if (kind, block) == ('fill', 'awards'):
                row = {'kind': kind, 'block': block, 'errorCode': None, 'usage': ReportedUsage(10, 0, 5, True)}
                self.rows.append(row)
                return {'items': [{'title': 'Лучший наставник года', 'year': '2022'},
                                  {'title': 'Премия совета директоров', 'year': None}]}, row
            reply, row = super().call(kind, block, prompt, schema)
            if kind == 'map' and reply is not None:
                hidden = [{'first': 'S5', 'last': value['last']} if value['first'] == 'S4' else value for value in reply['hidden']]
                reply = {**reply, 'hidden': hidden,
                         'blocks': [*reply['blocks'], {'block': 'awards', 'ranges': [{'first': 'S4', 'last': 'S4'}]}]}
            return reply, row
    calls = Awarded('promotions')
    fixture, operation = lite_run(tmp_path, 'promotions', calls=calls, lines={4: 'Лучший наставник года, 2022'},
                                  package=awards_package())
    assert operation.state == 'published'
    # The map is told what the block holds in its author's words, and may give it lines.
    asked, schema = calls.prompts[('map', 'map')]
    assert {'block': 'awards', 'holds': 'AWARDS / НАГРАДЫ — Extract each award, prize or contest place with its title and '
                                        'the stated year.'} in asked['blocks']
    assert 'awards' in schema['properties']['blocks']['items']['properties']['block']['enum']
    # The block's call follows its schema: a text may be null and a date is asked for as its text.
    request, shape = calls.prompts[('fill', 'awards')]
    assert request['instructions'] == ['Extract each award, prize or contest place with its title and the stated year.']
    item = shape['properties']['items']['items']['properties']
    assert item == {'title': {'type': ['string', 'null'], 'minLength': 1}, 'year': {'type': ['string', 'null'], 'minLength': 1}}
    # The award the line states is shown with its year read by code; the one no line states is not.
    shown = document_text(fixture)
    assert 'Лучший наставник года' in shown and 'Премия совета директоров' not in shown and 'НАГРАДЫ' in shown
    award, = [record for record in fixture.current().project.facts.extensions if record.semantic_type == 'foldcv:awards']
    cells = {cell.field_key: cell.typed_value for cell in award.cells}
    assert cells['title'] == 'Лучший наставник года' and cells['year']['year'] == 2022


def test_a_block_the_template_lacks_is_not_asked_for_and_shows_nothing():
    from packages.resume_core.importing.lite.scheme import Import
    line = 'Java — 5 лет, Spring Boot, PostgreSQL, Kafka, Kubernetes, управление командой'
    extracted = extract((FIXTURES / 'promotions.docx').read_bytes(), 'promotions.docx')
    extracted.units[5].text = line
    blocks = [block.id for block in generic_package().definition.blocks if block.id != 'focus']
    calls = StoredCalls('promotions')
    result = Import([canonical_source(extracted)], calls, envelope=False, blocks=blocks).run()
    assert ('fill', 'focus') not in [(row['kind'], row['block']) for row in calls.rows] and 'focus' not in result.table
    # Without Focus nothing shows the stated experience: its words are among the line's words the document lacks.
    lack = next(words for ref, words in result.lack.items() if result.text(ref) == line)
    assert {'лет', '5'} <= set(lack)


def test_a_name_is_a_whole_word_of_its_line_and_the_experience_is_the_technologys_own(promotions):
    from packages.resume_core.importing.lite.scheme import Import, within
    from packages.resume_core.importing.lite.tech import named_in, source_spelling
    assert not named_in('Java', ['JavaScript, TypeScript']) and named_in('Java', ['Java, JS'])
    assert not named_in('C', ['Excel, Scrum']) and named_in('C', ['C, C++']) and not named_in('Go', ['Google Cloud'])
    assert within('java', 'javascript') == -1 and within('java', 'javascript, java 17') == 12
    # A character that folds to two (ß, a ligature a PDF keeps) does not shift the positions.
    assert source_spelling('WinForms', ['Straße, Win Forms']) == 'Win Forms'
    assert source_spelling('WinForms', ['Conﬁgured it, Win Forms']) == 'Win Forms'
    importer = Import(promotions[0].current().project.sources, StoredCalls('promotions'), envelope=False)
    texts = {'S1': 'Python — 5 лет, Docker — 2 года, Go', 'S2': 'Kafka', 'S3': '3 года'}
    importer.text = texts.__getitem__
    importer.spans = lambda refs: list(refs)

    def stated(technology, text):
        evidence = {}
        return importer.experience('focus', '/0/experience', technology, text, list(texts), evidence), evidence.get('/0/experience')
    # The length that stands nearest to the name, in the name's own line; never another technology's.
    assert stated('Docker', '5 лет') == (None, None) and stated('Docker', '2 года') == ('2 года', ['S1'])
    assert stated('Python', '5 лет') == ('5 лет', ['S1']) and stated('Go', '5 лет') == (None, None)
    # A narrow column sets the length on the line under the name.
    assert stated('Kafka', '3 года') == ('3 года', ['S2', 'S3'])


def test_an_import_that_stopped_continues_from_the_reading_it_kept_and_calls_no_model_again(tmp_path):
    from resume_api.importer.template_pipeline import AccountStop
    from tests.templates.pipeline_fixtures import resume_command

    class Stopping(LiteTransport):
        """Answers three of the pipeline's requests, then the account stops (as a signed-out provider would)."""
        stop_after = 3

        def generate(self, request, cancel):
            if lite_import.LITE.get() is not None and self.stop_after is not None and len(self.calls) >= self.stop_after:
                raise ContentFailure('AUTH_REQUIRED', logical_attempts=1, cleanup_verified=True, dispatch_witness={'transport': 'lite'})
            return super().generate(request, cancel)

        def lite_calls(self, model, cancel, remaining, cap=None):
            self.readings += 1
            return super().lite_calls(model, cancel, remaining, cap)
    data = (FIXTURES / 'promotions.docx').read_bytes()
    fixture = EmploymentFixture(tmp_path, captured=generic_package(), src=canonical_source(extract(data, 'promotions.docx')),
                                original_bytes=data, cap=80, fallback=False, concurrency=1)
    fixture.transport = Stopping(fixture, StoredCalls('promotions'))
    fixture.transport.readings = 0
    fixture.pipeline = fixture.fresh_pipeline()
    fixture.pipeline.derive = derive_task
    capture = fixture.command.capture
    capture.allow_text_rewrite, capture.policy.lite = False, True
    capture.policy.processing_seconds, capture.policy.finalization_seconds = import_seconds(), finalization_seconds()
    with pytest.raises(AccountStop):
        asyncio.run(fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted))
    stopped = fixture.current().pre_draft.template_operations[0]
    # The scheme read the CV once, and its reading is kept with the import while tasks wait for it.
    assert fixture.transport.readings == 1 and stopped.lite_reading and 0 < len(stopped.task_results) < len(stopped.tasks)
    # The resume answers the tasks left from that reading: the stored run has no reply left, and none is asked for.
    fixture.transport.stop_after = None
    fixture.transport.stored = StoredCalls('promotions', fail={'map', 'fill', 'entry', 'split', 'write'})
    operation = asyncio.run(fixture.pipeline.run(fixture.project, resume_command(stopped), admitted=fixture.admitted))
    assert operation.state == 'published' and fixture.transport.readings == 1 and not fixture.transport.stored.rows
    # The résumé is the one a run with no stop gives, and the reading is not kept in the project.
    whole, _operation = lite_run(tmp_path / 'whole', 'promotions')
    assert jobs(fixture) == jobs(whole) and document_text(fixture) == document_text(whole)
    assert fixture.current().project.template_operations[0].lite_reading is None
    assert sorted((value.owner, value.reason, len(value.lines)) for value in operation.other_lines) == sorted(
        (value.owner, value.reason, len(value.lines)) for value in _operation.other_lines)


class RefusingProvider(ScriptedTemplateProvider):
    """Refuses the scheme's own calls (they carry no captured request) and counts every call a task makes."""

    def generate(self, request, files, cancel):
        if request.request_value is None:
            self.calls.append({'kind': 'lite'})
            raise ContentFailure('REFUSED', logical_attempts=1, cleanup_verified=True, dispatch_witness={'transport': 'scripted'})
        return super().generate(request, files, cancel)


@pytest.mark.asyncio
async def test_a_start_with_lite_captures_a_lite_import_and_no_task_calls_a_model(tmp_path):
    provider = RefusingProvider()
    async with app_client(tmp_path, call_cap=40, provider=provider) as (client, app):
        project = (await upload(client)).json()['workspace']['projectId']
        started = await client.post('/v2/projects/' + project + '/import',
            json={'kind': 'start', 'clientRequestId': 'import-1', 'allowTextRewrite': True, 'lite': True})
        assert started.status_code == 202, started.text
        runner = app.state.projects.imports.runners.get(started.json()['id'])
        if runner is not None:
            await runner
        [task] = [value for value in (await client.get('/v2/projects/' + project + '/tasks')).json()['tasks']
                  if value['id'] == started.json()['id']]
        # The scheme asked for its map twice and was refused: the import fails with that and publishes nothing.
        assert (task['state'], task['error']) == ('failed', 'IMPORT_INVALID_RESULT'), task
        operation = operation_of(app, project)
        policy = operation.capture.policy
        # A lite import never rewrites, has no map of the product's own and answers its tasks one by one.
        assert (policy.lite, policy.source_map, policy.concurrency, operation.capture.allow_text_rewrite) == (True, False, 1, False)
        app.state.intake.validate(operation, saved(app, project))
        # No task of the pipeline reached the provider.
        assert [call['kind'] for call in provider.calls] == ['lite', 'lite']
        assert saved(app, project).project is None
        # A fast import does not ask for the legacy import's fallback model, so a saved one that is gone cannot
        # refuse its start; the legacy start still checks it.
        def gone(_primary):
            raise ProjectFailure('MODEL_DENIED', 409)
        app.state.intake.fallback = gone
        assert app.state.intake.capture(saved(app, project), False, lite=True).fallback is None
        with pytest.raises(ProjectFailure, match='MODEL_DENIED'):
            app.state.intake.capture(saved(app, project), False, lite=False)


def test_a_template_without_career_highlights_asks_no_part_for_them_and_shows_none(promotions):
    """D184: «Две колонки» 1.7.0 has no block career_highlights. The map does not offer it, no write call names it, no
    task or notice is made for it, and the import publishes; the summary is still written."""
    fixture, operation = promotions
    package = fixture.current().project.template_package
    assert 'career_highlights' not in {block.id for block in package.definition.blocks}
    assert operation.state == 'published'
    assert 'career_highlights' not in {task.block_id for task in operation.tasks}
    notices = [issue for issue in fixture.current().project.import_issues if issue.code == 'IMPORT_TEXT_GENERATED']
    blocks = {task.id: task.block_id for task in operation.tasks}
    assert [blocks[notice.task_id] for notice in notices] == ['summary']

    class Seen(StoredCalls):
        def __init__(self, name):
            super().__init__(name)
            self.prompts, self.schemas = {}, {}

        def call(self, kind, block, prompt, schema):
            self.prompts[(kind, block)], self.schemas[(kind, block)] = json.loads(prompt), schema
            return super().call(kind, block, prompt, schema)
    calls = Seen('promotions')
    result = lite_import.run(fixture.current().project.sources, package, calls)
    mapped = [item['block'] for item in calls.prompts[('map', 'map')]['blocks']]
    assert 'career_highlights' not in mapped and 'summary' in mapped and 'projects' in mapped
    assert 'career_highlights' not in json.dumps(calls.schemas[('map', 'map')])
    assert [item['block'] for item in calls.prompts[('write', 'write')]['write']] == ['summary']
    assert 'career_highlights' not in result.table


def test_the_map_keeps_a_block_whose_lines_a_block_of_the_template_takes():
    """A template without Focus still maps focus lines: they feed its technology lists (D184 rule, map_blocks)."""
    from packages.resume_core.importing.lite.scheme import map_blocks
    names = lambda present: [name for name, _holds in map_blocks(lambda block: block in present)]
    assert 'focus' in names({'programming'}) and 'focus' not in names({'summary'})
    assert 'career_highlights' not in names({'focus', 'projects'}) and 'career_highlights' in names({'career_highlights'})
    # The entry block is always offered: the entries are mapped under it.
    assert names(set()) == ['projects']


def test_a_career_wide_section_is_text_with_no_field_and_moves_into_no_job(tmp_path):
    """D184, 2e: the CV has its own section of career-wide achievements and the template has no block for it. The map
    offers no such block, so its line gets none; the import does not move it into a job. It takes the path of text with
    no field: not on the page, kept with the import's other lines, and marked for the original (red). The jobs keep
    their own results. Synthetic CV: the stored run, with its last two lines made a career section."""
    line = 'Сократила время выпуска релизов вдвое в трёх командах'

    class Career(StoredCalls):
        def call(self, kind, block, prompt, schema):
            reply, row = super().call(kind, block, prompt, schema)
            if kind == 'map' and reply is not None:
                # S30 is the career line now: the map gives it to no block (the stored run gave it to education).
                reply = {**reply, 'blocks': [item for item in reply['blocks'] if item['block'] != 'education']}
            return reply, row
    fixture, operation = lite_run(tmp_path, 'promotions', calls=Career('promotions'),
                                  lines={29: 'Ключевые достижения', 30: line})
    assert operation.state == 'published'
    project = fixture.current().project
    shown = document_text(fixture)
    assert line not in shown and 'Ключевые достижения' not in shown
    assert not any(getattr(block.presentation, 'view_key', None) == 'career_highlights' for block in project.document.blocks())
    # The jobs keep their own results; no job took the career line.
    assert 'Провела переход группы на трёхнедельные релизы' in shown and 'Подготовила 30 практических заданий' in shown
    assert not any(line in record.model_dump_json() for record in project.facts.records if record.kind == 'employment')
    # Kept as text with no field, and marked for the original; the heading is hidden form.
    assert [(value.reason, value.lines) for value in operation.other_lines if line in value.lines] == [('no_field', [line])]
    assert line in [issue.message for issue in project.import_issues if issue.code == 'IMPORT_LINES_NO_FIELD']
    assert any('Ключевые достижения' in value.lines for value in operation.other_lines if value.reason == 'hidden')
