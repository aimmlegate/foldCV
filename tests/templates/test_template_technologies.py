"""D164, point 14 of T4, and D165 with its follow-up: the technologies an entry owns are read against the entry's lines.
A name the lines name in some form passes; one they word otherwise takes their wording and cites its line; any other
leaves the reply by code on every slot and is named in the block's notice, so no model repair runs for it (synthetic
text only)."""

import json

import pytest

from packages.resume_core.hashing import sha256
from packages.resume_core.importing import template_proposals
from packages.resume_core.importing.template_completion import complete_reply
from packages.resume_core.importing.template_identity import evidence_options
from packages.resume_core.importing.template_import import (admit_operation, capture_task_input, dispatch_attempt,
                                                            record_return, reserve_attempt)
from packages.resume_core.importing.template_proposals import parse_proposal
from packages.resume_core.importing.template_technologies import (EntryLines, carried, entry_runs, named, owned_types,
                                                                  source_spelling, verdict)
from packages.resume_core.models.contracts import Source
from packages.resume_core.models.template_import import DroppedValue
from packages.resume_core.project_limits import finalization_seconds, import_seconds
from packages.resume_core.sources import capture_span, line_spans, source_slice
from packages.resume_core.templates.operations import derive_task
from tests.templates.entry_fixtures import ref_of
from tests.templates.generic_fixtures import (block_reply, date, generic_package, generic_script, identity, job, period,
                                              satisfied)
from tests.templates.pipeline_fixtures import NOW, cleaned, owner, resume_command, setup_operation, usage
from tests.templates.template_runtime_fixtures import EmploymentFixture
from tests.templates.test_reply_completion import NO_OFFERS, entry, offered, projects, reply, text_source

TYPES = owned_types(generic_package().definition.fact_types)
EXPANDED = 'TCA (Composable Architecture)'

# One employer, a stack line of the team that no entry holds, four projects; each names its stack on a line of its own.
TEAM = 'Team stack: Fastlane, Xcode Cloud'
LINES = ['Alex Example', 'Mobile engineer', 'Example Labs, 2021–2025', 'Senior iOS developer', TEAM,
    'Atlas, 2021–2022', 'Stack: Swift, TCA, Combine, Realm', 'Built the Atlas booking screens.',
    'Beacon, 2022–2023', 'Stack: Swift 4–5, WinForms', 'Built the Beacon map module.',
    'Comet, 2023–2024', 'Stack: Kotlin, K8s', 'Built the Comet payments flow.',
    'Delta, 2024–2025', 'Stack: Rust, Docker, Tokio', 'Built the Delta onboarding.']
STACKS = {'Atlas': 'Stack: Swift, TCA, Combine, Realm', 'Beacon': 'Stack: Swift 4–5, WinForms', 'Comet': 'Stack: Kotlin, K8s',
    'Delta': 'Stack: Rust, Docker, Tokio'}
YEARS = {'Atlas': '2021–2022', 'Beacon': '2022–2023', 'Comet': '2023–2024', 'Delta': '2024–2025'}
TASKS = {'Atlas': 'Built the Atlas booking screens.', 'Beacon': 'Built the Beacon map module.',
    'Comet': 'Built the Comet payments flow.', 'Delta': 'Built the Delta onboarding.'}
# What the model writes: an expanded abbreviation, names with another dash and spacing, an alias, verbatim names.
WRITTEN = {'Atlas': ['Swift', EXPANDED, 'Combine'], 'Beacon': ['Swift 4-5', 'Win Forms'], 'Comet': ['Kotlin', 'Kubernetes'],
    'Delta': ['Rust', 'Docker']}
# The same names as the source writes them.
STATED = {'Atlas': ['Swift', 'TCA', 'Combine'], 'Beacon': ['Swift 4–5', 'WinForms'], 'Comet': ['Kotlin', 'Kubernetes'],
    'Delta': ['Rust', 'Docker']}
UNBOUND = 'Убраны данные, которые источник не подтверждает: {}. Остальное в блоке принято.'


