"""A block declared per_entry (D117): one outline call names its entries by their lines, each entry runs as its own
task with its own review and holds the items its lines state, the outline review may add an entry, and the block
closes when they all ended with its records in the outline's order."""

import asyncio
import threading
import time

import pytest

from types import SimpleNamespace

from packages.resume_core.models.contracts import Source
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.template_entries import line_options, ordered_entries, outline_scopes, reorder_records, splits_entries
from packages.resume_core.template_identity import capture_span, evidence_options, line_spans
from packages.resume_core.template_import import (TemplateImportFailure, add_entry_tasks, add_outline_review, admit_operation,
    capture_task_input, children_of, digest, entries_of, reserve_attempt, retain_operation, spent_calls)
from packages.resume_core.templates.compiler import sha256
from packages.resume_core.templates.replies import proposal_protocol
from resume_api.importer.template_pipeline import Spawned
from tests.templates.entry_fixtures import TITLES, entries_package, entries_script, lines_source, outline_answer, ref_of
from tests.templates.pipeline_fixtures import NOW, model, owner, setup_operation
from tests.templates.template_runtime_fixtures import RuntimeFixture


def offered(src):
    spans = [capture_span(src, src.units[0]), *line_spans(src, src.units[0])]
    return {option.ref: option for option in evidence_options(spans, [src])}


class Entry:
    def __init__(self, title, first, last):
        self.title, self.first, self.last = title, first, last


def test_only_a_model_list_block_declared_per_entry_splits():
    package = entries_package()
    block = package.definition.blocks[0]
    assert splits_entries(block) and not splits_entries(block.model_copy(update={'per_entry': False}))
    assert not splits_entries(block.model_copy(update={'content_schema': {'type': 'object', 'properties': {}}}))


def test_an_outline_names_entries_by_their_first_and_last_offered_line():
    src, _raw = lines_source(3)
    table = offered(src)
    lines = line_options(table, [src])
    assert [option.text.strip() for option in lines] == src.units[0].text.strip().split('\n')
    # A reversed pair is the same entry; a whole-unit ref stands for every line of the unit; a title is trimmed.
    scopes = outline_scopes([Entry('  Systems   Notes  ', 'S4', 'S3'), Entry('', 'S5', 'S5')], table, [src])
    assert [(title, [option.ref for option in lines if option.span in spans]) for title, spans in scopes] == [
        ('Systems Notes', ['S3', 'S4']), ('Запись 2', ['S5'])]
    assert len(outline_scopes([Entry('all', 'S1', 'S1')], table, [src])[0][1]) == 5
    with pytest.raises(ValueError, match='share a line'):
        outline_scopes([Entry('a', 'S3', 'S4'), Entry('b', 'S4', 'S5')], table, [src])
    with pytest.raises(ValueError, match='unoffered'):
        outline_scopes([Entry('a', 'S3', 'S9')], table, [src])
    # The outline review names only lines no running entry holds.
    taken = [lines[1].span]
    assert [title for title, _spans in outline_scopes([Entry('a', 'S3', 'S3'), Entry('b', 'S4', 'S4')], table, [src], taken=taken)] == ['b']


