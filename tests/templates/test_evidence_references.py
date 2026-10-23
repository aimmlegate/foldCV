"""Replies select offered evidence and review checks by reference; the coordinator restores captured identities."""

import asyncio
from copy import deepcopy
import json

import pytest

from packages.resume_core.models.template_import import ReviewInputRecord
from packages.resume_core.template_identity import capture_span, evidence_options
from packages.resume_core.template_import import TemplateImportFailure, digest, dispatch_attempt, record_return, reserve_attempt
from packages.resume_core.template_proposals import parse_proposal
from packages.resume_core.template_review import make_review_input, record_review, reusable_receipt, validate_review_reply
from packages.resume_core.templates.compiler import sha256
from packages.resume_core.templates.projection import SchemaFailure, validate_payload
from packages.resume_core.templates.replies import check_references, proposal_schema, review_schema
from resume_api.providers.dynamic_result import dynamic_result
from tests.templates.evidence_references import by_reference
from tests.templates.pipeline_fixtures import NOW, cleaned, owner, ready_operation, setup_operation, usage
from tests.templates.scripted_template_provider import (ScriptedTemplateProvider, scripted_template_answer,
    scripted_template_result)
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.test_template_import_app import app_client, upload


def offered(src):
    # The whole unit and one narrower span; the narrower one names the paper title only.
    return evidence_options([capture_span(src, src.units[0]), capture_span(src, src.units[0], 0, 5)], [src])


def returned(answer, *, request=None, tamper=None):
    operation = ready_operation()
    _, _, captured, src, facts = setup_operation()
    options = offered(src)
    if request is None:
        request = {'protocol': 'template_import_v1', 'evidence': [value.model_dump(mode='json', by_alias=True) for value in options]}
    if tamper:
        tamper(request)
    task = operation.tasks[0]
    operation, attempt = reserve_attempt(operation, task.id, 'initial', digest(request), operation.capture.primary,
        owner(1), NOW, request_value=request)
    operation = dispatch_attempt(operation, attempt, NOW)
    raw = json.dumps({'payload': answer(src, request)})
    operation = record_return(operation, attempt, raw, 'completed', usage(), cleaned(), returned_at=NOW)
    operation, facts, proposal = parse_proposal(operation, attempt, captured, [src], facts)
    return operation, facts, proposal, captured, src, options, raw


def referenced(src, request):
    return by_reference(raw_proposal(src), request)


def test_reply_schemas_offer_only_the_captured_choices():
    _, _, captured, src, _ = setup_operation()
    content = captured.blocks[0].full_schema
    schema = proposal_schema(content, ['S1', 'S2'])
    assert schema['$defs']['EvidenceRef'] == {'type': 'string', 'enum': ['S1', 'S2']}
    assert dynamic_result(schema).provider_schema['$defs']['EvidenceRef'] == {'type': 'string', 'enum': ['S1', 'S2']}
    reply = referenced(src, {'evidence': [value.model_dump(mode='json', by_alias=True) for value in offered(src)]})
    validate_payload(schema, reply)
    for wrong in ['S3', capture_span(src, src.units[0]).model_dump(mode='json', by_alias=True)]:
        changed = deepcopy(reply)
        changed['fields'][0]['evidence'] = [wrong]
        with pytest.raises(SchemaFailure):
            validate_payload(schema, changed)
    assert 'EvidenceRef' not in proposal_schema(content).get('$defs', {})


def test_coordinator_restores_selected_spans_and_keeps_the_raw_model_return():
    operation, facts, proposal, _, _, options, raw = returned(referenced)
    assert proposal.state == 'provisional', proposal.errors
    attempt = operation.attempts[0]
    assert attempt.raw_return == proposal.raw_return == raw
    assert {ref for field in json.loads(raw)['payload']['fields'] for ref in field['evidence']} == {'S1'}
    assert proposal.reply.schema_version == 1
    assert all(field.evidence == [options[0].span] for field in proposal.reply.fields)
    assert all(field.evidence == [options[0].span] for field in proposal.resolved_fields)
    assert all(value.evidence == [options[0].span] for value in facts.observations)


