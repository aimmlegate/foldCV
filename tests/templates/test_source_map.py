"""T4 of D158: one call maps the CV before its blocks; the coordinator checks the map and repairs it once when its
entries leave lines out, and a map that failed or stays doubted is not used: the import runs as before it."""

import json
from types import SimpleNamespace

import pytest

from packages.resume_core.models.contracts import Source
from packages.resume_core.hashing import sha256
from packages.resume_core.importing.template_identity import evidence_options, offered_evidence
from packages.resume_core.importing.template_import import (admit_operation, capture_task_input, reserve_attempt,
                                                            retain_operation, spent_calls)
from packages.resume_core.importing.template_map import (apply_repair, map_input, map_repair_input, parse_map,
                                                         uncovered, whole_source)
from packages.resume_core.import_failure import TemplateImportFailure
from packages.resume_core.models.template_import import MAP_BLOCK_ID, ImportOperation
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.replies import map_schema
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from packages.resume_core.templates.loading import load_definition
from resume_api.projects.import_progress import CALLED, activity, step_titles
from tests.templates.entry_fixtures import entries_package, entry_answer, lines_source, ref_of, satisfied
from tests.templates.pipeline_fixtures import NOW, model, owner, resume_command, setup_operation
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_template_retry import failure

# A synthetic CV: a job with its own duty above two projects, a second job, skills, a contact and a heading.
LINES = ['Alex Example', 'Backend engineer', 'Experience', 'Example Labs — backend engineer, 03.2020 – 11.2023',
    '- Kept the release train running', 'Project: Queue Platform', '- Implemented queue processing',
    'Project: Ledger Service', '- Wrote the ledger import', 'Second Works, engineer, 2016 – 2019', '- Ran the nightly reports',
    'Skills: Python, PostgreSQL', 'Phone: +1 555 010 0000']


