"""A complete controlled receipt promotes canonical records, never rejected cells."""

import json

import pytest

from packages.resume_core.template_admission import admit_proposal
from packages.resume_core.template_builtin_admission import apply_builtin_records, make_builtin_candidate
from packages.resume_core.template_import import dispatch_attempt, record_return, reserve_attempt
from packages.resume_core.template_identity import capture_span
from packages.resume_core.template_proposals import parse_proposal
from packages.resume_core.template_review import record_review
from packages.resume_core.templates.compiler import sha256
from tests.templates.employment_fixtures import employment_package, employment_proposal, employment_source
from tests.templates.evidence_references import by_reference
from tests.templates.pipeline_fixtures import NOW, cleaned, owner, ready_operation, usage
from tests.templates.storage_fixtures import papers
from tests.templates.test_builtin_bindings import mapped_reply
from tests.templates.test_semantic_admission import review_attempt


def proposal_ready(tmp_path):
    package, src, reply, _allocated, _options = mapped_reply(tmp_path)
    return proposed_from(package, src, reply.model_dump(mode='json', by_alias=True))


def proposed_from(package, src, reply, *, allow_text_rewrite=True):
    operation = ready_operation(captured=package, src=src, allow_text_rewrite=allow_text_rewrite)
    task = operation.tasks[0]
    operation, attempt = reserve_attempt(operation, task.id, 'initial', task.input_hash,
        operation.capture.primary, owner(1), NOW)
    operation = dispatch_attempt(operation, attempt, NOW)
    operation = record_return(operation, attempt, json.dumps({'payload': reply}),
        'completed', usage(), cleaned(), returned_at=NOW)
    facts = papers()
    facts.extensions = []
    operation, facts, proposed = parse_proposal(operation, attempt, package, [src], facts)
    assert proposed.state == 'provisional', proposed.errors
    assert not facts.records and not facts.extensions
    return operation, facts, proposed, package, src


def accept(operation, facts, proposed, package, src, rejected=()):
    operation, review_id, _review, results = review_attempt(operation, proposed, package, src)
    for value in results:
        if value['targetId'] in rejected:
            value.update(disposition='violation', reason='Unsupported by the retained source', actionable=False)
    attempt = operation.attempts[-1]
    attempt.raw_return = json.dumps({'payload': by_reference({'results': results}, operation.review_inputs[-1].value)})
    attempt.return_hash = attempt.raw_return_hash = sha256(attempt.raw_return.encode())
    operation, receipt = record_review(operation, review_id, [src], NOW)
    return admit_proposal(operation, proposed.id, receipt.id, package, [src], facts,
        expected_revisions={}, expected_relation_revisions={})


@pytest.mark.parametrize('rejected', [None, 'date', 'relation'])
def test_only_admitted_builtin_cells_and_attached_extensions_become_effective(tmp_path, rejected):
    operation, facts, proposed, package, src = proposal_ready(tmp_path)
    first = next(value for value in operation.allocations if value.key == 'job-a')
    target = first.cell_ids['start'] if rejected == 'date' else proposed.resolved_relations[0].id if rejected == 'relation' else None
    operation, review_id, _review, _results = review_attempt(operation, proposed, package, src, fail_target=target)
    operation, receipt = record_review(operation, review_id, [src], NOW)
    admitted, after = admit_proposal(operation, proposed.id, receipt.id, package, [src], facts,
        expected_revisions={}, expected_relation_revisions={})
    assert len(after.records) == 2
    employment = next(record for record in after.records if record.id == first.record_id)
    assert employment.employer.value == employment.employer.raw_text == 'Example a'
    assert employment.role.value is None and employment.role.status == 'unknown'
    if rejected == 'date':
        assert employment.periods == []
        assert first.cell_ids['start'] not in admitted.proposals[0].admitted_cell_ids
        assert next(value for value in after.observations if value.item_handle == first.item_handle and value.field_key == 'start').admission == 'rejected'
    else:
        period = employment.periods[0]
        assert period.id == first.period_ids['employment-period']
        assert period.start.value.precision == 'year' and period.start.value.year == 2020
        assert period.start.value.month is None and period.start.value.day is None
        assert period.start.raw_text == '2020' and period.end.value is None
        assert first.cell_ids['start'] in admitted.proposals[0].admitted_cell_ids
    assert len(after.extensions) == (1 if rejected == 'relation' else 2)
    if rejected == 'relation':
        assert all(relation.id != target for relation in after.relations)
    else:
        extra = next(value for value in after.extensions if value.cells[0].raw_input == 'Scope a')
        assert extra.relations[0].target_id == employment.id
    assert admitted.proposals[0].applied_receipt_id == receipt.id
    assert admit_proposal(admitted, proposed.id, receipt.id, package, [src], after,
        expected_revisions={}, expected_relation_revisions={}) == (admitted, after)