def test_blank_and_whole_unit_options_are_no_lines_and_lines_keep_the_document_order():
    raw = 'Alex\n'
    src = Source(id='source-mixed', revision=1, originalName='mixed.txt', mimeType='text/plain', byteSha256=sha256(raw.encode()),
        byteRef='sources/mixed.txt', parser='text', parserVersion='1', units=[{'id': 'unit-' + str(index), 'revision': 1,
            'order': index, 'text': text, 'location': {'kind': 'paragraph', 'index': index, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []} for index, text in enumerate(['Alex', '   ', 'A\nB'])],
        overlays=[], warnings=[])
    spans = [span for unit in src.units for span in [capture_span(src, unit), *line_spans(src, unit)]]
    table = {option.ref: option for option in evidence_options(list(reversed(spans)), [src])}
    assert [option.text for option in line_options(table, [src])] == ['Alex', 'A\n', 'B']


def test_the_entry_rule_joins_the_proposal_protocol_of_entry_requests_only():
    rules = proposal_protocol(None, entry=True)['rules']
    assert rules[-1].startswith('entry names the part of the source') and 'usually one' in rules[-1]
    assert proposal_protocol(None) is proposal_protocol(None) and rules[:-1] == proposal_protocol(None)['rules']


def entries_operation(count=2):
    src, _raw = lines_source(count)
    operation, _command, package, _source, facts = setup_operation(captured=entries_package(), src=src, cap=20)
    operation = admit_operation(operation, NOW)
    task = operation.tasks[0]
    operation = capture_task_input(operation, task.id, {'protocol': 'template_import_v1', 'evidence': [
        option.model_dump(mode='json', by_alias=True) for option in offered(src).values()], 'effectiveCells': [], 'tools': []}, [], NOW)
    return operation, src, package, facts


def test_entry_tasks_join_the_block_task_in_order_and_only_a_block_task_adds_them():
    operation, src, _package, _facts = entries_operation(3)
    parent = operation.tasks[0]
    scopes = outline_scopes([Entry('a', 'S3', 'S3'), Entry('b', 'S4', 'S4')], offered(src), [src])
    operation = add_outline_review(operation, parent.id)
    operation = add_entry_tasks(operation, parent.id, [[scope] for scope in scopes], 'outline')
    review, first, second = children_of(operation, parent.id)
    assert review.kind == 'outline_review' and review.entry is None and review.parent_task_id == parent.id
    assert [task.entry.index for task in (first, second)] == [1, 2] and first.entry.title == 'a'
    assert (first.kind, first.block_id, first.dependencies) == (parent.kind, parent.block_id, parent.dependencies)
    later = add_entry_tasks(operation, parent.id, [outline_scopes([Entry('c', 'S5', 'S5')], offered(src), [src])], 'review')
    assert [task.entry.index for task in entries_of(later, parent.id)] == [1, 2, 3] and entries_of(later, parent.id)[-1].entry.origin == 'review'
    with pytest.raises(TemplateImportFailure, match='IMPORT_TASK_NOT_READY'):
        add_entry_tasks(operation, first.id, [scopes], 'outline')
    with pytest.raises(TemplateImportFailure, match='IMPORT_TASK_NOT_READY'):
        add_outline_review(operation, parent.id)
    # Saves keep the captured tasks and accept only children added after them.
    retain_operation(operation, later)
    with pytest.raises(ProjectStoreFailure):
        retain_operation(later, operation)
    changed = later.model_copy(deep=True)
    changed.tasks[-1].entry = changed.tasks[-1].entry.model_copy(update={'title': 'other'})
    with pytest.raises(ProjectStoreFailure):
        retain_operation(later, changed)
    stranger = later.model_copy(deep=True)
    stranger.tasks.append(parent.model_copy(update={'id': 'task-stranger', 'parent_task_id': None}))
    with pytest.raises(ProjectStoreFailure):
        retain_operation(later, stranger)
    # Only a running import adds tasks: once it is finalizing, an added entry is refused.
    with pytest.raises(ProjectStoreFailure):
        retain_operation(operation.model_copy(update={'state': 'finalizing'}), later.model_copy(update={'state': 'finalizing'}))


def test_the_outline_and_its_review_have_their_own_slots():
    operation, src, _package, _facts = entries_operation()
    parent = operation.tasks[0]
    scopes = outline_scopes([Entry('a', 'S3', 'S3'), Entry('b', 'S4', 'S4')], offered(src), [src])
    operation = add_outline_review(operation, parent.id)
    operation = add_entry_tasks(operation, parent.id, [[scope] for scope in scopes], 'outline')
    review, first, _second = children_of(operation, parent.id)
    for child in (review, first):
        operation = capture_task_input(operation, child.id, {'protocol': 'template_import_v1', 'child': child.id}, [], NOW)
    with pytest.raises(TemplateImportFailure, match='IMPORT_MODEL_NOT_CAPTURED'):
        reserve_attempt(operation, parent.id, 'outline', digest('o'), model('other'), owner(1), NOW)
    with pytest.raises(TemplateImportFailure, match='IMPORT_ATTEMPT_SLOT'):
        reserve_attempt(operation, first.id, 'outline', digest('o'), operation.capture.primary, owner(1), NOW)
    with pytest.raises(TemplateImportFailure, match='IMPORT_ATTEMPT_SLOT'):
        reserve_attempt(operation, first.id, 'outline_review', digest('o'), operation.capture.primary, owner(1), NOW)
    outlined, attempt = reserve_attempt(operation, parent.id, 'outline', digest('o'), operation.capture.primary, owner(1), NOW)
    assert outlined.tasks[0].state == 'running'
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_UNKNOWN'):
        reserve_attempt(outlined, parent.id, 'outline', digest('p'), operation.capture.primary, owner(2), NOW)
    outlined.attempts[0].state, outlined.attempts[0].cleanup.state = 'reconciled', 'verified'
    outlined.attempts[0].cleanup.evidence_hash, outlined.attempts[0].cleanup.witness = digest('x'), 'w'
    with pytest.raises(TemplateImportFailure, match='IMPORT_SLOT_SPENT'):
        reserve_attempt(outlined, parent.id, 'outline', digest('p'), operation.capture.primary, owner(2), NOW)
    # The block may still run whole after its outline; an outline after that is spent.
    whole, _initial = reserve_attempt(outlined, parent.id, 'initial', digest('i'), operation.capture.primary, owner(2), NOW)
    whole.attempts[1].state, whole.attempts[1].cleanup = 'reconciled', outlined.attempts[0].cleanup
    with pytest.raises(TemplateImportFailure, match='IMPORT_SLOT_SPENT'):
        reserve_attempt(whole, parent.id, 'outline', digest('o'), operation.capture.primary, owner(3), NOW)
    reviewed, _checked = reserve_attempt(outlined, review.id, 'outline_review', digest('r'), operation.capture.primary, owner(2), NOW)
    with pytest.raises(TemplateImportFailure, match='IMPORT_MODEL_NOT_CAPTURED'):
        reserve_attempt(outlined, review.id, 'outline_review', digest('r'), operation.capture.fallback, owner(2), NOW)
    assert reviewed.attempts[-1].slot == 'outline_review'


def test_records_are_shown_in_the_entries_order_and_an_added_entry_goes_by_its_source_position():
    operation, src, _package, facts = entries_operation(3)
    parent = operation.tasks[0]
    table = offered(src)
    operation = add_entry_tasks(operation, parent.id, [[scope] for scope in outline_scopes([Entry('c', 'S5', 'S5'),
        Entry('a', 'S3', 'S3')], table, [src])], 'outline')
    operation = add_entry_tasks(operation, parent.id, [outline_scopes([Entry('b', 'S4', 'S4')], table, [src])], 'review')
    # The outline runs against the source order (newest first); the review's entry goes between its neighbours.
    assert [task.entry.title for task in ordered_entries(operation, parent.id, [src])] == ['c', 'b', 'a']
    forward = add_entry_tasks(entries_operation(3)[0], parent.id, [[scope] for scope in outline_scopes([Entry('a', 'S3', 'S3'),
        Entry('c', 'S5', 'S5')], table, [src])], 'outline')
    forward = add_entry_tasks(forward, parent.id, [outline_scopes([Entry('b', 'S4', 'S4')], table, [src])], 'review')
    assert [task.entry.title for task in ordered_entries(forward, parent.id, [src])] == ['a', 'b', 'c']
    from tests.templates.storage_fixtures import papers
    stored = papers()
    first, second = [record.id for record in stored.extensions]
    reordered = reorder_records(stored.model_copy(deep=True), [second, first])
    assert [record.id for record in reordered.extensions] == [second, first]
    assert reorder_records(stored.model_copy(deep=True), [first]).extensions == stored.extensions


def entries_fixture(tmp_path, *, count=2, concurrency=2, cap=30, **options):
    src, raw = lines_source(count)
    return RuntimeFixture(tmp_path, captured=entries_package(), src=src, original_bytes=raw, concurrency=concurrency, cap=cap, **options)


async def run_import(fixture):
    return await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)


