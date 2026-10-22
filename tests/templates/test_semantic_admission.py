"""Complete controlled receipts gate facts; these checks do not measure model quality."""

import json

import pytest

from packages.resume_core.models.template_import import ReviewInputRecord
from packages.resume_core.template_admission import admit_proposal
from packages.resume_core.template_identity import capture_span
from packages.resume_core.template_import import (TemplateImportFailure, digest, dispatch_attempt, record_return,
    reserve_attempt)
from packages.resume_core.template_proposals import parse_proposal
from packages.resume_core.template_review import (decide_review, make_review_input, record_review, reusable_receipt,
    validate_review_reply)
from packages.resume_core.templates.projection import SchemaFailure, project_payload, validate_payload
from packages.resume_core.templates.replies import proposal_schema, review_schema
from packages.resume_core.templates.compiler import sha256
from tests.templates.pipeline_fixtures import NOW, cleaned, owner, ready_operation, setup_operation, usage


def raw_proposal(source, *, empty=False):
    span = capture_span(source, source.units[0]).model_dump(by_alias=True)
    payload = [] if empty else [{'title': 'Reliable Queues', 'journal': journal, 'year': year,
        'url': 'https://example.org/paper-' + key, 'status': 'published'}
        for key, journal, year in [('a', 'Systems Notes', 2024), ('b', 'Queue Review', 2025)]]
    return {'schemaVersion': 1, 'payload': payload,
        'discoveries': [{'key': key, 'semanticType': 'papers', 'pointer': '/' + str(index)}
            for index, key in enumerate(['a', 'b'])] if not empty else [],
        'fields': [{'item': {'kind': 'discovery_key', 'key': key}, 'fieldKey': field,
            'pointer': '/' + str(index) + '/' + field, 'evidence': [span], 'effectiveCellIds': []}
            for index, key in enumerate(['a', 'b']) for field in payload[index]] if not empty else [],
        'lineage': [{'kind': 'add', 'parents': [], 'children': ['a', 'b']}] if not empty else [], 'relations': []}


def proposed(*, empty=False, corrupt=None):
    operation = ready_operation()
    _, _, package, source, facts = setup_operation()
    task = operation.tasks[0]
    value = raw_proposal(source, empty=empty)
    if corrupt:
        corrupt(value)
    operation, attempt = reserve_attempt(operation, task.id, 'initial', task.input_hash,
        operation.capture.primary, owner(1), NOW)
    operation = dispatch_attempt(operation, attempt, NOW)
    operation = record_return(operation, attempt, json.dumps({'payload': value}), 'completed', usage(), cleaned(), returned_at=NOW)
    operation, facts, proposal = parse_proposal(operation, attempt, package, [source], facts)
    return operation, facts, proposal, package, source


def review_attempt(operation, proposal, package, source, *, fail_target=None):
    task = operation.tasks[0]
    value = make_review_input(operation, proposal, package, [source], operation.capture.primary,
        effective_cells=[], semantic_context={'capturedTaskInput': operation.task_inputs[0].value})
    results = [{'ruleId': target.rule_id, 'targetId': target.target_id,
        'disposition': 'violation' if target.target_id == fail_target else 'satisfied',
        'reason': 'Not supported by retained source' if target.target_id == fail_target else '',
        'evidence': [], 'actionable': target.target_id == fail_target} for target in value.targets]
    operation, attempt = reserve_attempt(operation, task.id, 'review', digest(value), value.policy, owner(2), NOW)
    operation.review_inputs.append(ReviewInputRecord(id='captured-review-input', attemptId=attempt,
        inputHash=digest(value), value=value))
    operation.attempts[-1].review_input_record_id = 'captured-review-input'
    operation = dispatch_attempt(operation, attempt, NOW)
    operation = record_return(operation, attempt, json.dumps({'payload': {'results': results}}),
        'completed', usage(), cleaned(), returned_at=NOW)
    return operation, attempt, value, results


def test_raw_schema_failure_is_retained_without_observations_handles_or_review():
    operation, facts, proposal, _, _ = proposed(corrupt=lambda value: value['payload'][0].update({'year': 'forthcoming'}))
    assert proposal.state == 'invalid' and proposal.errors
    assert not operation.allocations and not facts.observations and not facts.extensions
    assert operation.attempts[0].raw_return and operation.attempts[0].usage == usage()
    assert not operation.receipts and operation.attempts[0].outcome == 'invalid_payload'


def test_safe_proposal_is_provisional_and_duplicate_return_reuses_allocations_and_observations():
    operation, facts, proposal, package, source = proposed()
    assert proposal.state == 'provisional' and not facts.extensions
    assert len(facts.observations) == 10 and all(value.admission == 'provisional' for value in facts.observations)
    again, unchanged, same = parse_proposal(operation, proposal.attempt_id, package, [source], facts)
    assert again == operation and unchanged == facts and same == proposal