def test_model_replacement_keeps_human_builtin_wording_and_does_not_claim_its_cell(tmp_path):
    operation, facts, proposed, package, src = proposal_ready(tmp_path)
    first = next(value for value in operation.allocations if value.key == 'job-a')
    declaration = next(value for value in package.definition.fact_types if value.id == 'employment')
    fields = [field for field in proposed.resolved_fields if field.item_handle == first.item_handle]
    all_cells = set(first.cell_ids.values())
    record, _applied = make_builtin_candidate(operation, first, declaration, fields, proposed.reply.payload,
        all_cells, [src], facts, {value.id: value for value in package.definition.fact_types}, [])
    record.employer.raw_text = record.employer.value = 'Exact human company'
    record.employer.user_corrected = True
    facts.records = [record]
    candidate, applied = make_builtin_candidate(operation, first, declaration, fields, proposed.reply.payload,
        all_cells, [src], facts, {value.id: value for value in package.definition.fact_types}, [])
    assert candidate.employer == record.employer and first.cell_ids['company'] not in applied
    assert first.cell_ids['start'] in applied


def test_model_split_cannot_retire_a_human_builtin_parent(tmp_path):
    operation, facts, proposed, package, src = proposal_ready(tmp_path)
    allocations = [value for value in operation.allocations if value.semantic_type == 'employment']
    declarations = {value.id: value for value in package.definition.fact_types}
    incoming = {}
    for allocation in allocations:
        fields = [field for field in proposed.resolved_fields if field.item_handle == allocation.item_handle]
        record, _applied = make_builtin_candidate(operation, allocation, declarations['employment'], fields,
            proposed.reply.payload, set(allocation.cell_ids.values()), [src], facts, declarations, [])
        incoming[allocation.item_handle] = record
    parent = next(iter(incoming.values())).model_copy(deep=True)
    parent.id, parent.user_corrected = 'human-parent', True
    facts.records = [parent]
    parent_allocation = allocations[0].model_copy(update={'item_handle': 'human-parent-handle', 'record_id': parent.id,
        'canonical_fields': {}, 'period_ids': {}, 'cell_ids': {}})
    from packages.resume_core.models.template_facts import Lineage
    lineage = [Lineage(kind='split', parents=['human-parent-handle'], children=list(incoming), attemptId='repair')]
    after = apply_builtin_records(facts, incoming, [parent_allocation, *allocations], lineage,
        accepted_handles=list(incoming), expected_revisions={'human-parent-handle': parent.revision}, action_id='repair')
    assert after == facts and not after.tombstones


@pytest.mark.parametrize('fixture', ['F01', 'F02'])
def test_employment_source_keeps_date_precision_and_distinct_owned_items(fixture):
    package = employment_package()
    src, _raw = employment_source(fixture)
    operation, facts, proposed, _package, _src = proposed_from(package, src, employment_proposal(src))
    admitted, after = accept(operation, facts, proposed, package, src)
    assert len([record for record in after.records if record.kind == 'employment']) == 1
    job = next(record for record in after.records if record.kind == 'employment')
    assert job.employer.value == 'Example Labs' and job.role.value == 'backend engineer'
    assert job.periods[0].start.value.precision == ('month' if fixture == 'F01' else 'year')
    assert job.periods[0].start.value.month == (3 if fixture == 'F01' else None)
    assert job.periods[0].start.value.day is None
    claims = [record for record in after.records if record.kind == 'claim']
    assert len(claims) == (2 if fixture == 'F01' else 1)
    assert all(record.job_id == job.id for record in claims)
    assert len({record.id for record in claims}) == len(claims)
    assert next(record for record in after.records if record.kind == 'technology').display.value == 'Python'
    assert next(record for record in after.records if record.kind == 'technology').job_id == job.id
    categories = [cell.typed_value for record in after.extensions for cell in record.cells if cell.field_key == 'category']
    assert sorted(categories) == (['result', 'task'] if fixture == 'F01' else ['task'])
    assert admitted.proposals[0].admitted_cell_ids