@pytest.mark.asyncio
async def test_a_per_entry_block_outlines_extracts_each_entry_in_parallel_and_closes_in_the_outline_order(tmp_path):
    fixture = entries_fixture(tmp_path)
    lock, state = threading.Lock(), {'now': 0, 'peak': 0}
    def script(request, value):
        with lock:
            state['now'] += 1
            state['peak'] = max(state['peak'], state['now'])
        try:
            if value.get('slot') == 'initial' and value['entry']['index'] == 1:
                # The first entry is slow, so the second is admitted first.
                time.sleep(0.3)
            return entries_script()(request, value)
        finally:
            with lock:
                state['now'] -= 1
    fixture.transport.scripted = script
    result = await run_import(fixture)
    assert result.state == 'published' and state['peak'] == 2
    parent, review, first, second = result.tasks
    assert [task.kind for task in result.tasks] == ['extract', 'outline_review', 'extract', 'extract']
    assert (first.entry.title, second.entry.title) == ('Systems Notes', 'Queue Review') and first.parent_task_id == parent.id
    # Outline, its review, then one proposal and one review per entry.
    assert [attempt.slot for attempt in result.attempts].count('outline') == 1 and spent_calls(result) == 6
    assert {attempt.model.effort for attempt in result.attempts if attempt.slot in {'outline', 'initial'}} == {'medium'}
    # Each entry request names its lines and the other entries; its reply is one item on a one-item schema.
    calls = {value['slot']: value for value in fixture.transport.calls if 'entry' in value and value['slot'] == 'initial'}
    entry_calls = [value for value in fixture.transport.calls if value.get('slot') == 'initial']
    assert [value['entry']['lines'] for value in entry_calls] == [[ref_of(value, 'paper-a')] for value in entry_calls[:1]] + [
        [ref_of(entry_calls[1], 'paper-b')]]
    assert [other['title'] for other in entry_calls[0]['entry']['others']] == ['Queue Review']
    assert entry_calls[0]['replyProtocol']['rules'][-1].startswith('entry names')
    assert all(len(proposal.reply.payload) == 1 for proposal in result.proposals)
    # The entry reviews see the entry in their task input; the outline review saw the outline.
    review_inputs = [value.value for value in result.review_inputs]
    assert all('entry' in value.semantic_context['taskInput'] for value in review_inputs)
    outline_call = next(value for value in fixture.transport.calls if value.get('slot') == 'outline_review')
    assert [entry['title'] for entry in outline_call['outline']['entries']] == ['Systems Notes', 'Queue Review']
    # The block closed after its entries with their handles, admitted, and shows the papers in the outline's order.
    results = {value.task_id: value for value in result.task_results}
    assert results[parent.id].disposition == 'admitted' and parent.state == 'accepted'
    assert set(results[parent.id].item_handles) == set(results[first.id].item_handles) | set(results[second.id].item_handles)
    assert results[review.id].disposition == 'derived' and results[review.id].value == {'added': [], 'remarks': [], 'diagnostics': []}
    records = fixture.current().project.facts.extensions
    assert [cell.raw_input for record in records for cell in record.cells if cell.field_key == 'journal'] == ['Systems Notes', 'Queue Review']
    assert not result.issues
    assert fixture.text().index('Systems Notes') < fixture.text().index('Queue Review')
    # The same import runs again without a call.
    before = len(fixture.transport.calls)
    assert await run_import(fixture) == result and len(fixture.transport.calls) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['invalid', 'one', 'refused', 'shared'])
