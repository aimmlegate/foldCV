"""T4 of D158: with a usable map each block's calls see only its lines, a block the map gives no line ends empty without
a call, and a block that rewrites a summary of the CV still reads all of it. A scripted import publishes the same
document as without the map."""

import pytest

from packages.resume_core.editing.template_wording import captured_text
from packages.resume_core.hashing import digest
from packages.resume_core.importing.template_identity import evidence_options
from packages.resume_core.importing.template_map import block_evidence, reads_whole_cv, whole_source
from packages.resume_core.sources import capture_span, line_spans
from packages.resume_core.templates.replies import MAPPED_REVIEW_PROTOCOL, REVIEW_PROTOCOL
from tests.templates.generic_fixtures import TABLES, generic_import, generic_package
from tests.templates.test_source_map import cv_source, line, table
from tests.templates.test_template_view_adapters import text


def test_a_block_is_offered_its_lines_under_the_maps_refs_and_a_unit_whole_only_with_all_its_lines():
    src = cv_source()
    offered = table(src)
    job, duty = line(offered, 'Example Labs — backend engineer, 03.2020 – 11.2023'), line(offered, '- Kept the release train running')
    unit = src.units[0]
    cell = capture_span(src, unit, unit.text.index('Python'), unit.text.index('Python') + len('Python'))
    evidence = block_evidence({'blocks': {'projects': [job, duty]}}, offered, 'projects', [cell], [src])
    refs = [option.ref for option in evidence]
    # The block's two lines keep the map's refs; the one-unit CV is not offered whole; the cell's span is new.
    assert refs[:2] == [job, duty] and len(refs) == 3 and refs[2] not in offered
    assert evidence[2].span == cell and int(refs[2][1:]) > max(int(ref[1:]) for ref in offered)
    every = [option.ref for option in offered.values() if '\n' not in option.text.strip()]
    whole = block_evidence({'blocks': {'skills': every}}, offered, 'skills', [], [src])
    assert [option.ref for option in whole] == list(offered)


def test_a_block_that_rewrites_a_summary_reads_the_whole_cv_and_the_others_their_lines():
    package = generic_package()
    blocks = {block.id: block for block in package.definition.blocks}
    rewrite = type('Task', (), {'kind': 'rewrite'})
    extract = type('Task', (), {'kind': 'extract'})
    assert reads_whole_cv(rewrite, blocks['summary'], package.definition)
    assert reads_whole_cv(rewrite, blocks['career_highlights'], package.definition)
    # Without rewriting the summary keeps the source's own summary: its lines are enough.
    assert not reads_whole_cv(extract, blocks['summary'], package.definition)
    assert not reads_whole_cv(rewrite, blocks['projects'], package.definition)
    identity = blocks['identity'].model_copy(update={'rewrite': blocks['summary'].rewrite})
    assert not reads_whole_cv(rewrite, identity, package.definition)


def test_a_value_cited_over_lines_offered_one_by_one_reads_as_their_text():
    src = cv_source()
    unit = src.units[0]
    lines = line_spans(src, unit)
    offered = [(span, unit.text[span.start:span.end]) for span in lines[3:6]]
    key = (src.id, src.revision, unit.id, unit.revision)
    start, end = lines[3].start, lines[5].end
    assert captured_text(offered, key, start, end) == unit.text[start:end]
    assert captured_text(offered, key, lines[4].start + 2, lines[4].end - 1) == unit.text[lines[4].start + 2:lines[4].end - 1]
    # A gap between the offered lines is not captured; with the whole unit offered nothing changes.
    assert captured_text([offered[0], offered[2]], key, start, end) is None
    assert captured_text([(capture_span(src, unit), unit.text)], key, start, end) == unit.text[start:end]


def requests(fixture, block_id):
    return [value for value in fixture.transport.calls if (value.get('declaration') or {}).get('id') == block_id]


def reviews(result, block_id):
    tasks = {task.id: task for task in result.tasks}
    return [record.value for record in result.review_inputs
        if tasks[next(attempt.task_id for attempt in result.attempts if attempt.id == record.attempt_id)].block_id == block_id]


@pytest.mark.asyncio
async def test_with_a_map_each_block_reads_its_lines_a_block_without_lines_makes_no_call_and_a_summary_reads_all(tmp_path):
    fixture, result, workspace, _originals = await generic_import(tmp_path, 'F01', source_map=True)
    assert result.state == 'published'
    tasks = {task.id: task for task in result.tasks}
    results = {tasks[value.task_id].block_id: value for value in result.task_results}
    every = evidence_options(whole_source([fixture.source]), [fixture.source])
    # Blocks the scripted CV states nothing for end empty by rule, without a call or a captured input.
    empty = sorted(block for block, value in results.items() if value.value == {'map': 'no_lines'})
    assert empty == ['courses', 'education', 'focus', 'languages', 'location', 'opensource', 'portfolio']
    assert not any(tasks[attempt.task_id].block_id in empty for attempt in result.attempts)
    assert not any(tasks[value.task_id].block_id in empty for value in result.task_inputs)
    projects, summary = requests(fixture, 'projects')[0], requests(fixture, 'summary')[0]
    value_map = next(value.value for value in result.task_results if tasks[value.task_id].kind == 'map')
    assert [option['ref'] for option in projects['evidence']] == value_map['blocks']['projects'] and projects['mapped'] is True
    # The summary rewrites: it reads the whole CV, unmarked, as without a map.
    assert len(summary['evidence']) == len(every) and 'mapped' not in summary
    trimmed, whole = reviews(result, 'projects')[0], reviews(result, 'summary')[0]
    assert trimmed.semantic_context['replyProtocol'] == MAPPED_REVIEW_PROTOCOL
    assert {option.ref for option in trimmed.evidence} <= set(value_map['blocks']['projects'])
    assert whole.semantic_context['replyProtocol'] == REVIEW_PROTOCOL and len(whole.evidence) >= len(every)
    # The model never sees the mark.
    assert '"mapped"' not in fixture.transport.prompts[[value.get('declaration', {}).get('id') for value in
        fixture.transport.calls].index('projects')]
    assert {digest(option.span) for option in trimmed.evidence} >= {digest(span) for field in next(
        proposal for proposal in result.proposals if proposal.applied_receipt_id is not None
        and tasks[next(a.task_id for a in result.attempts if a.id == proposal.attempt_id)].block_id == 'projects').resolved_fields
        for span in field.evidence}


def document(workspace):
    return [text(block) for block in workspace.project.document.blocks() if block.type != 'section']


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.parametrize('name,concurrency,rewrite', [('F10', 1, True), ('F10', 3, True), ('F10', 1, False), ('F04', 3, False),
    ('F07', 1, True), ('F06', 1, True)])
async def test_a_scripted_import_with_a_map_publishes_the_document_it_publishes_without_one(tmp_path, name, concurrency, rewrite):
    table = TABLES[name](rewrite)
    mapped, result, workspace, _originals = await generic_import(tmp_path / 'map', name, source_map=True,
        concurrency=concurrency, rewrite=rewrite, table=table)
    plain, baseline, before, _originals = await generic_import(tmp_path / 'base', name, concurrency=concurrency,
        rewrite=rewrite, table=table)
    assert result.state == baseline.state == 'published'
    assert document(workspace) == document(before)
    assert [issue.code for issue in result.issues] == [issue.code for issue in baseline.issues]
    # Fewer calls (empty blocks make none) and shorter requests, the map's included.
    assert len(mapped.transport.calls) < len(plain.transport.calls)
    assert sum(map(len, mapped.transport.prompts)) < sum(map(len, plain.transport.prompts))
