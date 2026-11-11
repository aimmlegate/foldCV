"""D164, point 14 of T4: the technologies an entry owns are read against the entry's lines. A name the lines state as
written, case and spacing aside, or by a catalog alias passes; one they write with other spaces or punctuation takes
their spelling and cites its line; any other is one finding of the template's own rule, settled by code before the
review, which the repair gets and which stays a warning when the repair leaves it (synthetic text only)."""

import json

import pytest

from packages.resume_core.hashing import sha256
from packages.resume_core.importing import template_proposals, template_review
from packages.resume_core.importing.template_completion import complete_reply
from packages.resume_core.importing.template_identity import evidence_options
from packages.resume_core.importing.template_import import (admit_operation, capture_task_input, dispatch_attempt,
                                                            record_return, reserve_attempt)
from packages.resume_core.importing.template_proposals import parse_proposal
from packages.resume_core.importing.template_technologies import (foreign_technologies, named, owned_types,
                                                                  source_spelling)
from packages.resume_core.models.contracts import Source
from packages.resume_core.project_limits import finalization_seconds, import_seconds
from packages.resume_core.sources import capture_span, line_spans
from packages.resume_core.template_capture import item_identities
from packages.resume_core.templates.operations import derive_task
from tests.templates.entry_fixtures import ref_of
from tests.templates.evidence_references import model_targets
from tests.templates.generic_fixtures import (block_reply, date, generic_package, generic_script, identity, job, period,
                                              satisfied)
from tests.templates.pipeline_fixtures import NOW, cleaned, owner, resume_command, setup_operation, usage
from tests.templates.template_runtime_fixtures import EmploymentFixture
from tests.templates.test_reply_completion import NO_OFFERS, entry, offered, projects, reply

TYPES = owned_types(generic_package().definition.fact_types)
EXPANDED = 'TCA (Composable Architecture)'
FINDING = 'Строки этой записи не называют технологию «' + EXPANDED + '».'

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


def test_only_the_technologies_an_entry_owns_are_respelled():
    _options, table, _lines = offered(TEXT)
    programming = next(block for block in generic_package().definition.blocks if block.id == 'programming')
    skills = {'schemaVersion': 3, 'payload': {'items': ['Win-Forms']}, 'discoveries': None, 'fields': [], 'lineage': None,
        'relations': None}
    assert (complete_reply(skills, programming.bindings, table, NO_OFFERS, technologies=TYPES)
        == complete_reply(skills, programming.bindings, table, NO_OFFERS))
    # A name read from the editor's cells stays as it is.
    payload = [job('North Studio', 'iOS developer', None, technologies=['Win-Forms'])]
    given = [{**entry('/0/technologies/0/display', []), 'effectiveCells': ['E1']}]
    assert completed(payload, given, technologies=TYPES)['payload'][0]['technologies'][0]['display'] == 'Win-Forms'


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
    # abbreviation the reply expanded does not.
    text = 'Example Labs — backend engineer\n2020–2023\nImplemented queue processing.\nPython\nStack: Go, TCA\n'
    when = period('2020–2023', date('2020', 2020), date('2023', 2023), False)
    payload = [job('Example Labs', 'backend engineer', when, technologies=['Python', 'Golang', 'TCA (Task Coordination API)'],
        tasks=['Implemented queue processing.'])]
    proposal, operation, src = parsed(text, payload, {'/0/technologies/1/display': 'Stack: Go, TCA',
        '/0/technologies/2/display': 'Stack: Go, TCA'})
    found = foreign_technologies(proposal, item_identities(operation), [src], TYPES)
    assert [field.pointer for field in found] == ['/0/technologies/2/display']


# ------------------------------------------------------------------------------------------- the review and the repair

def project(name, technologies):
    start, end = YEARS[name].split('–')
    return job('Example Labs', 'Senior iOS developer', period(YEARS[name], date(start, int(start)), date(end, int(end)), False),
        project={'name': name, 'description': None}, technologies=technologies, tasks=[TASKS[name]])