async def test_a_block_runs_whole_when_its_outline_gives_no_two_entries(tmp_path, kind):
    from tests.templates.test_semantic_admission import raw_proposal
    fixture = entries_fixture(tmp_path, count=2)
    def outline(value):
        if kind == 'invalid':
            return '{not json'
        if kind == 'one':
            return outline_answer(value, ('paper-a',))
        if kind == 'refused':
            return {'entries': [{'title': 'x', 'first': 'S99', 'last': 'S99'}]}
        return {'entries': [{'title': 'a', 'first': 'S1', 'last': 'S3'}, {'title': 'b', 'first': 'S3', 'last': 'S4'}]}
    def whole(value):
        return raw_proposal(fixture.source)
    fixture.transport.scripted = entries_script(outline=outline, entry=whole)
    result = await run_import(fixture)
    assert result.state == 'published' and len(result.tasks) == 1
    assert [attempt.slot for attempt in result.attempts] == ['outline', 'initial', 'review']
    assert result.task_results[0].disposition == 'admitted' and len(fixture.current().project.facts.extensions) == 2


@pytest.mark.asyncio
async def test_one_call_at_a_time_runs_the_block_whole_without_an_outline(tmp_path):
    # The groups would run one after another, each paying its own call and review: the whole block is faster.
    from tests.templates.test_semantic_admission import raw_proposal
    fixture = entries_fixture(tmp_path, concurrency=1)
    fixture.transport.scripted = entries_script(entry=lambda _value: raw_proposal(fixture.source))
    result = await run_import(fixture)
    assert result.state == 'published' and len(result.tasks) == 1
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'review']


@pytest.mark.asyncio
async def test_the_outline_review_adds_a_missed_entry_and_its_remark_is_the_blocks_notice(tmp_path):
    fixture = entries_fixture(tmp_path, count=3)
    def review(value):
        return {'missing': [{'title': 'Stream Letters', 'first': ref_of(value, 'paper-c'), 'last': ref_of(value, 'paper-c')},
                {'title': 'again', 'first': ref_of(value, 'paper-a'), 'last': ref_of(value, 'paper-a')}],
            'remarks': [{'entries': [1], 'reason': 'Первая запись могла включать вторую.'}]}
    fixture.transport.scripted = entries_script(review=review)
    result = await run_import(fixture)
    assert result.state == 'published'
    parent = result.tasks[0]
    entries = entries_of(result, parent.id)
    assert [(task.entry.title, task.entry.origin) for task in entries] == [('Systems Notes', 'outline'), ('Queue Review', 'outline'),
        ('Stream Letters', 'review')]
    review_task = next(task for task in result.tasks if task.kind == 'outline_review')
    review_result = next(value for value in result.task_results if value.task_id == review_task.id)
    # The second missed entry repeats an outlined one: it adds nothing and is named in the notice.
    assert review_result.value['added'] == [entries[-1].id] and review_result.value['remarks'] == [
        'Первая запись могла включать вторую.', 'Запись «again» из проверки уже входит в другую запись.']
    [issue] = result.issues
    assert issue.code == 'IMPORT_OUTLINE_REMARK' and issue.task_id == review_task.id
    assert issue.message == ('Разметка записей блока под вопросом: Первая запись могла включать вторую. '
        'Запись «again» из проверки уже входит в другую запись.')
    assert issue.category == 'uncertain_interpretation'
    journals = [cell.raw_input for record in fixture.current().project.facts.extensions for cell in record.cells if cell.field_key == 'journal']
    assert journals == ['Systems Notes', 'Queue Review', 'Stream Letters'] and spent_calls(result) == 8


