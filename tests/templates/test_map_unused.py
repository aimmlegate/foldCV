"""T4 of D158, point 10: lines the map gives to no block, and that may hold content, are named in one import notice at the
top of the page, and their retained coverage says why; lines with no content of any block are not named."""

import pytest

from packages.resume_core.sources import capture_span, line_spans, source_slice
from packages.resume_core.templates.materialize import UNUSED_REASON, _retained_coverage
from resume_api.importer.template_pipeline import unused_text
from tests.templates.generic_fixtures import generic_import
from tests.templates.test_source_map import cv_source


def test_the_notice_counts_the_unused_lines_and_quotes_the_first_three():
    assert unused_text(['One line']) == 'Строки резюме не попали ни в один раздел: 1. «One line».'
    long = 'x' * 100
    assert unused_text(['a', 'b', long, 'd', 'e']) == ('Строки резюме не попали ни в один раздел: 5. «a», «b», «' + 'x' * 79
        + '…» и ещё 2.')


def test_retained_text_on_an_unused_line_names_the_reason_and_the_rest_keeps_its_own():
    src = cv_source()
    unit = src.units[0]
    lines = line_spans(src, unit)
    found = []
    # Everything but lines 5 to 7 is shown; of those, line 6 is a line the map gave to no block.
    covered = [capture_span(src, unit, 0, lines[4].start), capture_span(src, unit, lines[7].start, len(unit.text))]
    shown = [type('Coverage', (), {'span': span}) for span in covered]
    _retained_coverage([src], shown, lambda span, _handle, _blocks, disposition, reason: found.append(
        (source_slice([src], span), disposition, reason)), [lines[5]])
    assert found == [(unit.text[lines[4].start:lines[5].start], 'source_only', 'retained outside configured field views'),
        (unit.text[lines[5].start:lines[5].end], 'source_only', UNUSED_REASON),
        (unit.text[lines[6].start:lines[7].start], 'source_only', 'retained outside configured field views')]


@pytest.mark.asyncio
async def test_lines_the_map_gives_no_block_are_named_once_at_the_top_and_kept_as_retained_source(tmp_path):
    def wrap(script):
        def answer(request, value):
            reply = script(request, value)
            if value.get('slot') == 'map':
                hidden = next(option['ref'] for option in value['evidence'] if option['text'].startswith('Open source:'))
                reply['blocks'] = [block for block in reply['blocks'] if block['block'] not in {'languages', 'opensource'}]
                reply['hidden'] = [{'first': hidden, 'last': hidden}]
            return reply
        return answer
    _fixture, result, workspace, _originals = await generic_import(tmp_path, 'F10', source_map=True, wrap=wrap)
    assert result.state == 'published'
    # The languages line is in no block and holds content; the open source line the map named as holding none.
    notices = [issue for issue in result.issues if issue.code == 'IMPORT_SOURCE_UNUSED']
    assert len(notices) == 1 and notices[0].message == 'Строки резюме не попали ни в один раздел: 1. «English».'
    assert notices[0].task_id == next(task.id for task in result.tasks if task.kind == 'map')
    project = workspace.project
    published = next(issue for issue in project.import_issues if issue.code == 'IMPORT_SOURCE_UNUSED')
    assert published.block_ids == [next(iter(project.document.blocks())).id]
    unused = [source_slice(project.sources, value.span) for value in project.import_coverage if value.reason == UNUSED_REASON]
    assert [text.strip() for text in unused] == ['English']
    assert all(value.disposition == 'source_only' for value in project.import_coverage if value.reason == UNUSED_REASON)
    # Without such lines there is no notice.
    _fixture, plain, _workspace, _originals = await generic_import(tmp_path / 'plain', 'F10', source_map=True)
    assert not any(issue.code == 'IMPORT_SOURCE_UNUSED' for issue in plain.issues)