def scripted(src, written=WRITTEN, *, repaired=None, cites=None):
    """Replies of the whole import. Outlined, the projects block has one entry per project; each project lists
    written[name], or repaired[name] in a repair, every name cited from the project's stack line unless cites names
    another line. Every check the model is asked holds."""
    block = projects()
    others = generic_script(src, {'identity': identity('Alex Example', 'Mobile engineer', 'other', 'Mobile engineer')})
    def script(request, value):
        if 'targets' in value:
            return satisfied(value)
        if value.get('declaration', {}).get('id') != 'projects' or value.get('slot') == 'outline_review':
            return others(request, value)
        if value.get('slot') == 'outline':
            return {'entries': [{'title': name, 'first': ref_of(value, name + ', ' + YEARS[name]),
                'last': ref_of(value, TASKS[name])} for name in STACKS]}
        names = [part['title'] for part in value['entry']['parts']] if 'entry' in value else list(STACKS)
        listed = repaired if repaired is not None and value.get('slot') != 'initial' else written
        moved = {'/' + str(position) + '/technologies/' + str(index) + '/display': (cites or {}).get((name, technology),
            STACKS[name]) for position, name in enumerate(names) for index, technology in enumerate(listed[name])}
        return block_reply(block, [project(name, listed[name]) for name in names], src, moved, value)
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
    return result, fixture.current().project


def entries(result):
    """The project entry tasks in source order."""
    return sorted([task for task in result.tasks if task.entry is not None], key=lambda task: task.entry.index)


def slots(result, task):
    return [attempt.slot for attempt in result.attempts if attempt.task_id == task.id]


def review_of(result, task, slot='review'):
    attempt = next(value for value in result.attempts if value.task_id == task.id and value.slot == slot)
    return next(value.value for value in result.review_inputs if value.attempt_id == attempt.id)


def settled_by_pointer(result, review):
    """{pointer: [(rule, disposition, reason)]} of the checks the coordinator settled in a review input."""
    proposal = next(value for value in result.proposals if value.proposal_hash == review.proposal_hash)
    handles = {allocation.item_handle: allocation for allocation in review.handle_map}
    pointers = {handles[field.item_handle].cell_ids[field.field_key]: field.pointer for field in proposal.resolved_fields}
    found = {}
    for check in review.settled:
        if check.target_id in pointers:
            found.setdefault(pointers[check.target_id], []).append((check.rule_id, check.disposition, check.reason))
    return found


def failing(settled):
    return {pointer: [value for value in values if value[1] != 'satisfied'] for pointer, values in settled.items()
        if any(value[1] != 'satisfied' for value in values)}


def admitted_names(result, task):
    """The technology names of the task's admitted reply, by project name."""
    attempts = {attempt.id: attempt for attempt in result.attempts}
    proposal = next(value for value in reversed(result.proposals) if value.applied_receipt_id is not None
        and attempts[value.attempt_id].task_id == task.id)
    return {item['project']['name']: [value['display'] for value in item['technologies']] for item in proposal.reply.payload}


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


def warnings(project):
    return [issue for issue in project.import_issues if issue.code == 'IMPORT_SOURCE_FALLBACK']


@pytest.mark.asyncio
async def test_an_expanded_abbreviation_is_one_finding_by_code_and_its_repair_keeps_the_source_form(tmp_path):
    repaired = {**WRITTEN, 'Atlas': ['Swift', 'TCA', 'Combine']}
    result, project = await imported(tmp_path, lambda src: scripted(src, repaired=repaired))
    first, second = entries(result)
    # The first group (Atlas and Beacon) is repaired once; the second has nothing to repair.
    assert slots(result, first) == ['initial', 'review', 'primary_repair', 'replacement_review']
    assert slots(result, second) == ['initial', 'review']
    review = review_of(result, first)
    settled = settled_by_pointer(result, review)
    assert failing(settled) == {'/0/technologies/1/display': [('projects-support', 'violation', FINDING)]}
    # The value's other checks hold, so the model is asked nothing about it.
    cell = next(check.target_id for check in review.settled if check.disposition == 'violation')
    assert len(settled['/0/technologies/1/display']) == sum(target.target_id == cell for target in review.targets) > 1
    assert cell not in {target['targetId'] for target in model_targets(review.model_dump(mode='json', by_alias=True))}
    # The repair is told which value and why, and writes the name as the source does.
    repair = next(attempt.request_value for attempt in result.attempts if attempt.task_id == first.id
        and attempt.slot == 'primary_repair')
    assert [(value['ruleId'], value.get('pointer'), value['reason']) for value in repair['feedback']] == [
        ('projects-support', '/0/technologies/1/display', FINDING)]
    assert not failing(settled_by_pointer(result, review_of(result, first, 'replacement_review')))
    # Beacon's names took the source's spelling without a finding; the alias and the verbatim names pass untouched.
    assert admitted_names(result, first) == {'Atlas': ['Swift', 'TCA', 'Combine'], 'Beacon': ['Swift 4–5', 'WinForms']}
    assert admitted_names(result, second) == {'Comet': ['Kotlin', 'Kubernetes'], 'Delta': ['Rust', 'Docker']}
    later = settled_by_pointer(result, review_of(result, second))
    assert not failing(later) and '/0/technologies/1/display' not in later and '/1/technologies/1/display' in later
    shown = cards(project)
    assert 'Composable Architecture' not in shown['Atlas'] and 'TCA' in shown['Atlas']
    assert 'Swift 4–5' in shown['Beacon'] and 'WinForms' in shown['Beacon'] and 'Kubernetes' in shown['Comet']
    assert not warnings(project)