@pytest.mark.asyncio
async def test_an_entry_whose_values_are_rejected_shows_its_own_lines_and_the_others_stay(tmp_path):
    from tests.templates.evidence_references import model_targets
    from tests.templates.test_template_pipeline import failing_review
    fixture = entries_fixture(tmp_path, fallback=False)
    def reviews(value):
        second = any(line.endswith('paper-b\n') for line in [option['text'] for option in value['evidence']
            if option['ref'] in value['semanticContext']['taskInput']['entry']['lines']])
        return failing_review(value, model_targets(value)) if second else {'results': []}
    fixture.transport.scripted = entries_script(reviews=reviews)
    result = await run_import(fixture)
    assert result.state == 'published'
    parent, _review, first, second = result.tasks
    results = {value.task_id: value for value in result.task_results}
    assert results[first.id].disposition == 'admitted' and results[second.id].disposition == 'source_fallback'
    # The repair of the second entry is reviewed as the first was; it still fails, and the entry shows its line.
    assert [attempt.slot for attempt in result.attempts if attempt.task_id == second.id] == ['initial', 'review', 'primary_repair', 'replacement_review']
    assert [span.model_dump() for span in results[second.id].source_spans] == [span.model_dump() for span in second.entry.spans]
    assert results[parent.id].disposition == 'admitted' and parent.state == 'accepted'
    text = fixture.text()
    assert 'Systems Notes' in text and 'https://example.org/paper-b' in text
    [issue] = [issue for issue in result.issues if issue.task_id == second.id]
    assert issue.code == 'IMPORT_SOURCE_FALLBACK'


@pytest.mark.asyncio
async def test_entries_that_run_out_of_the_import_time_fall_back_and_the_block_still_closes(tmp_path):
    fixture = entries_fixture(tmp_path)
    original = fixture.transport.generate
    def generate(request, cancel):
        try:
            return original(request, cancel)
        finally:
            if request.request_value.get('slot') == 'outline':
                # The import limit passes once the outline returned: nothing after it may call the model.
                fixture.now = '2026-10-21T00:05:01+00:00'
    fixture.transport.generate = generate
    fixture.transport.scripted = entries_script()
    result = await run_import(fixture)
    assert result.state == 'published' and result.inference_closed and spent_calls(result) == 1
    parent, review, first, second = result.tasks
    results = {value.task_id: value for value in result.task_results}
    assert results[parent.id].disposition == 'source_fallback' and parent.state == 'source_fallback'
    assert results[review.id].disposition == 'derived' and results[review.id].value['diagnostics'] == ['IMPORT_PROCESSING_EXHAUSTED']
    assert [results[task.id].disposition for task in (first, second)] == ['source_fallback'] * 2
    # Each entry shows its own lines as a cited scope, placed in its block; the outline review says it did not complete.
    assert [results[task.id].value['scope'] for task in (first, second)] == ['cited'] * 2
    assert [[span.model_dump() for span in results[task.id].source_spans] for task in (first, second)] == [
        [span.model_dump() for span in task.entry.spans] for task in (first, second)]
    assert 'https://example.org/paper-a' in fixture.text() and 'https://example.org/paper-b' in fixture.text()
    codes = sorted(issue.code for issue in result.issues)
    assert codes == ['IMPORT_OUTLINE_UNCHECKED', 'IMPORT_SOURCE_FALLBACK', 'IMPORT_SOURCE_FALLBACK']
    assert next(issue.message for issue in result.issues if issue.code == 'IMPORT_OUTLINE_UNCHECKED') == 'Проверка полноты записей блока не завершилась.'


@pytest.mark.asyncio
async def test_a_resumed_import_keeps_the_entries_it_added_and_finishes_them(tmp_path):
    fixture = entries_fixture(tmp_path)
    fixture.transport.scripted = entries_script()
    original = fixture.transport.generate
    def generate(request, cancel):
        result = original(request, cancel)
        if request.request_value.get('slot') == 'outline_review':
            # The process is lost after the outline review's return was saved: the first entry, beside it, ends its own
            # calls; nothing new starts.
            raise RuntimeError('controlled process loss after a saved return')
        return result
    fixture.transport.generate = generate
    with pytest.raises(RuntimeError, match='controlled process loss'):
        await run_import(fixture)
    fixture.transport.generate = original
    operation = fixture.current().pre_draft.template_operations[0]
    assert len(operation.tasks) == 4 and spent_calls(operation) == 4 and len(operation.task_results) == 1
    from tests.templates.pipeline_fixtures import resume_command
    fresh = fixture.restart()
    result = await fresh.run(fixture.project, resume_command(operation), admitted=fixture.admitted)
    assert result.state == 'published' and len(result.tasks) == 4 and spent_calls(result) == 6
    journals = [cell.raw_input for record in fixture.current().project.facts.extensions for cell in record.cells if cell.field_key == 'journal']
    assert journals == ['Systems Notes', 'Queue Review']


