"""D156: review findings left after the repair are warnings. A task keeps every admitted value no finding names as
unsupported; a withdrawn value's own lines and the lines an omission names show in its own entry; a fallback reaches
no other value or entry, and an entry group without a usable reply shows only its own lines.

The source is one employment with four projects; since D155 every project cites the employer and job-title lines,
which lie outside the entries' lines."""

import copy

import pytest

from packages.resume_core.models.contracts import Source
from packages.resume_core.hashing import sha256
from packages.resume_core.project_limits import finalization_seconds, import_seconds
from packages.resume_core.sources import source_slice
from packages.resume_core.templates.operations import derive_task
from tests.templates.entry_fixtures import ref_of
from tests.templates.evidence_references import expanded_checks, model_targets
from tests.templates.generic_fixtures import (block_reply, date, generic_package, generic_script, identity, job, period,
                                              span)
from tests.templates.template_runtime_fixtures import EmploymentFixture
from tests.templates.test_template_retry import failure

LINES = ['Alex Example', 'Mobile engineer', 'Example Labs, 2021–2025', 'Senior iOS developer',
    'Atlas, 2021–2022', 'Built the Atlas booking screens.', 'Atlas used Swift Concurrency throughout.',
    'Cut the Atlas checkout time by 30%.',
    'Beacon, 2022–2023', 'Built the Beacon map module.', 'Wrote the Beacon offline cache.',
    'Reduced the Beacon crash rate by half.',
    'Comet, 2023–2024', 'Built the Comet payments flow.', 'Raised the Comet conversion by 10%.',
    'Delta, 2024–2025', 'Built the Delta onboarding.', 'Grew the Delta retention by 5%.']
OMITTED = 'Atlas used Swift Concurrency throughout.'
NAMES = ['Atlas', 'Beacon', 'Comet', 'Delta']
BOUNDS = {'Atlas': ('Atlas, 2021–2022', 'Cut the Atlas checkout time by 30%.'),
    'Beacon': ('Beacon, 2022–2023', 'Reduced the Beacon crash rate by half.'),
    'Comet': ('Comet, 2023–2024', 'Raised the Comet conversion by 10%.'),
    'Delta': ('Delta, 2024–2025', 'Grew the Delta retention by 5%.')}


def project(name, years, tasks, results):
    start, end = years.split('–')
    when = period(years, date(start, int(start)), date(end, int(end)), False)
    return job('Example Labs', 'Senior iOS developer', when, project={'name': name, 'description': None}, tasks=tasks,
        results=results)


PROJECTS = {
    'Atlas': project('Atlas', '2021–2022', ['Built the Atlas booking screens.'], ['Cut the Atlas checkout time by 30%.']),
    'Beacon': project('Beacon', '2022–2023', ['Built the Beacon map module.', 'Wrote the Beacon offline cache.'],
        ['Reduced the Beacon crash rate by half.']),
    'Comet': project('Comet', '2023–2024', ['Built the Comet payments flow.'], ['Raised the Comet conversion by 10%.']),
    'Delta': project('Delta', '2024–2025', ['Built the Delta onboarding.'], ['Grew the Delta retention by 5%.'])}