def cv_source():
    raw = ('\n'.join(LINES) + '\n').encode()
    value = Source(id='source-cv', revision=1, originalName='cv.txt', mimeType='text/plain', byteSha256=sha256(raw),
        byteRef='sources/cv.txt', parser='text', parserVersion='1', units=[{'id': 'unit-cv', 'revision': 1, 'order': 0,
            'text': raw.decode(), 'location': {'kind': 'pasted', 'index': 0, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []}], overlays=[], warnings=[])
    return value


def table(src):
    return {option.ref: option for option in evidence_options(whole_source([src]), [src])}


def line(offered, text):
    return next(ref for ref, option in offered.items() if option.text.strip() == text)


REQUEST = {'blocks': [{'block': 'identity'}, {'block': 'projects'}, {'block': 'skills'}], 'entryBlocks': [{'block': 'projects'}]}


def header(offered, value, text):
    return {'value': value, 'line': line(offered, text)}


def entry(offered, title, first, last, employer=None, job=None, period=None):
    return {'block': 'projects', 'title': title, 'first': line(offered, first), 'last': line(offered, last),
        'employer': employer, 'jobTitle': job, 'period': period}


def full_map(offered, *, own_duty=True):
    """A map whose entries hold every projects line: the job's own duty is an entry of that job."""
    job, second = LINES[3], LINES[9]
    head = {'employer': header(offered, 'Example Labs', job), 'job': header(offered, 'backend engineer', job),
        'period': header(offered, '03.2020 – 11.2023', job)}
    entries = [entry(offered, 'Queue Platform', LINES[5], LINES[6], **head), entry(offered, 'Ledger Service', LINES[7], LINES[8], **head),
        entry(offered, 'Second Works', second, LINES[10], header(offered, 'Second Works', second), header(offered, 'engineer', second),
            header(offered, '2016 – 2019', second))]
    if own_duty:
        entries.insert(0, entry(offered, 'Example Labs', LINES[4], LINES[4], **head))
    return {'blocks': [{'block': 'identity', 'ranges': [{'first': line(offered, LINES[0]), 'last': line(offered, LINES[1])}]},
        {'block': 'projects', 'ranges': [{'first': line(offered, job), 'last': line(offered, LINES[10])}]},
        {'block': 'skills', 'ranges': [{'first': line(offered, LINES[11]), 'last': line(offered, LINES[11])}]}],
        'entries': entries, 'hidden': [{'first': line(offered, LINES[2]), 'last': line(offered, LINES[2])}]}


def test_a_map_names_each_blocks_lines_and_the_entries_of_a_block_of_entries():
    src = cv_source()
    offered = table(src)
    value = parse_map(full_map(offered), offered, [src], REQUEST)
    texts = lambda refs: [offered[ref].text.strip() for ref in refs]
    assert texts(value['blocks']['identity']) == LINES[:2] and texts(value['blocks']['skills']) == [LINES[11]]
    assert texts(value['blocks']['projects']) == LINES[3:11]
    assert [(item['title'], texts(item['lines'])) for item in value['entries']] == [('Example Labs', [LINES[4]]),
        ('Queue Platform', LINES[5:7]), ('Ledger Service', LINES[7:9]), ('Second Works', LINES[9:11])]
    assert value['uncovered'] == {} and value['repaired'] is False
    # The heading holds no content and the phone line only contacts: no line is left unused.
    assert texts(value['hidden']) == [LINES[2]] and value['unused'] == []
    # The whole unit's ref stands for its lines.
    whole = next(ref for ref, option in offered.items() if '\n' in option.text.strip())
    widest = parse_map({'blocks': [{'block': 'skills', 'ranges': [{'first': whole, 'last': whole}]}], 'entries': [], 'hidden': []},
        offered, [src], REQUEST)
    assert texts(widest['blocks']['skills']) == LINES


@pytest.mark.parametrize('broken', ['unoffered', 'backwards', 'shared', 'block', 'entry_block', 'header_line'])
def test_a_map_with_a_ref_that_is_no_offered_line_a_backwards_range_or_entries_sharing_a_line_is_refused(broken):
    src = cv_source()
    offered = table(src)
    reply = full_map(offered)
    if broken == 'unoffered':
        reply['blocks'][0]['ranges'][0]['last'] = 'S99'
    elif broken == 'backwards':
        reply['blocks'][0]['ranges'][0] = {'first': line(offered, LINES[1]), 'last': line(offered, LINES[0])}
    elif broken == 'shared':
        reply['entries'][1]['last'] = reply['entries'][2]['first']
    elif broken == 'block':
        reply['blocks'][0]['block'] = 'summary'
    elif broken == 'entry_block':
        reply['entries'][0]['block'] = 'skills'
    else:
        reply['entries'][0]['employer']['line'] = 'S99'
    with pytest.raises(ValueError):
        parse_map(reply, offered, [src], REQUEST)


def units_source(texts):
    """A source read one unit per line, as a PDF is."""
    raw = ('\n'.join(texts) + '\n').encode()
    return Source(id='source-pdf', revision=1, originalName='cv.pdf', mimeType='application/pdf', byteSha256=sha256(raw),
        byteRef='sources/cv.pdf', parser='text', parserVersion='1', units=[{'id': 'unit-' + str(index), 'revision': 1,
            'order': index, 'text': text, 'location': {'kind': 'pasted', 'index': index, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []} for index, text in enumerate(texts)], overlays=[], warnings=[])


def test_the_map_request_offers_no_blank_unit_so_its_map_is_not_refused_for_naming_one():
    # Live: a PDF's first unit was blank; the map named its ref, which is no line, and the whole map was refused.
    src = units_source(['', *LINES])
    whole = table(src)
    blank = next(ref for ref, option in whole.items() if not option.text.strip())
    reply = full_map(whole)
    reply['hidden'].append({'first': blank, 'last': blank})
    with pytest.raises(ValueError, match='no offered line'):
        parse_map(reply, whole, [src], REQUEST)
    _command, package, _src = mapped_operation()
    request = map_input(SimpleNamespace(capture=SimpleNamespace(allow_text_rewrite=True)),
        SimpleNamespace(template_package=package, sources=[src]))
    offered = offered_evidence(request)
    assert blank not in offered and all(option.text.strip() for option in offered.values())
    assert sorted(option.text.strip() for option in offered.values()) == sorted(LINES)
    value = parse_map(full_map(offered), offered, [src], REQUEST)
    assert [offered[ref].text.strip() for ref in value['blocks']['identity']] == LINES[:2]


def test_a_header_value_stays_on_its_line_moves_to_the_line_that_states_it_or_is_dropped():
    src = cv_source()
    offered = table(src)
    reply = full_map(offered)
    first = reply['entries'][1]
    # Another dash and case: the line's own wording is kept.
    first['period'] = header(offered, '03.2020 - 11.2023', LINES[3])
    first['employer'] = header(offered, 'example labs', LINES[3])
    # Named on the project's line, stated on the job's line: it takes that line.
    first['jobTitle'] = header(offered, 'backend engineer', LINES[5])
    # Stated nowhere: dropped and named.
    reply['entries'][3]['jobTitle'] = header(offered, 'principal engineer', LINES[9])
    value = parse_map(reply, offered, [src], REQUEST)
    queue, second = value['entries'][1], value['entries'][3]
    assert queue['header'] == {'employer': {'value': 'Example Labs', 'line': line(offered, LINES[3])},
        'jobTitle': {'value': 'backend engineer', 'line': line(offered, LINES[3])},
        'period': {'value': '03.2020 – 11.2023', 'line': line(offered, LINES[3])}}
    assert second['header']['jobTitle'] is None and second['dropped'] == ['principal engineer']
    assert 'dropped' not in queue


def test_the_lines_of_a_block_of_entries_no_entry_holds_are_uncovered_but_header_and_hidden_lines_are_not():
    src = cv_source()
    offered = table(src)
    value = parse_map(full_map(offered, own_duty=False), offered, [src], REQUEST)
    # The job's own duty above its projects is in no entry (probe B lost such lines on a long CV).
    assert {block: [offered[ref].text.strip() for ref in refs] for block, refs in value['uncovered'].items()} == {
        'projects': [LINES[4]]}
    assert uncovered({**value, 'hidden': [*value['hidden'], line(offered, LINES[4])]}) == {}


def repaired(offered, src, value, lines, entries=()):
    return apply_repair(value, {'lines': lines, 'entries': list(entries)}, offered, src)


def test_the_repair_places_each_uncovered_line_adds_an_entry_the_map_missed_or_names_a_line_of_no_entry():
    src = cv_source()
    offered = table(src)
    value = parse_map(full_map(offered, own_duty=False), offered, [src], REQUEST)
    duty = line(offered, LINES[4])
    request = map_repair_input({'protocol': 'template_import_v1', 'blocks': REQUEST['blocks'],
        'entryBlocks': REQUEST['entryBlocks'], 'evidence': [option.model_dump(mode='json', by_alias=True)
            for option in offered.values()]}, value, offered, [src])
    # The repair offers the block's lines and names the map's entries by number; the block list goes.
    assert 'blocks' not in request and request['uncovered'] == [duty] and request['slot'] == 'map_repair'
    assert [entry['index'] for entry in request['map']['entries']] == [1, 2, 3]
    assert {option['text'].strip() for option in request['evidence']} == set(LINES[3:11])
    joined = repaired(offered, [src], value, [{'line': duty, 'entry': 1}])
    assert joined['entries'][0]['lines'] == [duty, *value['entries'][0]['lines']] and joined['repaired'] is True
    head = {'employer': header(offered, 'Example Labs', LINES[3]), 'jobTitle': header(offered, 'backend engineer', LINES[3]),
        'period': header(offered, '03.2020 – 11.2023', LINES[3])}
    added = repaired(offered, [src], value, [{'line': duty, 'entry': 4}], [{'title': 'Example Labs', **head}])
    # The added entry goes first: the map's entries follow the CV's order.
    assert [item['title'] for item in added['entries']] == ['Example Labs', 'Queue Platform', 'Ledger Service', 'Second Works']
    assert added['entries'][0]['lines'] == [duty] and added['entries'][0]['header']['employer']['value'] == 'Example Labs'
    none = repaired(offered, [src], value, [{'line': duty, 'entry': None}])
    assert duty in none['hidden'] and none['uncovered'] == {}
    for answer in ([], [{'line': duty, 'entry': 7}], [{'line': 'S99', 'entry': 1}]):
        with pytest.raises(ValueError):
            repaired(offered, [src], value, answer)


def test_lines_no_block_reads_are_unused_unless_the_map_names_them_as_no_content_or_they_hold_only_contacts():
    src = cv_source()
    offered = table(src)
    reply = full_map(offered)
    reply['hidden'] = []
    reply['blocks'] = [block for block in reply['blocks'] if block['block'] != 'skills']
    value = parse_map(reply, offered, [src], REQUEST)
    assert [offered[ref].text.strip() for ref in value['unused']] == [LINES[2], LINES[11]]


def test_the_map_schema_names_lines_by_plain_refs_and_blocks_by_their_ids():
    schema = map_schema(['identity', 'projects'], ['projects'])
    text = json.dumps(schema)
    assert schema['$defs']['MapBlockRef'] == {'type': 'string', 'enum': ['identity', 'projects']}
    assert schema['$defs']['LineRange']['properties']['first'] == {'pattern': '^S[1-9][0-9]*$', 'title': 'First',
        'type': 'string'} and len(text) < 2500


def test_no_template_may_declare_the_map_tasks_id():
    config = load_definition(BUNDLED_TEMPLATE.read_bytes())
    location = next(block for block in config['blocks'] if block['id'] == 'location')
    config['blocks'].append({**location, 'id': MAP_BLOCK_ID, 'placement': {**location['placement'], 'order': 99}})
    with pytest.raises(SchemaFailure, match='reserved'):
        compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def mapped_operation(*, concurrency=1):
    src, _raw = lines_source(2)
    operation, command, package, _src, _facts = setup_operation(captured=entries_package(), src=src, cap=20, concurrency=concurrency)
    command.capture.policy.source_map = True
    return command, package, src


def test_a_new_import_starts_with_its_map_task_and_its_model_blocks_wait_for_it():
    from packages.resume_core.importing.template_import import start_operation
    from packages.resume_core.models.template_facts import WorkingFactsV2
    command, package, src = mapped_operation()
    facts = WorkingFactsV2(schemaVersion=2, revision=1, records=[], tombstones=[], extensions=[], observations=[], relations=[],
        manualScopes=[])
    serial = iter(range(100))
    operation, _created = start_operation('pipeline-project', command, package, [src], facts, [], NOW,
        id_factory=lambda prefix: prefix + '-' + str(next(serial)))
    mapper, block = operation.tasks
    assert (mapper.kind, mapper.block_id, mapper.dependencies) == ('map', MAP_BLOCK_ID, [])
    assert block.kind == 'extract' and block.dependencies == [mapper.id]
    # Only the map task holds the map's slots; a repair needs a map that answered.
    operation = admit_operation(operation, NOW)
    operation = capture_task_input(operation, mapper.id, {'protocol': 'template_import_v1', 'map': True}, [], NOW)
    with pytest.raises(TemplateImportFailure, match='IMPORT_REPAIR_WITHOUT_INITIAL'):
        reserve_attempt(operation, mapper.id, 'map_repair', sha256(b'r'), model(), owner(1), NOW)
    with pytest.raises(TemplateImportFailure, match='IMPORT_MODEL_NOT_CAPTURED'):
        reserve_attempt(operation, mapper.id, 'map', sha256(b'm'), model('other'), owner(2), NOW)
    reserved, _attempt = reserve_attempt(operation, mapper.id, 'map', sha256(b'm'), model(), owner(3), NOW)
    retain_operation(operation, reserved)
    # A captured map task shape is checked: it has the reserved id and no parent.
    shaped = operation.model_dump(mode='json', by_alias=True)
    shaped['tasks'][0]['blockId'] = 'arbitrary-paper-view'
    with pytest.raises(ValueError, match='map task shape'):
        ImportOperation.model_validate(shaped)


def map_answer(value, keys=(0, 1)):
    papers = [option['ref'] for option in value['evidence'] if 'Reliable Queues' in option['text'] and '\n' not in option['text'].strip()]
    return {'blocks': [{'block': 'arbitrary-paper-view', 'ranges': [{'first': papers[0], 'last': papers[-1]}]}],
        'entries': [{'block': 'arbitrary-paper-view', 'title': 'Paper ' + str(key + 1), 'first': papers[key], 'last': papers[key],
            'employer': None, 'jobTitle': None, 'period': None} for key in keys],
        'hidden': [{'first': ref_of(value, 'Alex Example'), 'last': ref_of(value, 'Publications')}]}


def papers_fixture(tmp_path, script, *, concurrency=1, mapped=True, cap=20):
    src, raw = lines_source(2)
    fixture = RuntimeFixture(tmp_path, scripted=script, captured=entries_package(), src=src, original_bytes=raw, cap=cap,
        concurrency=concurrency, fallback=False)
    fixture.command.capture.policy.source_map = mapped
    return fixture


def answering(map_reply=None, repair=None):
    """Scripted replies: the map (or the given override), a repair, and entries and reviews as D117's tests answer them."""
    def script(_request, value):
        slot = value.get('slot')
        if slot == 'map':
            return map_reply(value) if map_reply else map_answer(value)
        if slot == 'map_repair':
            return repair(value) if repair else {'lines': [], 'entries': []}
        if slot == 'outline':
            return {'entries': [{'title': 'Paper ' + str(key), 'first': ref, 'last': ref} for key, ref in enumerate(
                [option['ref'] for option in value['evidence'] if 'Reliable Queues' in option['text']
                    and '\n' not in option['text'].strip()], 1)]}
        if slot == 'outline_review':
            return {'missing': [], 'remarks': []}
        if 'targets' in value:
            return satisfied(value)
        if 'entry' not in value:
            # The whole block (one call at a time): every paper line is its entry.
            value = {**value, 'entry': {'lines': [option['ref'] for option in value['evidence']
                if 'Reliable Queues' in option['text'] and '\n' not in option['text'].strip()]}}
        return entry_answer(value)
    return script


async def run(fixture):
    return await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)


def calls(operation):
    """The import's calls by block, task kind and slot, without the map task's; in call order at one call at a time,
    sorted when calls ran side by side (their order follows the timing)."""
    tasks = {task.id: task for task in operation.tasks}
    made = [(tasks[attempt.task_id].block_id, tasks[attempt.task_id].kind, attempt.slot) for attempt in operation.attempts
        if tasks[attempt.task_id].kind != 'map']
    return made if operation.capture.policy.concurrency == 1 else sorted(made)


def prompts(fixture):
    """The text of every extraction call; sorted when calls ran side by side. A review lists its checks in the order of
    their cells' ids, which differ from run to run, so reviews are compared by their calls only."""
    sent = [prompt for prompt, value in zip(fixture.transport.prompts, fixture.transport.calls, strict=True)
        if value.get('slot') not in {'map', 'map_repair'} and 'targets' not in value]
    return sent if fixture.command.capture.policy.concurrency == 1 else sorted(sent)


def map_result(operation):
    task = next(task for task in operation.tasks if task.kind == 'map')
    return task, next(value for value in operation.task_results if value.task_id == task.id)


@pytest.mark.asyncio
@pytest.mark.parametrize('concurrency', [1, 3])
async def test_the_map_runs_first_at_any_width_and_its_checked_result_is_stored(tmp_path, concurrency):
    fixture = papers_fixture(tmp_path, answering(), concurrency=concurrency)
    result = await run(fixture)
    assert result.state == 'published' and result.attempts[0].slot == 'map'
    task, value = map_result(result)
    assert task.state == 'accepted' and value.disposition == 'derived' and len(value.value['entries']) == 2
    assert value.value['unused'] == [] and value.value['uncovered'] == {}
    # The map call ran with the import model and effort.
    assert result.attempts[0].model == result.capture.primary


FAILURES = {
    'failed': lambda _value: failure('PROVIDER_ERROR'),
    'refused': lambda _value: failure('REFUSED'),
    'unparsable': lambda _value: 'not a reply',
    'backwards': lambda value: {**map_answer(value), 'blocks': [{'block': 'arbitrary-paper-view', 'ranges': [
        {'first': ref_of(value, 'paper-b'), 'last': ref_of(value, 'paper-a')}]}]},
    'unoffered': lambda value: {**map_answer(value), 'entries': [{**map_answer(value)['entries'][0], 'last': 'S99'}]},
    'shared': lambda value: {**map_answer(value), 'entries': [{**entry, 'first': ref_of(value, 'paper-a'),
        'last': ref_of(value, 'paper-b')} for entry in map_answer(value)['entries']]},
}


@pytest.mark.asyncio
@pytest.mark.parametrize('case', sorted(FAILURES))
@pytest.mark.parametrize('concurrency', [1, 3])
async def test_a_map_that_failed_or_cannot_be_used_ends_empty_and_the_import_runs_as_before(tmp_path, case, concurrency):
    base = papers_fixture(tmp_path / 'base', answering(), concurrency=concurrency, mapped=False)
    baseline = await run(base)
    fixture = papers_fixture(tmp_path / 'case', answering(FAILURES[case]), concurrency=concurrency)
    result = await run(fixture)
    task, value = map_result(result)
    assert result.state == 'published' and task.state == 'empty' and value.disposition == 'empty'
    assert value.value['map'] == 'unused' and value.value['reason']
    # Every other call is the import's without a map, sent with the same text, and its document is the same.
    assert calls(result) == calls(baseline)
    assert prompts(fixture) == prompts(base)
    assert [attempt.slot for attempt in result.attempts if attempt.slot in {'map', 'map_repair'}] == ['map']
    assert fixture.text() == base.text() != '' and result.issues == baseline.issues == []


@pytest.mark.asyncio
@pytest.mark.parametrize('repair', ['leaves', 'fails', 'unknown_entry'])
async def test_a_map_that_stays_doubted_after_its_repair_ends_empty_and_the_import_runs_as_before(tmp_path, repair):
    base = papers_fixture(tmp_path / 'base', answering(), concurrency=3, mapped=False)
    baseline = await run(base)
    answers = {'leaves': lambda _value: {'lines': [], 'entries': []}, 'fails': lambda _value: failure('PROVIDER_ERROR'),
        'unknown_entry': lambda value: {'lines': [{'line': value['uncovered'][0], 'entry': 9}], 'entries': []}}
    # The map leaves the second paper out of every entry.
    fixture = papers_fixture(tmp_path / 'case', answering(lambda value: map_answer(value, keys=(0,)), answers[repair]),
        concurrency=3)
    result = await run(fixture)
    task, value = map_result(result)
    assert result.state == 'published' and task.state == 'empty' and value.value['map'] == 'unused'
    assert [attempt.slot for attempt in result.attempts if attempt.slot.startswith('map')] == ['map', 'map_repair']
    assert calls(result) == calls(baseline) and prompts(fixture) == prompts(base)


@pytest.mark.asyncio
async def test_a_repair_that_places_every_uncovered_line_makes_the_map_usable(tmp_path):
    def repair(value):
        assert [entry['index'] for entry in value['map']['entries']] == [1] and len(value['uncovered']) == 1
        return {'lines': [{'line': value['uncovered'][0], 'entry': 2}], 'entries': [{'title': 'Paper 2', 'employer': None,
            'jobTitle': None, 'period': None}]}
    fixture = papers_fixture(tmp_path, answering(lambda value: map_answer(value, keys=(0,)), repair), concurrency=3)
    result = await run(fixture)
    task, value = map_result(result)
    assert task.state == 'accepted' and value.value['repaired'] is True
    assert [entry['title'] for entry in value.value['entries']] == ['Paper 1', 'Paper 2']


@pytest.mark.asyncio
async def test_a_map_call_that_never_answered_is_made_once_more(tmp_path):
    seen = []

    def stalled(value):
        seen.append(value)
        if len(seen) == 1:
            failure('STALLED')
        return map_answer(value)
    fixture = papers_fixture(tmp_path, answering(stalled), concurrency=3)
    result = await run(fixture)
    task, value = map_result(result)
    assert [attempt.slot for attempt in result.attempts[:2]] == ['map', 'map'] and task.state == 'accepted'
    assert result.attempts[0].error_code == 'STALLED' and value.disposition == 'derived'


@pytest.mark.asyncio
async def test_without_room_for_the_map_and_the_blocks_the_import_runs_as_before(tmp_path):
    base = papers_fixture(tmp_path / 'base', answering(), mapped=False, cap=3)
    baseline = await run(base)
    fixture = papers_fixture(tmp_path / 'case', answering(), cap=3)
    result = await run(fixture)
    task, value = map_result(result)
    assert value.value == {'map': 'unused', 'reason': 'IMPORT_CALL_CAP'} and not task.attempt_ids
    assert calls(result) == calls(baseline) and spent_calls(result) == spent_calls(baseline)
    assert prompts(fixture) == prompts(base)


@pytest.mark.asyncio
async def test_an_import_started_without_a_map_resumes_and_publishes_without_one(tmp_path):
    # A capture made before T4 has no sourceMap and its import no map task; nothing of this slice is in its record.
    stopped = []

    def script(_request, value):
        if 'targets' in value and not stopped:
            stopped.append(value)
            failure('QUOTA_EXHAUSTED')
        return answering()(_request, value)
    fixture = papers_fixture(tmp_path, script, mapped=False)
    from resume_api.importer.template_pipeline import AccountStop
    with pytest.raises(AccountStop):
        await run(fixture)
    stored = fixture.current().pre_draft.template_operations[0]
    text = stored.model_dump_json(by_alias=True)
    assert 'sourceMap' not in text and '"map"' not in text and all(task.kind != 'map' for task in stored.tasks)
    fixture.restart()
    result = await fixture.pipeline.run(fixture.project, resume_command(stored), admitted=fixture.admitted)
    assert result.state == 'published' and all(task.kind != 'map' for task in result.tasks)
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'review', 'review']