@pytest.mark.parametrize('case', ['unknown_ref', 'copied_span', 'changed_text'])
def test_unknown_reference_copied_span_or_changed_offer_refuses_the_whole_reply(case):
    def answer(src, request):
        reply = referenced(src, request)
        if case == 'unknown_ref':
            reply['fields'][0]['evidence'] = ['S9']
        elif case == 'copied_span':
            reply['fields'][0]['evidence'] = [capture_span(src, src.units[0]).model_dump(mode='json', by_alias=True)]
        return reply
    def tamper(request):
        if case == 'changed_text':
            request['evidence'][0]['text'] += ' (edited)'
    operation, facts, proposal, *_ = returned(answer, tamper=tamper)
    assert proposal.state == 'invalid' and proposal.errors
    assert not operation.allocations and not facts.observations
    assert operation.attempts[0].outcome == 'invalid_payload' and operation.attempts[0].raw_return


def test_requests_without_references_keep_copied_spans_and_refuse_references():
    _, _, proposal, *_ = returned(lambda src, _request: raw_proposal(src), request={'protocol': 'template_import_v1'})
    assert proposal.state == 'provisional', proposal.errors
    _, _, refused, *_ = returned(lambda src, _request: by_reference(raw_proposal(src),
        {'evidence': [value.model_dump(mode='json', by_alias=True) for value in offered(src)]}),
        request={'protocol': 'template_import_v1'})
    assert refused.state == 'invalid'


def review_returned(operation, proposal, captured, src, results_for):
    value = make_review_input(operation, proposal, captured, [src], operation.capture.primary,
        effective_cells=[], semantic_context={'capturedTaskInput': operation.task_inputs[0].value})
    operation, attempt = reserve_attempt(operation, operation.tasks[0].id, 'review', digest(value), value.policy, owner(2), NOW)
    operation.review_inputs.append(ReviewInputRecord(id='captured-review-input', attemptId=attempt,
        inputHash=digest(value), value=value))
    operation.attempts[-1].review_input_record_id = 'captured-review-input'
    operation = dispatch_attempt(operation, attempt, NOW)
    raw = json.dumps({'payload': {'results': results_for(value)}})
    operation = record_return(operation, attempt, raw, 'completed', usage(), cleaned(), returned_at=NOW)
    return operation, attempt, value, raw


def test_review_selects_checks_and_evidence_by_reference_and_its_receipt_keeps_identities_and_spans():
    operation, _, proposal, captured, src, options, _ = returned(referenced)
    def results(value):
        return [{'check': entry['check'], 'disposition': 'satisfied', 'reason': '', 'evidence': entry.get('evidence', []),
            'actionable': False} for entry in value.semantic_context['checks']]
    operation, attempt, value, raw = review_returned(operation, proposal, captured, src, results)
    assert value.schema_version == 2 and not value.source_spans and not value.source_texts
    assert value.evidence[:2] == options
    checks = {entry['check']: entry for entry in value.semantic_context['checks']}
    assert list(checks) == list(check_references(value)) == ['C' + str(index) for index in range(1, len(value.targets) + 1)]
    assert all((entry['ruleId'], entry['targetId']) == (target.rule_id, target.target_id)
        for entry, target in zip(checks.values(), value.targets, strict=True))
    assert value.semantic_context['proposal']['fields'][0]['evidence'] == ['S1']
    schema = review_schema(value)
    assert schema['$defs']['CheckRef']['enum'] == list(checks) and schema['$defs']['EvidenceRef']['enum'] == ['S1', 'S2']
    assert 'targetId' not in json.dumps(schema['$defs']['ReferencedDisposition'])
    operation, receipt = record_review(operation, attempt, [src], NOW)
    assert [(result.rule_id, result.target_id) for result in receipt.reply.results] == [
        (target.rule_id, target.target_id) for target in value.targets]
    cited = [result for result in receipt.reply.results if result.evidence]
    assert cited and all(result.evidence == [options[0].span] for result in cited)
    assert operation.attempts[-1].raw_return == raw and '"C1"' in raw and 'targetId' not in raw
    assert reusable_receipt(operation, value, [src]) == receipt
    payload = json.loads(raw)['payload']['results']
    for change in [{'check': 'C99'}, {'evidence': ['S99']}, {'targetId': value.targets[0].target_id}]:
        with pytest.raises(SchemaFailure):
            validate_review_reply({'results': [{**payload[0], **change}, *payload[1:]]}, value, [src])
    for incomplete in [payload[1:], [payload[0], *payload]]:
        with pytest.raises(TemplateImportFailure, match='IMPORT_REVIEW_INCOMPLETE'):
            validate_review_reply({'results': incomplete}, value, [src])