def test_the_short_form_declares_per_entry_and_the_bundled_projects_blocks_use_it():
    from packages.resume_core.templates.compiler import compile_template
    from packages.resume_core.templates.shorthand import expand
    from packages.resume_core.templates.store import BUNDLED_TEMPLATES
    from packages.resume_core.templates.projection import SchemaFailure
    definitions = {'text': {'type': ['string', 'null'], 'minLength': 1}}
    def block(**fields):
        return expand({'schema_version': 4, 'content_definitions': definitions, 'blocks': [
            {'id': 'jobs', 'region': 'main', 'order': 1, 'view': {'nodes': []}, 'schema': [{'name': 'text'}], **fields}]})['blocks'][0]
    assert block(per_entry=True)['per_entry'] is True and 'per_entry' not in block()
    with pytest.raises(SchemaFailure):
        expand({'schema_version': 4, 'blocks': [{'id': 'jobs', 'region': 'main', 'order': 1, 'view': {'nodes': []},
            'schema': [{'name': 'text'}], 'per_entries': True}]})
    for path in BUNDLED_TEMPLATES.values():
        package = compile_template(path)
        assert [item.id for item in package.definition.blocks if item.per_entry] == ['projects']
    assert compile_template(BUNDLED_TEMPLATES['generic-two-column']).revision == '2.8.0'
    assert compile_template(BUNDLED_TEMPLATES['generic-one-column']).revision == '1.1.0'


def scheduled(pipeline, tasks, width, spawns):
    """Runs pipeline.run_tasks over fake tasks; a task named in `spawns` reports those children and stays open."""
    events, closed = [], []
    async def execute(_project, _operation, identifier, _deadline, _cancel):
        events.append(identifier)
        await asyncio.sleep(0.01)
        if identifier in spawns:
            return Spawned(identifier, tuple(spawns[identifier]), True)
        return None
    async def close(_project, _operation, parent):
        events.append('close-' + parent)
        closed.append(parent)
    pipeline.execute_task, pipeline.close_entries = execute, close
    operation = SimpleNamespace(id='operation', tasks=[SimpleNamespace(id=name, dependencies=list(after), parent_task_id=None)
        for name, after in tasks], capture=SimpleNamespace(policy=SimpleNamespace(concurrency=width)))
    return pipeline.run_tasks('project', operation, None, threading.Event()), events, closed


@pytest.mark.asyncio
@pytest.mark.parametrize('width', [1, 2])
async def test_a_blocks_entries_start_before_the_blocks_still_queued_and_its_dependents_wait_for_the_close(tmp_path, width):
    # The entries are the rest of the longest chain: queued after every other block, three slots would run the other
    # blocks first and the split would save nothing.
    run, events, closed = scheduled(RuntimeFixture(tmp_path).pipeline, [('a', ()), ('b', ()), ('c', ()), ('d', ('a',))],
        width, {'a': ['a1', 'a2']})
    await run
    assert closed == ['a'] and events.index('a2') < events.index('c')
    assert events.index('close-a') < events.index('d') and events.index('a1') < events.index('close-a')
    assert sorted(name for name in events if not name.startswith('close')) == ['a', 'a1', 'a2', 'b', 'c', 'd']


@pytest.mark.asyncio
async def test_an_entry_holds_every_item_its_lines_state_and_lines_that_state_none_give_an_empty_entry(tmp_path):
    # An outline entry that joins two papers loses neither; a heading the outline names as an entry stays empty.
    fixture = entries_fixture(tmp_path, count=3, concurrency=3)
    def outline(value):
        return {'entries': [{'title': 'Publications', 'first': ref_of(value, 'Publications'), 'last': ref_of(value, 'Publications')},
            {'title': TITLES['paper-a'], 'first': ref_of(value, 'paper-a'), 'last': ref_of(value, 'paper-a')},
            {'title': 'Two papers', 'first': ref_of(value, 'paper-b'), 'last': ref_of(value, 'paper-c')}]}
    fixture.transport.scripted = entries_script(outline=outline)
    result = await run_import(fixture)
    assert result.state == 'published'
    parent = result.tasks[0]
    heading, single, double = entries_of(result, parent.id)
    results = {value.task_id: value for value in result.task_results}
    assert [results[task.id].disposition for task in (heading, single, double)] == ['empty', 'admitted', 'admitted']
    assert sorted(len(proposal.reply.payload) for proposal in result.proposals) == [0, 1, 2]
    assert results[parent.id].disposition == 'admitted' and parent.state == 'accepted'
    journals = [cell.raw_input for record in fixture.current().project.facts.extensions for cell in record.cells if cell.field_key == 'journal']
    assert journals == ['Systems Notes', 'Queue Review', 'Stream Letters'] and not result.issues