def employment_source():
    raw = ('\n'.join(LINES) + '\n').encode()
    value = Source(id='source-papers', revision=1, originalName='projects.txt', mimeType='text/plain',
        byteSha256=sha256(raw), byteRef='sources/papers.txt', parser='text', parserVersion='1',
        units=[{'id': 'unit-papers', 'revision': 1, 'order': 0, 'text': raw.decode(),
            'location': {'kind': 'pasted', 'index': 0, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []}], overlays=[], warnings=[])
    return value, raw


def review(src, value, finding):
    """The model's review: `finding(check, names)` gives a failing check's disposition and the source texts it cites;
    names are the projects of the reviewed entry."""
    entry = value['semanticContext'].get('taskInput', {}).get('entry')
    names = [part['title'] for part in entry['parts']] if entry else []
    results = []
    for target, check in zip(model_targets(value), expanded_checks(value), strict=True):
        found = finding(check, names)
        disposition, texts = found if found else ('satisfied', ())
        results.append({'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': disposition,
            'reason': 'Замечание проверки.' if found else '', 'actionable': bool(found),
            'evidence': [span(src, text) for text in texts]})
    return {'results': results}


def scripted(src, finding=lambda check, names: None, *, cites=None, entry=None):
    """Replies of the whole import: the projects block outlined as one entry per project and run in two groups, each
    entry answering its projects; `cites` names list evidence per project and `entry(names, value, build)` may give a
    group another reply (`build(request)` makes the scripted one)."""
    block = next(value for value in generic_package().definition.blocks if value.id == 'projects')
    others = generic_script(src, {'identity': identity('Alex Example', 'Mobile engineer', 'other', 'Mobile engineer')})
    def script(request, value):
        if 'targets' in value:
            return review(src, value, finding)
        if value.get('declaration', {}).get('id') != 'projects' or value.get('slot') == 'outline_review':
            return others(request, value)
        if value.get('slot') == 'outline':
            return {'entries': [{'title': name, 'first': ref_of(value, first), 'last': ref_of(value, last)}
                for name, (first, last) in BOUNDS.items()]}
        names = [part['title'] for part in value['entry']['parts']]
        moved = {'/' + str(position) + pointer: phrases for position, name in enumerate(names)
            for pointer, phrases in (cites or {}).get(name, {}).items()}
        def build(request):
            return block_reply(block, copy.deepcopy([PROJECTS[name] for name in names]), src, moved, request)
        return entry(names, value, build) if entry else build(value)
    return script


async def imported(tmp_path, script_of):
    src, raw = employment_source()
    fixture = EmploymentFixture(tmp_path, captured=generic_package(), src=src, original_bytes=raw, cap=60,
        fallback=False, concurrency=2)
    fixture.command.capture.allow_text_rewrite = True
    fixture.command.capture.policy.processing_seconds = import_seconds()
    fixture.command.capture.policy.finalization_seconds = finalization_seconds()
    fixture.pipeline.derive = derive_task
    fixture.transport.scripted = script_of(src)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published'
    return fixture, result, fixture.current().project


def cards(project):
    """Each project card's lines by its project name, as the document shows them."""
    found = {}
    for block in project.document.blocks():
        if block.type != 'section' or block.presentation is None or block.presentation.view_key != 'projects':
            continue
        lines = [''.join(part.text if not hasattr(part, 'content') else ''.join(child.text for child in part.content)
            for part in child.content) for child in block.children]
        name = next(name for name in NAMES if any(name in line for line in lines[:1]))
        found[name] = lines
    return found


def outside(project):
    """The source lines the projects block shows outside its cards."""
    return [block.content[0].text for region in project.document.regions for block in region.blocks
        if block.type == 'paragraph' and block.presentation.view_key == 'projects' and block.content[0].citations]


def entries(result):
    """The project entry tasks in source order, with their results."""
    results = {value.task_id: value for value in result.task_results}
    tasks = sorted([task for task in result.tasks if task.entry is not None], key=lambda task: task.entry.index)
    return [(task, results[task.id]) for task in tasks]


def whole(card, name):
    """A card shows its employer, role, tasks and results."""
    project = PROJECTS[name]
    text = '\n'.join(card)
    return ('Example Labs' in card[0] and 'Роль: Senior iOS developer' in text
        and all(task['value'].rstrip('.') in text for task in project['tasks'])
        and all(result['value'].rstrip('.') in text for result in project['results']))


def is_scope(check):
    return check.get('kind') == 'scope'


def cell_of(result, task, pointer):
    """The cell the task's admitted reply put at the pointer."""
    attempts = {attempt.id: attempt for attempt in result.attempts}
    proposal = next(value for value in result.proposals if value.applied_receipt_id is not None
        and attempts[value.attempt_id].task_id == task.id)
    field = next(field for field in proposal.resolved_fields if field.pointer == pointer)
    return next(value for value in result.allocations if value.item_handle == field.item_handle).cell_ids[field.field_key]


@pytest.mark.asyncio
async def test_a_coverage_finding_left_after_the_repair_keeps_every_card_and_adds_its_line_to_the_entry(tmp_path):
    # terra-high-rw-51: the first group's reviews named an omission (and a task given as a result); the repair did not
    # fix it; the fallback then emptied two cards of the group.
    def finding(check, names):
        if is_scope(check) and check.get('ruleId') == 'application:source-coverage' and 'Atlas' in names:
            return 'violation', [OMITTED]
        if (check.get('ruleId') == 'projects-task_result_separation'
                and check.get('value') == 'Cut the Atlas checkout time by 30%.'):
            return 'violation', []
        return None
    _fixture, result, project = await imported(tmp_path, lambda src: scripted(src, finding))
    first, second = entries(result)
    # The first group ran its repair; the findings stay, so it is kept with a warning and nothing is withdrawn.
    assert [attempt.slot for attempt in result.attempts if attempt.task_id == first[0].id] == [
        'initial', 'review', 'primary_repair', 'replacement_review']
    assert (first[0].state, first[1].disposition) == ('accepted', 'source_fallback')
    assert (second[0].state, second[1].disposition) == ('accepted', 'admitted')
    shown = cards(project)
    assert set(shown) == set(NAMES) and all(whole(shown[name], name) for name in NAMES)
    # The omitted line shows once, inside the Atlas card, after its values.
    assert shown['Atlas'][-1] == OMITTED and sum(line == OMITTED for lines in shown.values() for line in lines) == 1
    assert OMITTED not in ''.join(line for name in ['Beacon', 'Comet', 'Delta'] for line in shown[name])
    # The task given as a result stays a result: a category finding withdraws nothing.
    assert 'Cut the Atlas checkout time by 30%' in '\n'.join(shown['Atlas'])
    issue = next(issue for issue in project.import_issues if issue.task_id == first[0].id)
    assert issue.code == 'IMPORT_SOURCE_FALLBACK' and 'scope-' + first[0].id in issue.target_ids
    assert issue.block_ids
    assert not outside(project)


@pytest.mark.asyncio
async def test_a_finding_that_one_task_is_unsupported_withdraws_it_alone_and_shows_its_line_in_its_card(tmp_path):
    # rw-51: Terra cites every task line for each task, so the lines of one withdrawn value took its siblings, and their
    # lines the rest of the card.
    both = ['Built the Beacon map module.', 'Wrote the Beacon offline cache.']
    cites = {'Beacon': {'/tasks/0/value': both, '/tasks/1/value': both}}
    def finding(check, _names):
        if check.get('ruleId') == 'projects-support' and check.get('value') == 'Built the Beacon map module.':
            return 'violation', []
        return None
    _fixture, result, project = await imported(tmp_path, lambda src: scripted(src, finding, cites=cites))
    first, second = entries(result)
    assert (first[0].state, first[1].disposition) == ('accepted', 'source_fallback')
    assert (second[0].state, second[1].disposition) == ('accepted', 'admitted')
    shown = cards(project)
    assert all(whole(shown[name], name) for name in ['Atlas', 'Comet', 'Delta'])
    beacon = '\n'.join(shown['Beacon'])
    # The withdrawn task's own line shows once, in the Beacon card; its sibling, the result, the employer and role stay.
    assert shown['Beacon'][-1] == 'Built the Beacon map module.' and beacon.count('Built the Beacon map module') == 1
    assert 'Wrote the Beacon offline cache' in beacon and 'Reduced the Beacon crash rate by half' in beacon
    assert 'Example Labs' in shown['Beacon'][0] and 'Роль: Senior iOS developer' in beacon
    assert first[1].source_spans and not first[1].value.get('leftoverOnly')
    # The task is no fact; the warning names it.
    withdrawn = cell_of(result, first[0], '/1/tasks/0/value')
    issue = next(issue for issue in project.import_issues if issue.task_id == first[0].id)
    assert withdrawn in issue.target_ids and issue.block_ids
    assert withdrawn not in {cell.id for record in project.facts.extensions for cell in record.cells}
    assert not outside(project)


@pytest.mark.asyncio
async def test_a_finding_on_the_shared_employer_and_title_lines_withdraws_them_from_no_other_card(tmp_path):
    # D155: every card cites the employer and job-title lines; a finding on one card's company and role reached every
    # card that cites them.
    def finding(check, names):
        if (names[:1] == ['Atlas'] and check.get('pointer') in {'/0/company', '/0/role'}
                and check.get('ruleId') == 'projects-evidence'):
            return 'violation', ['Example Labs, 2021–2025']
        return None
    _fixture, result, project = await imported(tmp_path, lambda src: scripted(src, finding))
    first, _second = entries(result)
    assert (first[0].state, first[1].disposition) == ('accepted', 'source_fallback')
    shown = cards(project)
    assert all(whole(shown[name], name) for name in ['Beacon', 'Comet', 'Delta'])
    atlas = '\n'.join(shown['Atlas'])
    # Atlas alone loses its company and role; its tasks and result stay. The shared lines are not its own, so it shows
    # no copy of them, and nothing shows outside the cards.
    assert shown['Atlas'][0] == 'Atlas' and 'Роль:' not in atlas and 'Example Labs' not in atlas
    assert 'Built the Atlas booking screens' in atlas and 'Cut the Atlas checkout time by 30%' in atlas
    assert not first[1].source_spans and not outside(project)
    issue = next(issue for issue in project.import_issues if issue.task_id == first[0].id)
    assert {cell_of(result, first[0], '/0/company'), cell_of(result, first[0], '/0/role')} <= set(issue.target_ids)


@pytest.mark.asyncio
async def test_an_entry_group_without_a_usable_reply_shows_its_own_lines_and_the_other_cards_stay_whole(tmp_path):
    # Finding 6: a group's refused reply cited the whole unit; its copy replaced every card citing that unit.
    def entry(names, value, build):
        if 'Comet' not in names:
            return build(value)
        if value['slot'] != 'initial':
            # Its repairs never answer (finding 8), so the group keeps no usable reply.
            failure('STALLED')
        reply = build(value)
        whole_unit = next(option['span'] for option in value['evidence'] if option['text'] == '\n'.join(LINES) + '\n')
        for field in reply['fields']:
            field['evidence'] = [whole_unit]
        # A value no line states, sent without its entry: the coordinator cannot cite it and refuses the reply.
        reply['payload'][0]['project']['name'] = 'Unstated Name'
        reply['fields'] = [field for field in reply['fields'] if field['pointer'] != '/0/project/name']
        return reply
    _fixture, result, project = await imported(tmp_path, lambda src: scripted(src, entry=entry))
    first, second = entries(result)
    assert (first[0].state, first[1].disposition) == ('accepted', 'admitted')
    assert (second[0].state, second[1].disposition) == ('source_fallback', 'source_fallback')
    codes = {attempt.error_code for attempt in result.attempts if attempt.task_id == second[0].id}
    assert codes == {'IMPORT_PROPOSAL_INVALID', 'STALLED'}
    own = [value.model_dump() for value in second[0].entry.spans]
    assert [value.model_dump() for value in second[1].source_spans] == own
    shown = cards(project)
    assert set(shown) == {'Atlas', 'Beacon'} and all(whole(shown[name], name) for name in shown)
    # The group's own lines show once, after the cards; no other line of the unit is copied.
    assert outside(project) == ['\n'.join(LINES[12:])]


@pytest.mark.asyncio
async def test_a_whole_block_that_kept_no_value_still_shows_its_cited_line(tmp_path):
    # Unchanged: a block without entries whose only value is withdrawn shows the line it cited, in its own place.
    table = {'summary': ({'text': 'Mobile engineer building iOS apps.'}, {'/text': 'Mobile engineer'})}
    def script_of(src):
        projects = scripted(src, lambda check, _names: ('violation', []) if check.get('pointer') == '/text'
            and check.get('ruleId') == 'application:semantic-support' else None)
        summary = generic_script(src, table)
        def script(request, value):
            if 'targets' not in value and value.get('declaration', {}).get('id') == 'summary':
                return summary(request, value)
            return projects(request, value)
        return script
    _fixture, result, project = await imported(tmp_path, script_of)
    task = next(task for task in result.tasks if task.block_id == 'summary')
    value = next(value for value in result.task_results if value.task_id == task.id)
    assert (task.state, value.disposition) == ('source_fallback', 'source_fallback')
    assert [source_slice(project.sources, span) for span in value.source_spans] == ['Mobile engineer\n']
    paragraphs = [block for region in project.document.regions for block in region.blocks
        if block.presentation is not None and block.presentation.view_key == 'summary' and block.type == 'paragraph']
    assert [block.content[0].text for block in paragraphs] == ['Mobile engineer'] and paragraphs[0].content[0].citations
    issue = next(issue for issue in project.import_issues if issue.task_id == task.id)
    assert issue.code == 'IMPORT_SOURCE_FALLBACK' and issue.message.startswith('Показан исходный текст')
    assert all(whole(lines, name) for name, lines in cards(project).items()) and len(cards(project)) == 4


@pytest.mark.asyncio
async def test_a_value_whose_owner_the_review_doubts_shows_its_line_under_no_card(tmp_path):
    # B03 inside an entry group: a claim the ownership check cannot link to its project is no fact of that card, so its
    # line shows outside the cards, and the card keeps the rest.
    def finding(check, names):
        if (names[:1] == ['Atlas'] and check.get('kind') == 'relation' and check.get('subject') == '/1/tasks/1'
                and check.get('ruleId') == 'projects-claim_ownership'):
            return 'violation', []
        return None
    _fixture, result, project = await imported(tmp_path, lambda src: scripted(src, finding))
    first, _second = entries(result)
    assert (first[0].state, first[1].disposition) == ('accepted', 'source_fallback')
    assert first[1].value['unowned'] and set(first[1].value['unowned']) <= {
        value for value in first[1].value['sourceTexts']}
    shown = cards(project)
    assert all(whole(shown[name], name) for name in ['Atlas', 'Comet', 'Delta'])
    beacon = '\n'.join(shown['Beacon'])
    assert 'Wrote the Beacon offline cache' not in beacon and 'Built the Beacon map module' in beacon
    assert 'Example Labs' in shown['Beacon'][0] and 'Роль: Senior iOS developer' in beacon
    assert outside(project) == ['Wrote the Beacon offline cache.']