@pytest.mark.asyncio
async def test_the_progress_titles_the_map_task_and_names_its_calls(tmp_path):
    def repair(value):
        return {'lines': [{'line': value['uncovered'][0], 'entry': None}], 'entries': []}
    fixture = papers_fixture(tmp_path, answering(lambda value: map_answer(value, keys=(0,)), repair), concurrency=3)
    result = await run(fixture)
    assert step_titles(fixture.package)[MAP_BLOCK_ID] == 'Разметка резюме'
    events, _at = activity(result, step_titles(fixture.package))
    texts = [text for _when, text in events]
    assert 'Размечаем резюме: «Разметка резюме»' in texts and 'Уточняем разметку: «Разметка резюме»' in texts
    assert CALLED['names'] == 'Собираем навыки'


@pytest.mark.asyncio
async def test_an_import_that_stopped_before_its_map_ended_finishes_with_the_map_unused_and_the_whole_cv(tmp_path):
    fixture = papers_fixture(tmp_path, answering())
    operation = await fixture.pipeline.start(fixture.project, fixture.command)
    fixture.pipeline.update_operation(fixture.project, operation.id,
        lambda value, _data, _workspace: admit_operation(value, NOW))
    operation = await fixture.pipeline.finish_fallbacks(fixture.project, operation.id)
    task, value = map_result(operation)
    assert task.state == 'empty' and value.value == {'map': 'unused', 'reason': 'IMPORT_PROCESSING_STOPPED'}
    block = next(task for task in operation.tasks if task.kind != 'map')
    stored = next(record.value for record in operation.task_inputs if record.task_id == block.id)
    assert block.state == 'source_fallback' and 'mapped' not in stored
    assert len(stored['evidence']) == len(table(fixture.source))