@pytest.mark.asyncio
async def test_a_block_whose_entries_kept_their_values_beside_a_remark_is_accepted(tmp_path):
    from tests.templates.evidence_references import model_targets
    from tests.templates.test_template_pipeline import failing_review
    fixture = entries_fixture(tmp_path, fallback=False)
    def reviews(value):
        # Every review rejects the category of its paper and accepts the rest.
        categories = {allocation['cellIds']['status'] for allocation in value['handleMap']}
        return failing_review(value, [target for target in model_targets(value) if target['targetId'] in categories])
    fixture.transport.scripted = entries_script(reviews=reviews)
    result = await run_import(fixture)
    parent, _review, first, second = result.tasks
    results = {value.task_id: value for value in result.task_results}
    assert [(task.state, results[task.id].disposition) for task in (first, second)] == [('accepted', 'source_fallback')] * 2
    assert (parent.state, results[parent.id].disposition) == ('accepted', 'admitted')
    assert len(fixture.current().project.facts.extensions) == 2


@pytest.mark.asyncio
async def test_the_outline_and_its_review_may_name_only_lines(tmp_path):
    # A whole page or unit as a bound would move an entry's first line to the top of that page.
    fixture = entries_fixture(tmp_path)
    seen = {}
    def script(request, value):
        if value.get('slot') in {'outline', 'outline_review'}:
            seen[value['slot']] = request.result_type.full_schema['$defs']['EvidenceRef']['enum']
        return entries_script()(request, value)
    fixture.transport.scripted = script
    result = await run_import(fixture)
    assert result.state == 'published'
    whole = next(option['ref'] for option in fixture.transport.calls[0]['evidence'] if option['text'].count('\n') > 1)
    lines = [option['ref'] for option in fixture.transport.calls[0]['evidence'] if option['text'].count('\n') <= 1]
    assert seen['outline'] == seen['outline_review'] == lines and whole not in seen['outline']


def test_consecutive_outline_entries_join_into_as_many_groups_as_calls_run_at_once():
    from packages.resume_core.template_entries import grouped
    def groups(lines, count):
        return [[title for title, _spans in group] for group in grouped([(str(index), ['line'] * size)
            for index, size in enumerate(lines)], count)]
    assert groups([2] * 12, 3) == [['0', '1', '2', '3'], ['4', '5', '6', '7'], ['8', '9', '10', '11']]
    # Groups have about the same number of lines, keep the outline's order and are never empty.
    assert groups([20, 1, 1, 1, 1], 3) == [['0'], ['1'], ['2', '3', '4']]
    assert groups([1, 1, 1, 1, 20], 3) == [['0', '1', '2'], ['3'], ['4']]
    assert groups([1, 1], 3) == [['0'], ['1']] and groups([1, 1, 1], 2) == [['0', '1'], ['2']]


@pytest.mark.asyncio
async def test_a_group_holds_several_outline_entries_and_the_outline_review_reads_the_entries_not_the_groups(tmp_path):
    fixture = entries_fixture(tmp_path, count=3)
    fixture.transport.scripted = entries_script(outline=lambda value: outline_answer(value, ('paper-a', 'paper-b', 'paper-c')))
    result = await run_import(fixture)
    assert result.state == 'published'
    parent = result.tasks[0]
    first, second = entries_of(result, parent.id)
    assert (first.entry.title, [part.title for part in first.entry.parts]) == ('Systems Notes, Queue Review', ['Systems Notes', 'Queue Review'])
    assert (second.entry.title, len(second.entry.parts)) == ('Stream Letters', 1)
    request = next(value for value in fixture.transport.calls if value.get('slot') == 'initial' and value['entry']['index'] == 1)
    assert [part['title'] for part in request['entry']['parts']] == ['Systems Notes', 'Queue Review'] and len(request['entry']['lines']) == 2
    review = next(value for value in fixture.transport.calls if value.get('slot') == 'outline_review')
    assert [entry['title'] for entry in review['outline']['entries']] == ['Systems Notes', 'Queue Review', 'Stream Letters']
    journals = [cell.raw_input for record in fixture.current().project.facts.extensions for cell in record.cells if cell.field_key == 'journal']
    assert journals == ['Systems Notes', 'Queue Review', 'Stream Letters'] and spent_calls(result) == 6


# Parallel review of the first version (2026-10-29): each case below failed before its fix.

