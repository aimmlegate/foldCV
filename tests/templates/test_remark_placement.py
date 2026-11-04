"""D145: a remark on a value the check rejected points at that value where the resume still shows it, never at the lines
the value was cited from (a tester's Kafka version remark marked the summary and every project)."""

import pytest

from packages.resume_core.models.template_document import FieldOccurrence
from tests.templates.generic_fixtures import TABLES, generic_import


pytestmark = pytest.mark.slow

SUMMARY = 'Backend engineer focused on reliable queue systems.'


def rejected_docker(check):
    return 'violation' if check.get('value') == 'Docker' and str(check.get('ruleId', '')).startswith('infrastructure') else None


def showing(project, display):
    """The cells showing a technology named `display` and the blocks showing them."""
    records = {record.id for record in project.facts.records if record.kind == 'technology' and record.display.raw_text == display}
    cells, blocks = set(), set()
    for block in project.document.blocks():
        for span in getattr(block, 'content', None) or ():
            if isinstance(span, FieldOccurrence) and span.record_id in records:
                cells.add(span.cell_id)
                blocks.add(block.id)
    return cells, blocks


@pytest.mark.asyncio
async def test_a_rejected_value_marks_its_shown_twin_and_not_the_lines_it_was_cited_from(tmp_path):
    # The infrastructure block's Docker cites the summary line and the review rejects it; the project's own line shows Docker.
    table = {**TABLES['F10'](True), 'infrastructure': ({'items': ['Docker']}, {'/items/0': SUMMARY})}
    _fixture, result, workspace, _originals = await generic_import(tmp_path, 'F10', table=table, verdict=rejected_docker)
    assert result.state == 'published'
    project = workspace.project
    remark = next(issue for issue in project.import_issues if issue.code == 'IMPORT_SOURCE_FALLBACK')
    cells, blocks = showing(project, 'Docker')
    summary = {block.id for block in project.document.blocks() if SUMMARY in ''.join(
        getattr(span, 'text', '') or '' for span in getattr(block, 'content', None) or ())}
    assert cells and blocks and summary
    assert cells <= set(remark.target_ids) and set(remark.block_ids) == blocks
    assert not summary & set(remark.block_ids)