@pytest.mark.asyncio
async def test_a_name_only_another_entry_states_is_a_finding_and_a_line_of_the_job_is_not(tmp_path):
    # Atlas takes a name of a later project, Delta one of an earlier project; Comet one of its job above its entry, which
    # no entry holds (D155: a project cites its employer and job title there too).
    written = {**WRITTEN, 'Atlas': ['Swift', 'TCA', 'Combine', 'Docker'], 'Comet': ['Kotlin', 'Kubernetes', 'Fastlane'],
        'Delta': ['Rust', 'Docker', 'Combine']}
    # The scripted repair keeps the number of names: it gives the place to a name the entry states.
    repaired = {**written, 'Atlas': ['Swift', 'TCA', 'Combine', 'Realm'], 'Delta': ['Rust', 'Docker', 'Tokio']}
    cites = {('Atlas', 'Docker'): STACKS['Delta'], ('Delta', 'Combine'): STACKS['Atlas'], ('Comet', 'Fastlane'): TEAM}
    result, project = await imported(tmp_path, lambda src: scripted(src, written, repaired=repaired, cites=cites))
    first, second = entries(result)
    finding = 'Строки этой записи не называют технологию «{}».'.format
    assert failing(settled_by_pointer(result, review_of(result, first))) == {
        '/0/technologies/3/display': [('projects-support', 'violation', finding('Docker'))]}
    assert failing(settled_by_pointer(result, review_of(result, second))) == {
        '/1/technologies/2/display': [('projects-support', 'violation', finding('Combine'))]}
    assert admitted_names(result, first)['Atlas'] == ['Swift', 'TCA', 'Combine', 'Realm']
    assert admitted_names(result, second) == {'Comet': ['Kotlin', 'Kubernetes', 'Fastlane'], 'Delta': ['Rust', 'Docker', 'Tokio']}
    shown = cards(project)
    assert 'Docker' not in shown['Atlas'] and 'Combine' not in shown['Delta'] and 'Fastlane' in shown['Comet']
    assert not warnings(project)


@pytest.mark.asyncio
async def test_a_repair_that_leaves_the_name_gives_one_warning_and_the_card_keeps_its_other_values(tmp_path):
    result, project = await imported(tmp_path, lambda src: scripted(src, repaired=WRITTEN))
    first, second = entries(result)
    assert slots(result, first) == ['initial', 'review', 'primary_repair', 'replacement_review']
    assert failing(settled_by_pointer(result, review_of(result, first, 'replacement_review'))) == {
        '/0/technologies/1/display': [('projects-support', 'violation', FINDING)]}
    [issue] = warnings(project)
    assert issue.task_id == first.id and FINDING in issue.message
    task_result = next(value for value in result.task_results if value.task_id == first.id)
    assert (first.state, task_result.disposition) == ('accepted', 'source_fallback')
    # The name is withdrawn alone: Atlas keeps its other names, its task and its role; Beacon is whole.
    shown = cards(project)
    assert EXPANDED not in shown['Atlas'] and 'Swift' in shown['Atlas'] and 'Combine' in shown['Atlas']
    assert TASKS['Atlas'].rstrip('.') in shown['Atlas'] and 'Senior iOS developer' in shown['Atlas']
    assert 'WinForms' in shown['Beacon'] and TASKS['Beacon'].rstrip('.') in shown['Beacon']


@pytest.mark.asyncio
async def test_an_import_stored_before_the_check_resumes_with_its_stored_review(tmp_path, monkeypatch):
    # The earlier build: no respelling and no finding by code. With one call at a time the projects block runs whole.
    monkeypatch.setattr(template_proposals, 'owned_types', lambda _types: frozenset())
    monkeypatch.setattr(template_review, 'owned_types', lambda _types: frozenset())
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
    # The stored proposal and review decide: no new call, no finding, and the names stay as the earlier build kept them.
    assert slots(result, task) == ['initial', 'review']
    assert [value.proposal_hash for value in result.proposals if value.attempt_id == stored.attempt_id] == [stored.proposal_hash]
    assert not failing(settled_by_pointer(result, review_of(result, task)))
    assert admitted_names(result, task) == WRITTEN
    assert EXPANDED in cards(fixture.current().project)['Atlas']