@pytest.mark.asyncio
async def test_a_value_every_entry_states_is_cited_from_each_entrys_own_line(tmp_path):
    # Completion searched the whole source and took the first lines stating a value: the fourth of four entries that
    # share the title cited the other three entries' lines and failed its own review.
    import re
    fixture = entries_fixture(tmp_path, count=4, concurrency=4)
    def lean(value):
        table = {option['ref']: option for option in value['evidence']}
        papers, fields = [], []
        for ref in value['entry']['lines']:
            match = re.fullmatch(r'Reliable Queues, (.+), (\d{4}), (\S+)\n?', table[ref]['text'])
            if match:
                fields += [{'item': None, 'fieldKey': None, 'pointer': '/' + str(len(papers)) + '/' + key, 'evidence': [ref],
                    'effectiveCells': None} for key in ('year', 'status')]
                papers.append({'title': 'Reliable Queues', 'journal': match.group(1), 'year': int(match.group(2)),
                    'url': match.group(3), 'status': 'published'})
        # Title, journal and url are copied word for word: the coordinator cites them.
        return {'schemaVersion': 3, 'payload': papers, 'discoveries': None, 'fields': fields, 'lineage': None, 'relations': None}
    fixture.transport.scripted = entries_script(entry=lean,
        outline=lambda value: outline_answer(value, ('paper-a', 'paper-b', 'paper-c', 'paper-d')))
    result = await run_import(fixture)
    assert result.state == 'published' and not result.issues
    from packages.resume_core.template_import import attempt_in
    entries = entries_of(result, result.tasks[0].id)
    assert len(entries) == 4
    for task in entries:
        [proposal] = [value for value in result.proposals if attempt_in(result, value.attempt_id).task_id == task.id]
        lines = {digest(span) for span in task.entry.spans}
        assert proposal.resolved_fields and all(digest(span) in lines for field in proposal.resolved_fields for span in field.evidence)


@pytest.mark.asyncio
@pytest.mark.parametrize('overlap', ['part', 'whole'])
async def test_a_missed_entry_that_overlaps_an_entry_keeps_its_free_lines_and_is_named_in_the_notice(tmp_path, overlap):
    # A missed entry sharing any line with a running entry was dropped without a word, its free lines unseen.
    fixture = entries_fixture(tmp_path, count=3 if overlap == 'part' else 2)
    def review(value):
        last = 'paper-c' if overlap == 'part' else 'paper-b'
        return {'missing': [{'title': 'Missed', 'first': ref_of(value, 'paper-b'), 'last': ref_of(value, last)}], 'remarks': []}
    fixture.transport.scripted = entries_script(review=review)
    result = await run_import(fixture)
    assert result.state == 'published'
    entries = entries_of(result, result.tasks[0].id)
    [issue] = result.issues
    assert issue.code == 'IMPORT_OUTLINE_REMARK'
    journals = [cell.raw_input for record in fixture.current().project.facts.extensions for cell in record.cells if cell.field_key == 'journal']
    if overlap == 'part':
        # Only the line no entry holds runs as the missed entry.
        assert [(task.entry.title, task.entry.origin, len(task.entry.spans)) for task in entries][-1] == ('Missed', 'review', 1)
        assert journals == ['Systems Notes', 'Queue Review', 'Stream Letters']
        assert 'Запись «Missed» из проверки частично входит в другую запись' in issue.message
    else:
        assert len(entries) == 2 and journals == ['Systems Notes', 'Queue Review']
        assert issue.message.endswith('Запись «Missed» из проверки уже входит в другую запись.')


@pytest.mark.asyncio
@pytest.mark.parametrize(('cap', 'split'), [(3, False), (5, False), (6, True)])
async def test_a_block_splits_only_when_the_outline_its_review_and_two_groups_fit_the_call_cap(tmp_path, cap, split):
    # With three calls left the outline, its review and one group's call took them all and nothing was admitted; the
    # whole block admits its values with a call and a review.
    from tests.templates.entry_fixtures import entry_answer
    from tests.templates.test_semantic_admission import raw_proposal
    fixture = entries_fixture(tmp_path, cap=cap)
    fixture.transport.scripted = entries_script(entry=lambda value: entry_answer(value) if 'entry' in value else raw_proposal(fixture.source))
    result = await run_import(fixture)
    assert result.state == 'published' and len(fixture.current().project.facts.extensions) == 2
    slots = [attempt.slot for attempt in result.attempts]
    if split:
        assert slots.count('outline') == 1 and spent_calls(result) == 6 and len(entries_of(result, result.tasks[0].id)) == 2
    else:
        assert slots == ['initial', 'review'] and len(result.tasks) == 1


def test_per_entry_is_refused_where_entries_could_not_keep_the_lists_limits():
    # A block with maxItems 1 published two entries: each entry's reply kept the limit, the whole list did not.
    from packages.resume_core.templates.compiler import compile_bytes
    from packages.resume_core.templates.projection import SchemaFailure
    from packages.resume_core.templates.store import BUNDLED_TEMPLATE
    from tests.templates.storage_fixtures import package
    import json
    for change in ({'content_schema': {**package().definition.blocks[0].content_schema, 'maxItems': 1}},
            {'content_schema': {**package().definition.blocks[0].content_schema, 'minItems': 2}}):
        config = package().definition.model_dump(mode='json', by_alias=True)
        config['blocks'][0].update(per_entry=True, **change)
        with pytest.raises(SchemaFailure, match='per_entry needs a model block whose content is a list without item limits'):
            compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')
    block = entries_package().definition.blocks[0]
    assert not splits_entries(block.model_copy(update={'content_schema': {**block.content_schema, 'maxItems': 1}}))
