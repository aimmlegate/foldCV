"""Controlled imports publish the real employment assembly."""

import pytest

from packages.resume_core.template_import import spent_calls
from tests.templates.employment_fixtures import employment_package, employment_source
from tests.templates.template_runtime_fixtures import EmploymentFixture, scripted_employment


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['F01', 'F02', 'invalid_metric'])
async def test_real_materializer_publishes_current_employment_and_exact_fallback(tmp_path, case):
    src, raw = employment_source('F02' if case == 'F02' else 'F01')
    unsupported = case == 'invalid_metric'
    fixture = EmploymentFixture(tmp_path, captured=employment_package(), src=src, original_bytes=raw,
        scripted=scripted_employment(src, unsupported=unsupported), cap=4, fallback=False)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.publication.state == 'saved'
    current = fixture.current()
    operation = current.project.template_operations[0]
    assert operation.state == 'published'
    assert spent_calls(operation) == len(fixture.transport.calls) == (4 if unsupported else 2)
    assert len([record for record in current.project.facts.records if record.kind == 'employment']) == 1
    assert fixture.text().count('Implemented queue processing.') == 1
    assert '80%' not in fixture.text()
    if unsupported:
        assert fixture.text().count('Our team reduced median latency from 800 ms to 500 ms.') == 1
        assert current.project.import_issues and all(finding.block_ids for finding in current.project.import_issues)
        assert not any('80%' in str(record.value.value) for record in current.project.facts.records if record.kind == 'claim')
        assert operation.task_results[0].disposition == 'source_fallback'
    elif case == 'F02':
        assert 'Results:' not in fixture.text() and not current.project.import_issues
    else:
        assert 'Results:' in fixture.text() and not current.project.import_issues
    assert current.project.template_package == fixture.package
    assert current.project.sources == [src]
    assert any(part.type == 'fact_field' and part.presentation.node_index is not None
        for block in current.project.document.blocks() for part in block.content)