@pytest.mark.parametrize('rewrite', [True, False])
def test_disabled_rewriting_retains_source_display_even_if_review_accepts_a_paraphrase(rewrite):
    package = employment_package()
    src, _raw = employment_source()
    reply = employment_proposal(src)
    paraphrase = 'Built asynchronous queue processing.'
    reply['payload'][0]['tasks'][0]['value'] = paraphrase
    operation, facts, proposed, _package, _src = proposed_from(package, src, reply, allow_text_rewrite=rewrite)
    admitted, after = accept(operation, facts, proposed, package, src)
    allocation = next(value for value in admitted.allocations if value.key == 'tasks-entry')
    claim = next(record for record in after.records if record.id == allocation.record_id)
    assert claim.value.value == paraphrase
    expected = paraphrase if rewrite else 'Implemented queue processing.'
    assert claim.value.raw_text == expected
    from packages.resume_core.template_effective import builtin_effective_cells
    cell = next(cell for cell in builtin_effective_cells(after, [admitted]) if cell.id == allocation.cell_ids['value'])
    assert cell.raw_input == expected and cell.typed_value == paraphrase
    stored = admitted.review_inputs[0].value
    assert ('/0/tasks/0/value' in stored.semantic_context.get('sourceWordingPointers', [])) is not rewrite


def test_rejected_individual_metric_and_its_classification_do_not_survive_as_effective_facts():
    package = employment_package()
    src, _raw = employment_source()
    operation, facts, proposed, _package, _src = proposed_from(package, src, employment_proposal(src, unsupported=True))
    bad = next(value for value in operation.allocations if value.key == 'results-entry')
    attribution = next(value for value in operation.allocations if value.key == 'results-entry-classification')
    admitted, after = accept(operation, facts, proposed, package, src,
        [bad.cell_ids['value'], attribution.cell_ids['attribution']])
    assert not any(record.kind == 'metric' for record in after.records)
    assert not any(record.id == bad.record_id for record in after.records)
    assert not any(record.item_handle == attribution.item_handle for record in after.extensions)
    assert next(record for record in after.records if record.kind == 'employment').employer.value == 'Example Labs'
    assert any(record.kind == 'claim' and record.value.value == 'Implemented queue processing.' for record in after.records)
    observation = next(value for value in after.observations if value.item_handle == bad.item_handle)
    assert observation.admission == 'rejected' and '80%' in observation.raw_input
    assert bad.cell_ids['value'] not in admitted.proposals[0].admitted_cell_ids


def test_rejected_owner_withholds_its_entire_nested_dependency_chain():
    package = employment_package()
    src, _raw = employment_source()
    operation, facts, proposed, _package, _src = proposed_from(package, src, employment_proposal(src))
    job = next(value for value in operation.allocations if value.key == 'job')
    _admitted, after = accept(operation, facts, proposed, package, src, set(job.cell_ids.values()))
    assert not after.records and not after.extensions and not after.relations
    assert after.observations and all(value.admission in {'rejected', 'uncertain'} for value in after.observations)


def test_disabled_rewriting_shows_a_cited_line_without_its_line_break():
    # Reference replies cite whole lines; the closing line break is not part of the source wording.
    package = employment_package()
    src, _raw = employment_source()
    reply = employment_proposal(src)
    unit = src.units[0]
    start = unit.text.index('Implemented queue processing.')
    line = capture_span(src, unit, start, unit.text.index('\n', start) + 1).model_dump(by_alias=True)
    field = next(value for value in reply['fields'] if value['pointer'] == '/0/tasks/0/value')
    field['evidence'] = [line]
    reply['payload'][0]['tasks'][0]['value'] = 'Built asynchronous queue processing.'
    operation, facts, proposed, _package, _src = proposed_from(package, src, reply, allow_text_rewrite=False)
    admitted, after = accept(operation, facts, proposed, package, src)
    allocation = next(value for value in admitted.allocations if value.key == 'tasks-entry')
    claim = next(record for record in after.records if record.id == allocation.record_id)
    assert claim.value.raw_text == 'Implemented queue processing.'
