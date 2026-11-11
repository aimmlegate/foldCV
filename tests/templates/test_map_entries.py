"""T4 of D158: a block of entries runs the map's entries, in at most three groups and with no outline; each entry reads
its own lines, and the coordinator puts each item's employer, job title and period from the map's header lines into
the reply before completion. A header value no line states is dropped and named."""

from copy import deepcopy

import pytest

from packages.resume_core.hashing import digest
from packages.resume_core.importing.template_map import header_fields, merge_header, parse_period
from packages.resume_core.models.template_import import EntryHeader, EntryPart, EntryScope, HeaderValue
from packages.resume_core.templates.replies import MAPPED_PROPOSAL_VERSION, PROPOSAL_PROTOCOL, proposal_protocol
from tests.templates.generic_fixtures import TABLES, generic_import, generic_package
from tests.templates.test_map_blocks import document
from tests.templates.test_source_map import LINES, cv_source, line, table


@pytest.mark.parametrize('text,start,end,ongoing', [
    ('03.2020 – 11.2023', ('03.2020', 2020, 3), ('11.2023', 2023, 11), False),
    ('2016 – 2019', ('2016', 2016, None), ('2019', 2019, None), False),
    ('Март 2020 — по настоящее время', ('03.2020', 2020, 3), None, True),
    ('since Jan 2021, present', ('01.2021', 2021, 1), None, True),
    ('сентябрь 2018 – декабрь 2019', ('09.2018', 2018, 9), ('12.2019', 2019, 12), False),
    ('2015', ('2015', 2015, None), None, False),
    ('2010–2011-10', ('2010', 2010, None), ('10.2011', 2011, 10), False),
])
def test_a_period_reads_its_dates_from_the_wording_the_cv_gives_it(text, start, end, ongoing):
    period = parse_period(text)
    as_date = lambda value: None if value is None else (value['raw'], value['year'], value['month'])
    assert (period['raw'], as_date(period['start']), as_date(period['end']), period['ongoing']) == (
        ' '.join(text.split()), start, end, ongoing)


@pytest.mark.parametrize('text', ['no dates here', '2020 – 2016', ''])
def test_a_period_without_a_date_or_running_backwards_reads_as_none(text):
    assert parse_period(text) is None


def test_the_header_fills_the_employment_fields_the_bindings_name():
    package = generic_package()
    blocks = {block.id: block for block in package.definition.blocks}
    assert header_fields(blocks['projects'], package.definition) == {'employer': ['company'], 'jobTitle': ['role'],
        'period': ['period']}
    assert header_fields(blocks['education'], package.definition) == {}


def scoped(offered, parts):
    """An entry scope of the given parts: (title, own line texts, header {key: (value, line text)})."""
    built = []
    for title, own, header in parts:
        values = {key: HeaderValue(value=value, span=offered[line(offered, text)].span) for key, (value, text) in header.items()}
        built.append(EntryPart(title=title, spans=[offered[line(offered, text)].span for text in own],
            header=EntryHeader(employer=values.get('employer'), jobTitle=values.get('jobTitle'), period=values.get('period'))))
    return EntryScope(index=1, title=', '.join(part.title for part in built), spans=[span for part in built for span in part.spans],
        parts=built, origin='map')


def item(company=None, role=None, period=None, tasks=()):
    return {'company': company, 'project': None, 'period': period, 'technologies': [], 'role': role, 'role_details': None,
        'tasks': [{'value': text} for text in tasks], 'results': []}