def source_of(lines):
    raw = ('\n'.join(lines) + '\n').encode()
    value = Source(id='source-papers', revision=1, originalName='projects.txt', mimeType='text/plain',
        byteSha256=sha256(raw), byteRef='sources/papers.txt', parser='text', parserVersion='1',
        units=[{'id': 'unit-papers', 'revision': 1, 'order': 0, 'text': raw.decode(),
            'location': {'kind': 'pasted', 'index': 0, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []}], overlays=[], warnings=[])
    return value, raw


# ------------------------------------------------------------------------------------------------ names and spellings

@pytest.mark.parametrize('name, line, spelled', [
    ('Win Forms', 'Tools: WinForms, WPF', 'WinForms'),
    ('win-forms', 'Tools: WinForms, WPF', 'WinForms'),
    ('Swift 4-5', 'Swift 4–5, UIKit', 'Swift 4–5'),
    ('TCA Composable Architecture', 'TCA (Composable Architecture), Combine', 'TCA (Composable Architecture)'),
    ('1C', '1С:Предприятие 8.3', '1С'),
    # A comma ends a name, and a name takes no letters from the words around it.
    ('SwiftUI', 'Swift, UI kit', None),
    ('Swift, UI', 'SwiftUI', None),
    ('Java', 'JavaScript, TypeScript', None),
    (EXPANDED, 'Stack: Swift, TCA, Combine', None),
])
def test_a_name_takes_the_spelling_of_a_line_only_when_spaces_or_punctuation_differ(name, line, spelled):
    assert source_spelling(name, [line]) == spelled


@pytest.mark.parametrize('name, line, stated', [
    ('swift', 'Stack: Swift, TCA, Combine', True),
    ('TCA', 'Stack: Swift, TCA, Combine', True),
    ('C++', 'C++17, Qt', True),
    ('Python', 'Python3 scripts', True),
    ('Kubernetes', 'Deploy to K8s clusters', True),
    ('Node.js', 'Backend on NodeJS', True),
    ('Go', 'Golang, gRPC', True),
    ('PostgreSQL 15', 'Postgres v15', True),
    (EXPANDED, 'Stack: Swift, TCA, Combine', False),
    ('Java', 'JavaScript, TypeScript', False),
    # A version the lines do not state is no alias of the name they state.
    ('Kafka 4.0', 'Kafka, Redis', False),
    ('Swift 4-5', 'Swift 4–5, UIKit', False),
])
def test_lines_name_a_technology_as_written_or_by_a_catalog_alias(name, line, stated):
    assert named(name, [line]) is stated


@pytest.mark.parametrize('name, lines', [
    # The source layout wrapped the name: two lines in a row read as one.
    ('Oracle Database 19c', ['Databases: Redis, Oracle Database', '19c, MySQL']),
    # A range with another dash and spacing, with or without a leading v, beside a qualifier the reply left out.
    ('Ruby 2.7–3.1', ['Languages: RUBY (MRI) 2.7-3.1, Redis']),
    ('Ruby v2.7 - 3.1', ['Languages: RUBY (MRI) 2.7-3.1, Redis']),
    # Base, version and qualifier: every word of them stands in the line of the base.
    ('Angular 15 (Standalone Components)', ['Web: Angular (v15 Standalone Components, 17 Signals)']),
    ('MVVM (Model-View-ViewModel)', ['Patterns: MVVM / Model-View-ViewModel']),
    # A catalog synonym with the same other words.
    ('Microsoft SQL Server Express', ['Databases: MS SQL Express, Redis']),
    # The CV's typo, one letter changed or two neighbouring letters swapped, which the name fixes.
    ('Postman', ['Testing: Pastman, JMeter']),
    ('Kubernetes', ['Deploy: Kuberentes, Helm']),
])
def test_lines_name_a_technology_in_the_other_forms_that_pass(name, lines):
    assert verdict(name, ['\n'.join(lines)]) is None


@pytest.mark.parametrize('name, line, value, fragment', [
    # A contraction: the parts of the line's name, split at case changes and signs, start the reply's words in order.
    ('Visual Basic .NET', 'Languages: C#, VB.NET', 'VB.NET', 'VB.NET'),
    ('Windows Forms', 'UI: WinForms, WPF', 'WinForms', 'WinForms'),
    ('Windows Presentation Foundation', 'UI: WinForms, WPF', 'WPF', 'WPF'),
    # A qualifier or version the line does not state: the value becomes the base as the line writes it.
    (EXPANDED, 'Stack: Swift, TCA, Combine', 'TCA', 'TCA'),
    ('tca (Composable Architecture)', 'Stack: Swift, TCA, Combine', 'TCA', 'TCA'),
    ('Realm 10', 'Stack: Swift, Realm, Combine', 'Realm', 'Realm'),
    # A base named by alias or with the CV's typo keeps the reply's spelling and is cited by the line's.
    ('Kubernetes (EKS)', 'Deploy to K8s clusters', 'Kubernetes', 'K8s'),
    ('Postman 10', 'Testing: Pastman, JMeter', 'Postman', 'Pastman'),
    # P14: other spaces or punctuation.
    ('Swift 4-5', 'Swift 4–5, UIKit', 'Swift 4–5', 'Swift 4–5'),
])
def test_a_technology_the_lines_word_otherwise_takes_their_wording(name, line, value, fragment):
    assert verdict(name, [line]) == (value, fragment)


@pytest.mark.parametrize('name, lines', [
    ('Tailwind', ['Stack: Swift, TCA, Combine']),
    # Two lines that are not in a row do not make one name.
    ('Oracle Database 19c', ['Databases: Redis, Oracle Database', 'Built the reports.', '19c, MySQL']),
    # The typo rule needs six letters, the same first letter and one change.
    ('Kafka', ['Queues: Kfaka, Redis']),
    ('Kotlin', ['Languages: Gotlin']),
    ('Postman', ['Testing: Pastmen, JMeter']),
    # A contraction joins two or more words, never across a slash, and every word takes a part.
    ('JavaScript', ['Languages: Java, Kotlin']),
    ('GitHubActions', ['CI: GitHub, Jenkins']),
    ('Apache Beam', ['Ran A/B tests']),
    ('React Native', ['Web: React, Redux']),
    # Other words after a catalog name stand right after it.
    ('Java Spring', ['Backend: Java, Spring']),
])
def test_a_technology_the_lines_name_in_no_form_is_left_out(name, lines):
    assert verdict(name, ['\n'.join(lines)]) is False


def units_source(*texts):
    """A source of one unit per line, as a parsed upload often has."""
    raw = '\n'.join(texts).encode()
    return Source(id='source-units', revision=1, originalName='lines.txt', mimeType='text/plain', byteSha256=sha256(raw),
        byteRef='sources/lines.txt', parser='text', parserVersion='1', units=[{'id': 'unit-' + str(index), 'revision': 1,
            'order': index, 'text': text, 'location': {'kind': 'pasted', 'index': index, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []} for index, text in enumerate(texts)], overlays=[], warnings=[])


def test_the_lines_of_an_entry_stay_in_a_row_across_units_and_another_entry_breaks_the_row():
    texts = ['Example Labs — engineer', 'Built the reports.', 'Stack: C#, Oracle Database', '19c, Redis',
        'North Co — engineer', 'Built the exports.']
    src = units_source(*texts)
    def line(index):
        return capture_span(src, src.units[index])
    # The record cites its header and its task; its stack lines below them are the technologies' own and join the run,
    # so the name the layout wrapped is named.
    runs = entry_runs([src], [line(0), line(1)], [line(2), line(3)])
    assert runs == ['\n'.join(texts[:4])] and verdict('Oracle Database 19c', runs) is None
    # The text between the cited lines counts, without the lines of another entry.
    assert entry_runs([src], [line(0), line(5)], [], others=[line(4)]) == ['\n'.join(texts[:4]), texts[5]]
    # Units that are not in a row are runs of their own.
    assert entry_runs([src], [line(0)], [line(2)]) == [texts[0], texts[2]]


# ---------------------------------------------------------------------------------------------------------- completion

TEXT = ('North Studio — iOS developer, 2019–2021\nStack: Swift 4–5, WinForms, TCA\nBuilt the booking screens.\n'
    'South Works — iOS developer, 2021–2023\nStack: Win Forms, K8s\nBuilt the map module.\n')


def completed(payload, given=(), **options):
    _options, table, _lines = offered(TEXT)
    return complete_reply(reply(payload, given), projects().bindings, table, NO_OFFERS, **options)


def test_a_name_written_with_other_punctuation_takes_the_source_spelling_and_cites_its_line():
    _options, _table, lines = offered(TEXT)
    payload = [job('North Studio', 'iOS developer', None, technologies=['Swift 4-5', 'win-forms', 'TCA'])]
    # The reply cites the header for one name; respelled, it cites the line that states it.
    given = [entry('/0/technologies/1/display', [lines['North Studio — iOS developer, 2019–2021']])]
    done = completed(payload, given, technologies=TYPES)
    assert [value['display'] for value in done['payload'][0]['technologies']] == ['Swift 4–5', 'WinForms', 'TCA']
    evidence = {value['pointer']: value['evidence'] for value in done['fields']}
    stack = lines['Stack: Swift 4–5, WinForms, TCA']
    assert evidence['/0/technologies/0/display'] == [stack] and evidence['/0/technologies/1/display'] == [stack]
    assert payload[0]['technologies'][0]['display'] == 'Swift 4-5'


def test_a_list_entry_above_a_respelled_name_gives_way_to_the_line_that_states_it():
    _options, _table, lines = offered(TEXT)
    payload = [job('North Studio', 'iOS developer', None, technologies=['Win-Forms', 'TCA'])]
    header = lines['North Studio — iOS developer, 2019–2021']
    done = completed(payload, [entry('/0/technologies', [header])], technologies=TYPES)
    evidence = {value['pointer']: value['evidence'] for value in done['fields']}
    assert done['payload'][0]['technologies'][0]['display'] == 'WinForms'
    assert evidence['/0/technologies/0/display'] == [lines['Stack: Swift 4–5, WinForms, TCA']]
    # A name the reply wrote as the source does keeps the list's evidence.
    assert evidence['/0/technologies/1/display'] == [header]


def test_the_entry_lines_give_the_spelling_before_the_rest_of_the_source():
    _options, table, lines = offered(TEXT)
    payload = [job('South Works', 'iOS developer', None, technologies=['Win-Forms'])]
    south = {lines[text]: table[lines[text]] for text in ['South Works — iOS developer, 2021–2023', 'Stack: Win Forms, K8s',
        'Built the map module.']}
    assert completed(payload, preferred=south, technologies=TYPES)['payload'][0]['technologies'][0]['display'] == 'Win Forms'
    assert completed(payload, technologies=TYPES)['payload'][0]['technologies'][0]['display'] == 'WinForms'


@pytest.mark.parametrize('names', [['Swift 4–5', 'TCA'], ['swift 4–5', 'tca'], ['Kubernetes'], [EXPANDED], []])
def test_a_name_the_lines_state_or_do_not_write_at_all_completes_as_before(names):
    payload = [job('North Studio', 'iOS developer', None, technologies=names, tasks=['Built the booking screens.'])]
    assert completed(payload, technologies=TYPES) == completed(payload)


@pytest.mark.parametrize('company, names', [('North Studio', ['Swift 4–5', 'TCA']), ('North Studio', ['swift 4–5', 'tca']),
    ('North Studio', ['WinForms', 'Swift 4–5']), ('South Works', ['Kubernetes', 'Win Forms']), ('South Works', [])])
def test_a_name_its_entry_states_stays_untouched_when_read_against_the_entry(company, names):
    payload = [job(company, 'iOS developer', None, technologies=names, tasks=['Built the booking screens.'
        if company == 'North Studio' else 'Built the map module.'])]
    read = EntryLines(TYPES, [text_source(TEXT)])
    assert completed(payload, technologies=TYPES, entry_lines=read) == completed(payload) and read.dropped == []


STACK_TEXT = ('North Studio — iOS developer, 2019–2021\n'
    'Stack: Swift, RUBY (MRI) 2.7-3.1, Angular (v15 Standalone Components), Oracle Database\n'
    '19c, MS SQL Express, Pastman\n'
    'Also: VB.NET, WinForms, WPF, MVVM, Realm, K8s\n'
    'Built the booking screens.\n')


def test_each_technology_passes_takes_the_wording_of_its_line_or_leaves_the_reply_with_its_citation():
    _options, table, lines = offered(STACK_TEXT)
    stack, next_line = lines[STACK_TEXT.splitlines()[1]], lines['19c, MS SQL Express, Pastman']
    also, header = lines['Also: VB.NET, WinForms, WPF, MVVM, Realm, K8s'], lines['North Studio — iOS developer, 2019–2021']
    # (written, its citation in the reply or None, what it becomes or None when it leaves, the line it cites then)
    cases = [('Swift', stack, 'Swift', stack), ('Ruby 2.7–3.1', stack, 'Ruby 2.7–3.1', stack),
        ('Angular 15 (Standalone Components)', stack, 'Angular 15 (Standalone Components)', stack),
        ('Oracle Database 19c', stack, 'Oracle Database 19c', stack),
        ('Microsoft SQL Server Express', next_line, 'Microsoft SQL Server Express', next_line),
        ('Postman', next_line, 'Postman', next_line),
        ('Visual Basic .NET', header, 'VB.NET', also), ('Windows Forms', None, 'WinForms', also),
        ('MVVM (Model-View-ViewModel)', also, 'MVVM', also), ('Realm 10', also, 'Realm', also),
        ('Kubernetes (EKS)', also, 'Kubernetes', also), ('Tailwind', None, None, None), ('Svelte', stack, None, None)]
    payload = [job('North Studio', 'iOS developer', None, technologies=[case[0] for case in cases],
        tasks=['Built the booking screens.'])]
    given = [entry('/0/technologies/' + str(index) + '/display', [case[1]]) for index, case in enumerate(cases) if case[1]]
    read = EntryLines(TYPES, [text_source(STACK_TEXT)])
    done = complete_reply(reply(payload, given), projects().bindings, table, NO_OFFERS, technologies=TYPES, entry_lines=read)
    kept = [case for case in cases if case[2] is not None]
    assert [value['display'] for value in done['payload'][0]['technologies']] == [case[2] for case in kept]
    evidence = {value['pointer']: value['evidence'] for value in done['fields']}
    assert [evidence['/0/technologies/' + str(index) + '/display'] for index in range(len(kept))] == [[case[3]] for case in kept]
    assert read.dropped == [{'pointer': '/0/technologies/11/display', 'fieldKey': 'display', 'text': 'Tailwind'},
        {'pointer': '/0/technologies/12/display', 'fieldKey': 'display', 'text': 'Svelte'}]
    # The job's other values complete as they would without the names that left.
    assert evidence['/0/tasks/0/value'] == [lines['Built the booking screens.']]


def test_only_the_technologies_an_entry_owns_are_respelled():
    _options, table, _lines = offered(TEXT)
    programming = next(block for block in generic_package().definition.blocks if block.id == 'programming')
    skills = {'schemaVersion': 3, 'payload': {'items': ['Win-Forms']}, 'discoveries': None, 'fields': [], 'lineage': None,
        'relations': None}
    assert (complete_reply(skills, programming.bindings, table, NO_OFFERS, technologies=TYPES)
        == complete_reply(skills, programming.bindings, table, NO_OFFERS))
    # A name read from the editor's cells stays as it is, also against its entry.
    payload = [job('North Studio', 'iOS developer', None, technologies=['Win-Forms', 'Bootstrap'])]
    given = [{**entry('/0/technologies/' + str(index) + '/display', []), 'effectiveCells': ['E1']} for index in range(2)]
    read = EntryLines(TYPES, [text_source(TEXT)])
    done = completed(payload, given, technologies=TYPES, entry_lines=read)
    assert [value['display'] for value in done['payload'][0]['technologies']] == ['Win-Forms', 'Bootstrap']
    assert read.dropped == []


def dropped(pointer, text, key='display'):
    return DroppedValue.model_validate({'pointer': pointer, 'fieldKey': key, 'text': text})


def test_a_repair_keeps_the_technologies_an_earlier_reply_lost_unless_it_states_or_loses_them_itself():
    earlier = [dropped('/0/technologies/2/display', 'Tailwind'), dropped('/1/technologies/0/display', 'Svelte'),
        dropped('/0/tasks/1/value', 'Invented task.', 'value'), dropped('/0/technologies/3/display', 'Docker'),
        dropped('/1/technologies/1/display', 'Svelte')]
    repair = {'payload': [job('North Studio', 'iOS developer', None, technologies=['Swift', 'docker'])]}
    own = [dropped('/0/technologies/2/display', 'tailwind')]
    # Tailwind is named by the repair's own loss, Docker stands in the repair, a task is no technology; Svelte once.
    assert [value.text for value in carried(earlier, own, repair, projects().bindings, TYPES)] == ['Svelte']


# ----------------------------------------------------------------------------------------------------- a block run whole

def parsed(text, payload, cites):
    """The proposal of one projects reply over `text` for the block run whole, with its operation and source; cites
    gives the line a value cites by its pointer, the coordinator cites the rest."""
    package = generic_package()
    src, _raw = source_of(text.splitlines())
    operation, _command, _package, _src, facts = setup_operation(captured=package, src=src, cap=4)
    operation = admit_operation(operation, NOW)
    task = next(task for task in operation.tasks if task.block_id == 'projects')
    task.dependencies = []
    unit = src.units[0]
    options = evidence_options([capture_span(src, unit), *line_spans(src, unit)], [src])
    request = {'protocol': 'template_import_v1', 'evidence': [option.model_dump(mode='json', by_alias=True) for option in options],
        'references': {'items': [], 'cells': [], 'relations': []}}
    operation = capture_task_input(operation, task.id, request, [], NOW)
    task = next(value for value in operation.tasks if value.id == task.id)
    operation, attempt = reserve_attempt(operation, task.id, 'initial', task.input_hash, operation.capture.primary, owner(1), NOW,
        request_value=request)
    operation = dispatch_attempt(operation, attempt, NOW)
    refs = {option.text.rstrip('\n'): option.ref for option in options}
    body = {'schemaVersion': 3, 'payload': payload, 'discoveries': None, 'lineage': None, 'relations': None,
        'fields': [entry(pointer, [refs[line]]) for pointer, line in cites.items()]}
    operation = record_return(operation, attempt, json.dumps({'payload': body}), 'completed', usage(), cleaned(), returned_at=NOW)
    operation, _facts, proposal = parse_proposal(operation, attempt, package, [src], facts)
    assert proposal.state == 'provisional', proposal.errors
    return proposal, operation, src


def test_a_block_run_whole_reads_each_name_against_the_lines_its_record_cites():
    # Below the record's other lines: a name alone on a line no other value cites stays, and so does an alias; an
    # abbreviation the reply expanded takes the form of the line it cites, and a name no line states leaves the reply
    # on the initial slot, the proposal stays valid and names it.
    text = 'Example Labs — backend engineer\n2020–2023\nImplemented queue processing.\nPython\nStack: Go, TCA\n'
    when = period('2020–2023', date('2020', 2020), date('2023', 2023), False)
    payload = [job('Example Labs', 'backend engineer', when,
        technologies=['Python', 'Golang', 'TCA (Task Coordination API)', 'Tailwind'], tasks=['Implemented queue processing.'])]
    proposal, _operation, src = parsed(text, payload, {'/0/technologies/1/display': 'Stack: Go, TCA',
        '/0/technologies/2/display': 'Stack: Go, TCA'})
    assert [value['display'] for value in proposal.reply.payload[0]['technologies']] == ['Python', 'Golang', 'TCA']
    field = next(value for value in proposal.resolved_fields if value.pointer == '/0/technologies/2/display')
    assert [source_slice([src], span) for span in field.evidence] == ['Stack: Go, TCA\n']
    assert [(value.pointer, value.text) for value in proposal.dropped_values] == [('/0/technologies/3/display', 'Tailwind')]


# ------------------------------------------------------------------------------------------- the review and the repair

def project(name, technologies, role='Senior iOS developer'):
    start, end = YEARS[name].split('–')
    return job('Example Labs', role, period(YEARS[name], date(start, int(start)), date(end, int(end)), False),
        project={'name': name, 'description': None}, technologies=technologies, tasks=[TASKS[name]])


def scripted(src, written=WRITTEN, *, repaired=None, cites=None, roles=None, review=satisfied):
    """Replies of the whole import. Outlined, the projects block has one entry per project; each project lists
    written[name], or repaired[name] with its role from roles in a repair, every name cited from the project's stack
    line unless cites names another line. review answers each review; by default every check the model is asked
    holds."""
    block = projects()
    others = generic_script(src, {'identity': identity('Alex Example', 'Mobile engineer', 'other', 'Mobile engineer')})
    def script(request, value):
        if 'targets' in value:
            return review(value)
        if value.get('declaration', {}).get('id') != 'projects' or value.get('slot') == 'outline_review':
            return others(request, value)
        if value.get('slot') == 'outline':
            return {'entries': [{'title': name, 'first': ref_of(value, name + ', ' + YEARS[name]),
                'last': ref_of(value, TASKS[name])} for name in STACKS]}
        names = [part['title'] for part in value['entry']['parts']] if 'entry' in value else list(STACKS)
        repair = repaired is not None and value.get('slot') != 'initial'
        listed = repaired if repair else written
        moved = {'/' + str(position) + '/technologies/' + str(index) + '/display': (cites or {}).get((name, technology),
            STACKS[name]) for position, name in enumerate(names) for index, technology in enumerate(listed[name])}
        items = [project(name, listed[name], (roles or {}).get(name, 'Senior iOS developer') if repair
            else 'Senior iOS developer') for name in names]
        return block_reply(block, items, src, moved, value)
    return script


def fixture_for(tmp_path, *, concurrency=2):
    src, raw = source_of(LINES)
    fixture = EmploymentFixture(tmp_path, captured=generic_package(), src=src, original_bytes=raw, cap=60, fallback=False,
        concurrency=concurrency)
    fixture.command.capture.allow_text_rewrite = True
    fixture.command.capture.policy.processing_seconds = import_seconds()
    fixture.command.capture.policy.finalization_seconds = finalization_seconds()
    fixture.pipeline.derive = derive_task
    return fixture, src


async def imported(tmp_path, script_of):
    fixture, src = fixture_for(tmp_path)
    fixture.transport.scripted = script_of(src)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published'
    return result, fixture.current().project, src


def entries(result):
    """The project entry tasks in source order."""
    return sorted([task for task in result.tasks if task.entry is not None], key=lambda task: task.entry.index)


def slots(result, task):
    return [attempt.slot for attempt in result.attempts if attempt.task_id == task.id]


def proposals_of(result, task):
    attempts = {attempt.id: attempt for attempt in result.attempts}
    return [value for value in result.proposals if attempts[value.attempt_id].task_id == task.id]


def admitted(result, task):
    return next(value for value in reversed(proposals_of(result, task)) if value.applied_receipt_id is not None)


def admitted_names(result, task):
    """The technology names of the task's admitted reply, by project name."""
    return {item['project']['name']: [value['display'] for value in item['technologies']]
        for item in admitted(result, task).reply.payload}


def cited_lines(result, task, src):
    """{technology name: the lines its admitted value cites} of the task's admitted reply."""
    proposal = admitted(result, task)
    return {proposal.reply.payload[int(field.pointer.split('/')[1])]['technologies'][int(field.pointer.split('/')[3])]
        ['display']: [source_slice([src], span).rstrip('\n') for span in field.evidence]
        for field in proposal.resolved_fields if '/technologies/' in field.pointer}


def cards(project):
    """Each project card's text, by project name, as the document shows it."""
    found = {}
    for block in project.document.blocks():
        if block.type != 'section' or block.presentation is None or block.presentation.view_key != 'projects':
            continue
        lines = [''.join(part.text if not hasattr(part, 'content') else ''.join(child.text for child in part.content)
            for part in child.content) for child in block.children]
        found[next(name for name in STACKS if name in lines[0])] = '\n'.join(lines)
    return found


def notices(project, code):
    return {issue.task_id: issue.message for issue in project.import_issues if issue.code == code}


def repairs(result):
    return [attempt for attempt in result.attempts if attempt.slot in {'primary_repair', 'fallback_repair'}]


@pytest.mark.asyncio
async def test_an_expanded_abbreviation_takes_the_source_form_by_code_and_no_repair_runs(tmp_path):
    result, project, src = await imported(tmp_path, scripted)
    first, second = entries(result)
    # P14 made the expansion a finding and repaired the first group; now no group is repaired.
    assert slots(result, first) == slots(result, second) == ['initial', 'review'] and not repairs(result)
    assert admitted_names(result, first) == {'Atlas': ['Swift', 'TCA', 'Combine'], 'Beacon': ['Swift 4–5', 'WinForms']}
    assert admitted_names(result, second) == {'Comet': ['Kotlin', 'Kubernetes'], 'Delta': ['Rust', 'Docker']}
    assert cited_lines(result, first, src)['TCA'] == [STACKS['Atlas']]
    shown = cards(project)
    assert 'Composable Architecture' not in shown['Atlas'] and 'TCA' in shown['Atlas']
    assert 'Swift 4–5' in shown['Beacon'] and 'WinForms' in shown['Beacon'] and 'Kubernetes' in shown['Comet']
    # A name that takes the source's form is not a value the source does not state: no notice.
    assert not notices(project, 'IMPORT_VALUE_UNBOUND') and not notices(project, 'IMPORT_SOURCE_FALLBACK')


@pytest.mark.asyncio
async def test_a_name_only_another_entry_states_leaves_the_reply_and_a_line_of_the_job_stays(tmp_path):
    # Atlas takes a name of a later project, Delta one of an earlier project; Comet one of its job above its entry, which
    # no entry holds (D155: a project cites its employer and job title there too).
    written = {**STATED, 'Atlas': ['Swift', 'TCA', 'Combine', 'Docker'], 'Comet': ['Kotlin', 'Kubernetes', 'Fastlane'],
        'Delta': ['Rust', 'Docker', 'Combine']}
    cites = {('Atlas', 'Docker'): STACKS['Delta'], ('Delta', 'Combine'): STACKS['Atlas'], ('Comet', 'Fastlane'): TEAM}
    result, project, _src = await imported(tmp_path, lambda src: scripted(src, written, cites=cites))
    first, second = entries(result)
    assert slots(result, first) == slots(result, second) == ['initial', 'review'] and not repairs(result)
    assert admitted_names(result, first)['Atlas'] == ['Swift', 'TCA', 'Combine']
    assert admitted_names(result, second) == {'Comet': ['Kotlin', 'Kubernetes', 'Fastlane'], 'Delta': ['Rust', 'Docker']}
    assert notices(project, 'IMPORT_VALUE_UNBOUND') == {first.id: UNBOUND.format('«Docker»'),
        second.id: UNBOUND.format('«Combine»')}
    shown = cards(project)
    assert 'Docker' not in shown['Atlas'] and 'Combine' not in shown['Delta'] and 'Fastlane' in shown['Comet']
    assert not notices(project, 'IMPORT_SOURCE_FALLBACK')


@pytest.mark.asyncio
async def test_a_name_no_line_states_leaves_the_initial_reply_without_a_repair_and_the_notice_names_it_once(tmp_path):
    written = {**STATED, 'Atlas': ['Swift', 'Bootstrap', 'TCA', 'Combine']}
    result, project, src = await imported(tmp_path, lambda src: scripted(src, written))
    first, second = entries(result)
    # P14 failed the name by code and the first group made two calls more: a repair and its review.
    assert slots(result, first) == slots(result, second) == ['initial', 'review'] and not repairs(result)
    [initial] = proposals_of(result, first)
    assert [(value.pointer, value.text) for value in initial.dropped_values] == [('/0/technologies/1/display', 'Bootstrap')]
    # The record keeps its other names, each cited from its stack line.
    assert admitted_names(result, first)['Atlas'] == ['Swift', 'TCA', 'Combine']
    assert {name: lines for name, lines in cited_lines(result, first, src).items() if name in {'TCA', 'Combine'}} == {
        'TCA': [STACKS['Atlas']], 'Combine': [STACKS['Atlas']]}
    assert notices(project, 'IMPORT_VALUE_UNBOUND') == {first.id: UNBOUND.format('«Bootstrap»')}
    assert 'Bootstrap' not in cards(project)['Atlas'] and 'Combine' in cards(project)['Atlas']
    assert not notices(project, 'IMPORT_SOURCE_FALLBACK')


def role_review(value):
    """The first group's first review fails Atlas's role; every other check holds."""
    shown = value['semanticContext']['proposal']['payload']
    atlas = isinstance(shown, list) and bool(shown) and ((shown[0] or {}).get('project') or {}).get('name') == 'Atlas'
    def verdict_of(check):
        failing = atlas and check.get('pointer') == '/0/role' and check.get('value') == 'Senior iOS developer'
        return 'violation' if failing else None
    return satisfied(value, verdict_of)


@pytest.mark.asyncio
async def test_the_notice_still_names_the_lost_name_when_a_repair_runs_for_another_reason(tmp_path):
    # Beacon's last name is one no line states. The review fails Atlas's role; the repair corrects it and lists Beacon's
    # names without the lost one.
    written = {**STATED, 'Beacon': ['Swift 4–5', 'WinForms', 'Bootstrap']}
    result, project, _src = await imported(tmp_path, lambda src: scripted(src, written, repaired=STATED,
        roles={'Atlas': 'iOS developer'}, review=role_review))
    first, second = entries(result)
    assert slots(result, first) == ['initial', 'review', 'primary_repair', 'replacement_review']
    assert slots(result, second) == ['initial', 'review']
    initial, repair = proposals_of(result, first)
    assert [value.text for value in initial.dropped_values] == ['Bootstrap']
    # The repair lost nothing itself and keeps what the first reply lost; it is the reply admitted.
    assert [value.text for value in repair.dropped_values] == ['Bootstrap'] and admitted(result, first) is repair
    assert repair.reply.payload[0]['role'] == 'iOS developer'
    assert notices(project, 'IMPORT_VALUE_UNBOUND') == {first.id: UNBOUND.format('«Bootstrap»')}
    assert 'Bootstrap' not in cards(project)['Beacon'] and 'WinForms' in cards(project)['Beacon']


@pytest.mark.asyncio
async def test_an_import_stored_before_the_check_resumes_with_its_stored_review(tmp_path, monkeypatch):
    # The earlier build: no respelling and no technology left out by code. With one call at a time the projects block
    # runs whole.
    monkeypatch.setattr(template_proposals, 'owned_types', lambda _types: frozenset())
    fixture, src = fixture_for(tmp_path, concurrency=1)
    script = scripted(src)
    def crashing(request, value):
        answer = script(request, value)
        if 'targets' in value and value['semanticContext']['taskInput']['declaration']['id'] == 'projects':
            # The process ends right after the projects review's return is saved.
            fixture.transport.fail_at = 'return'
        return answer
    fixture.transport.scripted = crashing
    with pytest.raises(SystemExit):
        await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    previous = fixture.current().pre_draft.template_operations[0]
    stored = next(value for value in previous.proposals
        if next(attempt for attempt in previous.attempts if attempt.id == value.attempt_id).slot == 'initial'
        and value.reply is not None and any(item.get('technologies') for item in value.reply.payload or []
            if isinstance(item, dict)))
    monkeypatch.undo()
    fixture.transport.fail_at, fixture.transport.scripted = None, script
    pipeline = fixture.restart()
    pipeline.derive = derive_task
    result = await pipeline.run(fixture.project, resume_command(previous), admitted=fixture.admitted)
    assert result.state == 'published'
    task = next(value for value in result.tasks if value.block_id == 'projects')
    # The stored proposal and review decide: no new call, no notice, and the names stay as the earlier build kept them.
    assert slots(result, task) == ['initial', 'review']
    assert [value.proposal_hash for value in result.proposals if value.attempt_id == stored.attempt_id] == [stored.proposal_hash]
    assert admitted_names(result, task) == WRITTEN
    shown = fixture.current().project
    assert EXPANDED in cards(shown)['Atlas']
    assert not notices(shown, 'IMPORT_VALUE_UNBOUND') and not notices(shown, 'IMPORT_SOURCE_FALLBACK')