class CitingProvider(ScriptedTemplateProvider):
    """The scripted reviewer answers every check by reference and cites the evidence each check names."""

    def generate(self, request, _files, _cancel):
        def answer(value):
            if 'targets' not in value:
                return scripted_template_answer(value)
            return {'results': [{'check': entry['check'], 'disposition': 'satisfied', 'reason': '',
                'evidence': entry.get('evidence', []), 'actionable': False} for entry in value['semanticContext']['checks']]}
        return scripted_template_result(self, request, answer)


@pytest.mark.asyncio
async def test_app_import_selects_evidence_by_reference_and_receipts_retain_restored_spans(tmp_path):
    provider = CitingProvider()
    async with app_client(tmp_path, call_cap=4, provider=provider) as (client, service, _jobs):
        project = (await upload(client)).json()['workspace']['projectId']
        job = (await client.post(f'/v1/rich/projects/{project}/template-import',
            json={'clientRequestId': 'references', 'allowTextRewrite': True})).json()
        async def finished():
            while True:
                current = (await client.post(f'/v1/rich/projects/{project}/jobs/{job["id"]}/read', json={})).json()
                if current.get('templateOutcome') is not None:
                    return current
                await asyncio.sleep(0.05)
        assert (await asyncio.wait_for(finished(), 60))['templateOutcome']['state'] == 'saved'
        operation = service.read(project).project.template_operations[0]
    extraction, review = operation.attempts
    assert [call['kind'] for call in provider.calls] == ['template_extraction', 'template_review']
    assert 'evidence' in extraction.request_value and not {'sourceSpans', 'sourceTexts'} & set(extraction.request_value)
    table = {value['ref']: value for value in extraction.request_value['evidence']}
    reply = json.loads(extraction.raw_return)['payload']
    assert reply['schemaVersion'] == 2 and operation.proposals[0].raw_return == extraction.raw_return
    restored = operation.proposals[0].reply
    for dumped, field in zip(reply['fields'], restored.fields, strict=True):
        assert all(ref in table for ref in dumped['evidence'])
        assert [span.model_dump(mode='json', by_alias=True) for span in field.evidence] == [table[ref]['span'] for ref in dumped['evidence']]
    record = operation.review_inputs[0].value
    assert record.schema_version == 2 and [value.ref for value in record.evidence][:len(table)] == list(table)
    assert 'evidence' not in record.semantic_context['taskInput']
    cited = [result for result in operation.receipts[0].reply.results if result.evidence]
    assert cited and all(span in [value.span for value in record.evidence] for result in cited for span in result.evidence)
    answered = json.loads(review.raw_return)['payload']['results']
    assert [result['check'] for result in answered] == list(check_references(record)) and not any('targetId' in result for result in answered)
    assert all(isinstance(ref, str) for result in answered for ref in result['evidence'])
    assert sha256(review.raw_return.encode()) == review.raw_return_hash
    assert not operation.issues and [task.state for task in operation.tasks] == ['accepted']