def test_header_values_join_each_item_with_their_lines_before_completion():
    src = cv_source()
    offered = table(src)
    package = generic_package()
    block = next(value for value in package.definition.blocks if value.id == 'projects')
    job = LINES[3]
    head = {'employer': ('Example Labs', job), 'jobTitle': ('backend engineer', job), 'period': ('03.2020 – 11.2023', job)}
    entry = scoped(offered, [('Queue Platform', LINES[5:7], head), ('Ledger Service', LINES[7:9], head)])
    own = {ref: option for ref, option in offered.items() if digest(option.span) in {digest(span) for span in entry.spans}}
    reply = {'payload': [item(tasks=['Implemented queue processing']), item(role='lead', tasks=['Wrote the ledger import'])],
        'fields': [{'pointer': '/1/role', 'evidence': [line(offered, LINES[7])], 'item': {'kind': 'handle', 'ref': 'H1'},
            'fieldKey': None, 'effectiveCells': None}]}
    merged, extended = merge_header(reply, entry, own, block, package.definition, [src])
    first, second = merged['payload']
    assert (first['company'], first['role'], first['period']['start']['raw'], first['period']['end']['raw']) == (
        'Example Labs', 'backend engineer', '03.2020', '11.2023')
    # An item that states a role of its own keeps it, and its entry keeps its item.
    assert second['role'] == 'lead' and second['company'] == 'Example Labs'
    # The header line joins the table under a ref of its own, where it stands in the CV: before the entry's lines.
    header = next(ref for ref, option in extended.items() if option.span == offered[line(offered, job)].span)
    assert header not in own and list(extended) == [header, *own]
    entries = {value['pointer']: value for value in merged['fields']}
    assert entries['/0/company']['evidence'] == entries['/0/period']['evidence'] == entries['/0/role']['evidence'] == [header]
    assert entries['/1/role']['item'] == {'kind': 'handle', 'ref': 'H1'} and entries['/1/role']['evidence'] == [
        line(offered, LINES[7])]
    assert reply['payload'][0]['company'] is None


def test_items_that_do_not_match_the_parts_one_by_one_take_the_part_whose_lines_state_them():
    src = cv_source()
    offered = table(src)
    package = generic_package()
    block = next(value for value in package.definition.blocks if value.id == 'projects')
    first = {'employer': ('Example Labs', LINES[3])}
    second = {'employer': ('Second Works', LINES[9])}
    entry = scoped(offered, [('Queue Platform', LINES[5:7], first), ('Second Works', LINES[9:11], second)])
    reply = {'payload': [item(tasks=['Ran the nightly reports'])], 'fields': []}
    merged, _table = merge_header(reply, entry, dict(offered), block, package.definition, [src])
    assert merged['payload'][0]['company'] == 'Second Works'


def test_a_project_name_that_only_repeats_the_items_employer_is_dropped():
    # Live: the map titles an entry that names no project by its employer, the reply took that title as the project's
    # name, and the card read «Employer — Employer».
    src = cv_source()
    offered = table(src)
    package = generic_package()
    block = next(value for value in package.definition.blocks if value.id == 'projects')
    entry = scoped(offered, [('Second Works', LINES[9:11], {'employer': ('Second Works', LINES[9])})])
    cases = [({'name': ' second  works', 'description': None}, None, []),
        ({'name': 'Second Works', 'description': 'Nightly reports'}, {'name': None, 'description': 'Nightly reports'}, []),
        ({'name': 'Report Engine', 'description': None}, {'name': 'Report Engine', 'description': None}, ['/0/project/name'])]
    for project, shown, cited in cases:
        reply = {'payload': [{**item(tasks=['Ran the nightly reports']), 'project': project}],
            'fields': [{'pointer': '/0/project/name', 'evidence': [line(offered, LINES[9])], 'item': None, 'fieldKey': None,
                'effectiveCells': None}]}
        merged, _table = merge_header(reply, entry, dict(offered), block, package.definition, [src])
        assert merged['payload'][0]['project'] == shown and merged['payload'][0]['company'] == 'Second Works'
        assert [value['pointer'] for value in merged['fields'] if value['pointer'].startswith('/0/project')] == cited