@pytest.mark.parametrize('failure', ['missing', 'extra', 'duplicate', 'conflict', 'invalid_evidence'])
def test_incomplete_review_has_no_receipt_or_effective_promotion(failure):
    operation, facts, proposal, package, source = proposed()
    operation, attempt, _, results = review_attempt(operation, proposal, package, source)
    if failure == 'missing':
        results.pop()
    elif failure == 'extra':
        results.append({**results[0], 'targetId': 'unknown-target'})
    elif failure == 'duplicate':
        results.append(results[0])
    elif failure == 'conflict':
        results.append({**results[0], 'disposition': 'violation'})
    else:
        span = capture_span(source, source.units[0]).model_dump(by_alias=True)
        span['sliceHash'] = digest('wrong-evidence')
        results[0]['evidence'] = [span]
    operation.attempts[-1].raw_return = json.dumps({'payload': {'results': results}})
    operation.attempts[-1].raw_return_hash = operation.attempts[-1].return_hash = sha256(operation.attempts[-1].raw_return.encode())
    with pytest.raises((TemplateImportFailure, ValueError)):
        record_review(operation, attempt, [source], NOW)
    assert not operation.receipts and not facts.extensions


def test_complete_receipt_promotes_only_supported_cells_and_retains_rejected_observation():
    operation, facts, proposal, package, source = proposed()
    rejected = operation.allocations[1].cell_ids['journal']
    operation, attempt, value, _ = review_attempt(operation, proposal, package, source, fail_target=rejected)
    operation, receipt = record_review(operation, attempt, [source], NOW)
    decision = decide_review(value, receipt, proposal)
    assert rejected not in decision.admitted_cell_ids and decision.feedback
    operation, facts = admit_proposal(operation, proposal.id, receipt.id, package, [source], facts,
        expected_revisions={}, expected_relation_revisions={})
    assert len(facts.extensions) == 2
    assert [cell.typed_value for cell in facts.extensions[0].cells if cell.field_key == 'journal'] == ['Systems Notes']
    assert 'journal' not in {cell.field_key for cell in facts.extensions[1].cells}
    assert next(value for value in facts.observations if value.item_handle == operation.allocations[1].item_handle
        and value.field_key == 'journal').admission == 'rejected'
    assert operation.proposals[0].applied_receipt_id == receipt.id
    assert admit_proposal(operation, proposal.id, receipt.id, package, [source], facts,
        expected_revisions={}, expected_relation_revisions={}) == (operation, facts)


def test_empty_extraction_needs_completed_scope_review_and_has_no_effective_values():
    operation, facts, proposal, package, source = proposed(empty=True)
    operation, attempt, value, _ = review_attempt(operation, proposal, package, source)
    assert value.targets and all(target.target_id == 'scope-' + operation.tasks[0].id for target in value.targets)
    operation, receipt = record_review(operation, attempt, [source], NOW)
    operation, facts = admit_proposal(operation, proposal.id, receipt.id, package, [source], facts,
        expected_revisions={}, expected_relation_revisions={})
    assert not facts.extensions and not facts.observations


@pytest.mark.parametrize('changed', ['owner', 'effective', 'rewrite', 'policy', 'context'])
def test_receipt_reuse_requires_equal_full_semantic_input(changed):
    operation, _, proposal, package, source = proposed()
    operation, attempt, value, _ = review_attempt(operation, proposal, package, source)
    operation, receipt = record_review(operation, attempt, [source], NOW)
    assert reusable_receipt(operation, value, [source]) == receipt
    altered = value.model_copy(deep=True)
    if changed == 'owner':
        altered.semantic_context['owner'] = 'another-employer'
    elif changed == 'effective':
        altered.semantic_context['effectiveRaw'] = 'New human wording'
    elif changed == 'rewrite':
        altered.allow_text_rewrite = not altered.allow_text_rewrite
    elif changed == 'policy':
        altered.policy.model = 'another-captured-review-model'
    else:
        altered.occurrence_context, altered.occurrence_independent = {'block': 'another-view'}, False
    assert altered.proposal_hash == value.proposal_hash
    assert reusable_receipt(operation, altered, [source]) is None


def test_uncertainty_needs_a_concrete_actionable_reason_to_enter_repair():
    operation, _, proposal, package, source = proposed()
    operation, attempt, value, results = review_attempt(operation, proposal, package, source)
    target = next(result for result in results if not result['targetId'].startswith('scope-'))
    target.update({'disposition': 'uncertain', 'reason': 'Unclear attribution', 'actionable': False})
    operation.attempts[-1].raw_return = json.dumps({'payload': {'results': results}})
    operation.attempts[-1].raw_return_hash = operation.attempts[-1].return_hash = sha256(operation.attempts[-1].raw_return.encode())
    operation, receipt = record_review(operation, attempt, [source], NOW)
    assert not decide_review(value, receipt, proposal).feedback
    receipt.reply.results[next(i for i, result in enumerate(results) if result is target)].actionable = True
    assert decide_review(value, receipt, proposal).feedback


def test_reply_schemas_keep_payload_constraints_and_user_property_names_exact():
    content = {'type': 'object', 'additionalProperties': False, 'required': ['default', 'oneOf', 'discriminator'],
        'properties': {name: {'type': 'string'} for name in ['default', 'oneOf', 'discriminator']},
        'if': {'properties': {'default': {'const': 'x'}}}, 'then': {'properties': {'oneOf': {'minLength': 2}}}}
    schema = proposal_schema(content)
    assert schema['properties']['payload'] == content
    project_payload(schema)
    validate_payload(review_schema(), {'results': []})
    value = {'schemaVersion': 1, 'payload': {'default': 'x', 'oneOf': 'a', 'discriminator': 'tag'},
        'discoveries': [], 'fields': [], 'lineage': [], 'relations': []}
    with pytest.raises(SchemaFailure):
        validate_payload(schema, value)
