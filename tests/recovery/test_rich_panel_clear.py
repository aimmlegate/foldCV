"""Atomic technology clearing preserves other scopes and authored content."""

import pytest

from packages.resume_core.models.rich_document import ParagraphBlock
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_panel import panel_mutation
from tests.recovery.test_rich_panel import apply, edit
from tests.recovery.test_rich_persistence import without_sources
from tests.recovery.test_rich_images_service import service


def populated():
    workspace = without_sources()
    for name, job in [('Python', None), ('Rust', None), ('Python', 'job-1')]:
        workspace = apply(workspace, operation='add', recordKind='technology', jobId=job, values={'display': name})
    return workspace


def clear(workspace, job=None, **values):
    return edit(workspace, operation='clear_technologies', recordId=None, recordKind='technology',
        periodId=None, jobId=job, values={}, **values)


@pytest.mark.parametrize('job', [None, 'job-1'])
def test_clear_has_one_step_per_changed_block_and_preserves_mixed_authored_content(job):
    workspace = populated()
    technologies = [record for record in workspace.project.facts.records if record.kind == 'technology']
    def span(record):
        return {'type': 'fact_field', 'bindingId': f'mixed-{record.id}', 'recordId': record.id,
            'fieldKey': 'display', 'text': record.display.raw_text, 'styles': {'bold': True}, 'syncedFactRevision': 1}
    mixed = ParagraphBlock.model_validate({'id': 'merged', 'revision': 1, 'type': 'paragraph', 'props': {},
        'content': [{'type': 'text', 'text': 'Authored prose: ', 'styles': {'italic': True}},
            *[span(record) for record in technologies]], 'provenance': [], 'children': []})
    pure = mixed.model_copy(deep=True); pure.id = 'pure'
    pure.content = []
    from packages.resume_core.models.rich_document import StyledText
    for record in technologies:
        if pure.content: pure.content.append(StyledText(type='text', text=' · ', styles={}))
        value = span(record); value["bindingId"] = f"pure-{record.id}"
        pure.content.append(type(mixed.content[1]).model_validate(value))
    workspace.project.document.regions[1].blocks += [mixed, pure]
    before = workspace.model_dump_json()
    mutation = panel_mutation(workspace, clear(workspace, job))
    puts = [step.block.id for step in mutation.steps if step.kind == 'put_block']
    assert len(puts) == len(set(puts))
    removed = {record.id for record in technologies if record.job_id == job}
    assert {step.record_id for step in mutation.steps if step.kind == 'remove_record'} == removed
    changed, _ = apply_rich_mutation(workspace, mutation)
    assert workspace.model_dump_json() == before
    assert [record for record in changed.project.facts.records] == [record for record in workspace.project.facts.records if record.id not in removed]
    result = next(block for block in changed.project.document.blocks() if block.id == mixed.id)
    assert result.content[0] == mixed.content[0]
    assert all(span.record_id not in removed for span in result.content[1:])
    assert result.content[1:] == [span for span in mixed.content[1:] if span.record_id not in removed]
    result = next(block for block in changed.project.document.blocks() if block.id == pure.id)
    assert result.content and result.content[0].type == 'fact_field' and result.content[-1].type == 'fact_field'
    assert ''.join(span.text for span in result.content) == ' · '.join(record.display.raw_text for record in technologies if record.id not in removed)
    assert next(block for block in changed.project.document.blocks() if block.id == 'narrative') == next(block for block in workspace.project.document.blocks() if block.id == 'narrative')


def test_empty_clear_is_unchanged_and_does_not_persist_or_infer(tmp_path):
    api, identifier = service(tmp_path)
    workspace = api.read(identifier)
    assert panel_mutation(workspace, clear(workspace)) is None
    api.persist = lambda *args: pytest.fail('No-op clear must not save')
    response = api.panel_preview(identifier, clear(workspace))
    assert response.workspace == workspace


def test_period_buttons_save_other_draft_fields_in_the_same_mutation():
    workspace = without_sources(); job = workspace.project.facts.records[1]; original = job.periods[0]
    changed = apply(workspace, operation='add_period', recordId=job.id, values={'employer': 'Draft employer',
        f'period:{original.id}:end': '2021-02'})
    job = changed.project.facts.records[1]
    assert job.employer.raw_text == 'Draft employer' and len(job.periods) == 2
    assert job.periods[0].end.raw_text == '2021-02'
    changed = apply(changed, operation='remove_period', recordId=job.id, periodId=job.periods[-1].id, values={'role': 'Draft role'})
    assert changed.project.facts.records[1].role.raw_text == 'Draft role'
    assert len(changed.project.facts.records[1].periods) == 1


@pytest.mark.parametrize('change', [
    {'recordKind': 'employment'}, {'recordId': 'candidate-1'}, {'periodId': 'period-1'},
    {'values': {'display': 'Python'}}, {'jobId': 'candidate-1'}, {'jobId': 'missing'}, {'factsRevision': 999},
])
def test_clear_rejects_invalid_payload_and_scope_without_side_effects(change):
    workspace = populated(); before = workspace.model_dump_json()
    values = {'operation': 'clear_technologies', 'recordId': None, 'periodId': None, 'recordKind': 'technology', 'values': {}, **change}
    with pytest.raises(ValueError): panel_mutation(workspace, edit(workspace, **values))
    assert workspace.model_dump_json() == before