def test_an_entry_of_the_map_reads_the_entry_rule_with_its_header_fields_and_others_keep_protocol_six():
    header = {'employer': ['company'], 'jobTitle': ['role'], 'period': ['period']}
    mapped = proposal_protocol(None, entry=True, header=header)
    assert mapped['version'] == MAPPED_PROPOSAL_VERSION and 'company and period' in mapped['rules'][-1]
    assert 'role only when' in mapped['rules'][-1] and 'entry.others' not in ' '.join(mapped['rules'])
    assert proposal_protocol(None, entry=True, header={})['rules'][-1].startswith('entry names the part')
    assert proposal_protocol(None, entry=True)['version'] == PROPOSAL_PROTOCOL['version']


def entry_requests(fixture):
    return [value for value in fixture.transport.calls if 'entry' in value and value.get('slot') == 'initial']


@pytest.mark.asyncio
@pytest.mark.parametrize('concurrency,groups', [(3, 2), (1, 1)])
async def test_a_block_of_entries_runs_the_maps_entries_in_groups_without_an_outline(tmp_path, concurrency, groups):
    fixture, result, workspace, _originals = await generic_import(tmp_path, 'F10', source_map=True, concurrency=concurrency)
    assert result.state == 'published'
    entries = [task for task in result.tasks if task.entry is not None]
    assert len(entries) == groups and {task.entry.origin for task in entries} == {'map'}
    assert not any(attempt.slot in {'outline', 'outline_review'} for attempt in result.attempts)
    assert not any(task.kind == 'outline_review' for task in result.tasks)
    for request in entry_requests(fixture):
        offered = {option['ref'] for option in request['evidence']}
        # Only its own lines, its parts with their header values, no list of other entries.
        assert set(request['entry']['lines']) == offered - {option['ref'] for option in request['evidence']
            if option['span']['start'] == 0 and '\n' in option['text'].strip()}
        assert 'others' not in request['entry'] and all('employer' in part for part in request['entry']['parts'])
        assert request['replyProtocol']['version'] == MAPPED_PROPOSAL_VERSION
    # The verbatim employer and role of an item are settled by the coordinator on their header lines.
    projects = [record.value for record in result.review_inputs if any(target.rule_id.startswith('projects')
        for target in record.value.targets)]
    for review in projects:
        settled = {value.target_id for value in review.settled}
        asked = {check for group in review.semantic_context['checks'] if group.get('pointer', '').endswith(('/company', '/role'))
            for check in group['checks']}
        assert settled and not asked


def template_dates(table):
    """The scripted table with each period date written as the templates ask (D135), MM.YYYY or YYYY, as the coordinator
    writes the dates it reads from a header period."""
    payload, cites = table['projects']
    for item in payload:
        for key in ('start', 'end'):
            value = (item.get('period') or {}).get(key)
            if value:
                value['raw'] = f"{value['month']:02d}.{value['year']}" if value['month'] else str(value['year'])
    return table


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.parametrize('name,concurrency,rewrite', [('F10', 3, True), ('F10', 1, True), ('F04', 3, False), ('F04', 3, True)])
async def test_a_scripted_import_of_entries_from_the_map_publishes_the_document_it_publishes_without_one(tmp_path, name,
                                                                                                      concurrency, rewrite):
    table_ = template_dates(TABLES[name](rewrite))
    _mapped, result, workspace, _originals = await generic_import(tmp_path / 'map', name, source_map=True,
        concurrency=concurrency, rewrite=rewrite, table=table_)
    _plain, baseline, before, _originals = await generic_import(tmp_path / 'base', name, concurrency=concurrency,
        rewrite=rewrite, table=table_)
    assert document(workspace) == document(before)
    assert [issue.code for issue in result.issues] == [issue.code for issue in baseline.issues]


@pytest.mark.asyncio
async def test_a_header_value_no_line_states_is_dropped_its_field_stays_empty_and_the_entry_names_it(tmp_path):
    def wrap(script):
        def answer(request, value):
            reply = deepcopy(script(request, value))
            if value.get('slot') == 'map':
                reply['entries'][0]['employer'] = {'value': 'Imagined Holdings', 'line': reply['entries'][0]['first']}
            elif 'entry' in value and value.get('slot') == 'initial':
                # As the entry rule asks: the reply leaves the employer to the coordinator.
                for index, part in enumerate(reply['payload']):
                    if part['company'] == 'Old Systems':
                        part['company'] = None
                        reply['fields'] = [field for field in reply['fields'] if field['pointer'] != '/' + str(index) + '/company']
            return reply
        return answer
    _fixture, result, workspace, _originals = await generic_import(tmp_path, 'F10', source_map=True, concurrency=3, wrap=wrap)
    assert result.state == 'published'
    mapped = next(value.value for value in result.task_results if any(task.id == value.task_id and task.kind == 'map'
        for task in result.tasks))
    assert mapped['entries'][0]['header']['employer'] is None and mapped['entries'][0]['dropped'] == ['Imagined Holdings']
    notices = [issue for issue in result.issues if issue.code == 'IMPORT_VALUE_UNBOUND']
    assert len(notices) == 1 and '«Imagined Holdings»' in notices[0].message
    assert 'Imagined Holdings' not in '\n'.join(document(workspace))


def names(result, block='projects'):
    tasks = {task.id: task for task in result.tasks}
    return [value.value for value in result.task_results if tasks[value.task_id].block_id == block
        and tasks[value.task_id].parent_task_id is None and isinstance(value.value, dict) and 'entries' in value.value]


@pytest.mark.asyncio
async def test_a_project_name_the_entrys_lines_do_not_state_word_for_word_is_one_finding_its_repair_fixes(tmp_path):
    def wrap(script):
        def answer(request, value):
            # The scripted replies share the table's items: change a copy.
            reply = deepcopy(script(request, value))
            if 'entry' in value and value.get('slot') == 'initial':
                for part in reply['payload']:
                    if (part.get('project') or {}).get('name') == 'Queue Platform':
                        # Re-punctuated: the lines write «Queue Platform».
                        part['project']['name'] = 'Queue-Platform'
            return reply
        return answer
    _fixture, result, workspace, _originals = await generic_import(tmp_path, 'F10', source_map=True, concurrency=3, wrap=wrap)
    assert result.state == 'published'
    found = [(record, value) for record in result.review_inputs for value in record.value.settled
        if value.disposition == 'violation' and value.reason.startswith('Название проекта')]
    assert len(found) == 1 and found[0][1].reason == 'Название проекта не стоит в строках записи слово в слово: «Queue-Platform».'
    review = found[0][0].value
    asked = {(target.rule_id, target.target_id) for target in review.targets} - {(value.rule_id, value.target_id)
        for value in review.settled}
    # The model is not asked about the name; its other checks keep their refs in target order.
    assert not any(target_id == found[0][1].target_id for _rule, target_id in asked)
    assert [group['checks'] for group in review.semantic_context['checks']] and len({check for group in
        review.semantic_context['checks'] for check in group['checks']}) == len(asked)
    slots = [attempt.slot for attempt in result.attempts]
    assert slots.count('primary_repair') == 1 and slots.count('replacement_review') == 1
    shown = '\n'.join(document(workspace))
    assert 'Queue Platform' in shown and 'Queue-Platform' not in shown
    # Only F10's own designed finding (a result claiming more than its line) stays a warning; the name's is fixed.
    assert [issue.code for issue in result.issues] == ['IMPORT_SOURCE_FALLBACK']
    assert 'Название проекта' not in result.issues[0].message


@pytest.mark.asyncio
async def test_an_entry_the_map_titled_by_its_employer_that_names_a_project_is_flagged_without_a_finding(tmp_path):
    _fixture, result, _workspace, _originals = await generic_import(tmp_path, 'F10', source_map=True, concurrency=3)
    # The scripted map titles each entry by its company; the second job names its project.
    [closed] = names(result)
    assert [(flag['title'], flag['name']) for flag in closed['titledByEmployer']] == [('Example Labs', 'Queue Platform')]
    assert not any(value.disposition == 'violation' and value.reason.startswith('Название проекта')
        for record in result.review_inputs for value in record.value.settled)
    assert [issue.code for issue in result.issues] == ['IMPORT_SOURCE_FALLBACK']
