"""Complete review receipts bind every semantic input before effective admission."""

from dataclasses import dataclass

from .models.template_import import CheckTarget, ReviewInput, ReviewReceipt, ReviewReply
from .project_store import strict_json
from .template_identity import capture_span, source_slice
from .template_import import TemplateImportFailure, attempt_in, checked, digest, identity, task_in
from .templates.models import Check
from .templates.compiler import sha256
from .templates.projection import pointer_tokens, validate_payload
from .templates.replies import review_schema
from .template_capture import item_identities


def _matches(pattern, pointer):
    expected, actual = pointer_tokens(pattern), pointer_tokens(pointer)
    return len(expected) <= len(actual) and all(left == '*' or left == right for left, right in zip(expected, actual))


def required_rules(block):
    rules = [rule.model_copy(deep=True) for rule in block.checks]
    used = {rule.id for rule in rules}
    for name, kind, instructions in [
        ('semantic-support', 'semantic_support', 'Check every value, qualification and individual/team attribution against its evidence.'),
        ('source-coverage', 'complete_assignment', 'Check extraction coverage or supported absence for the captured source scope.'),
    ]:
        identifier = 'application:' + name
        while identifier in used:
            identifier += ':required'
        rules.append(Check(id=identifier, kind=kind, version=1, parameters={'fields': [], 'instructions': [instructions]}))
        used.add(identifier)
    return rules


def expected_checks(task, proposal, allocations, rules):
    cells = {allocation.item_handle: allocation.cell_ids for allocation in allocations}
    scope = 'scope-' + task.id
    pairs = set()
    for rule in rules:
        if rule.id == rules[-1].id:
            pairs.add((rule.id, scope))
            continue
        if rule.kind == 'claim_ownership' and proposal.resolved_relations:
            targets = [relation.id for relation in proposal.resolved_relations]
        else:
            targets = [cells[field.item_handle][field.field_key] for field in proposal.resolved_fields
                if not rule.parameters.fields or any(_matches(pattern, field.pointer) for pattern in rule.parameters.fields)]
        pairs.update((rule.id, target) for target in targets or [scope])
    for relation in proposal.resolved_relations:
        support = rules[-2].id
        pairs.add((support, relation.id))
    return [CheckTarget(ruleId=rule, targetId=target) for rule, target in sorted(pairs)]


def make_review_input(operation, proposal, package, sources, policy, *, effective_cells, semantic_context,
                      occurrence_context=None, occurrence_independent=True):
    if proposal.state != 'provisional' or proposal.reply is None:
        raise TemplateImportFailure('IMPORT_PROPOSAL_NOT_REVIEWABLE')
    attempt = attempt_in(operation, proposal.attempt_id)
    task = task_in(operation, attempt.task_id)
    block = next(block for block in package.definition.blocks if block.id == task.block_id)
    rules = required_rules(block)
    handles = set(task.allowed_handles) | {field.item_handle for field in proposal.resolved_fields}
    allocations = [allocation for allocation in item_identities(operation) if allocation.item_handle in handles]
    targets = expected_checks(task, proposal, allocations, rules)
    spans = [capture_span(source, unit) for source in sources for unit in source.units]
    spans += [span for field in proposal.resolved_fields for span in field.evidence]
    spans += [span for relation in proposal.reply.relations for span in relation.evidence]
    spans = list({digest(span): span for span in spans}.values())
    texts = {digest(span): source_slice(sources, span) for span in spans}
    context = dict(semantic_context)
    if not operation.capture.allow_text_rewrite:
        context['sourceWordingPointers'] = sorted({field.pointer for field in proposal.resolved_fields
            if any(_matches(pattern, field.pointer) for pattern in block.rewrite.fields)})
    return ReviewInput(schemaVersion=1, protocol='template_import_v1', proposalHash=proposal.proposal_hash,
        targets=targets, handleMap=allocations, rules=rules, sourceSpans=spans, sourceTexts=texts,
        effectiveCells=effective_cells, relations=proposal.resolved_relations, packageHash=package.package_hash,
        allowTextRewrite=operation.capture.allow_text_rewrite, semanticContext=context, policy=policy,
        occurrenceContext=occurrence_context, occurrenceIndependent=occurrence_independent)


def validate_review_reply(value, expected, sources):
    validate_payload(review_schema(), value)
    reply = ReviewReply.model_validate(value, strict=True)
    pairs = [(result.rule_id, result.target_id) for result in reply.results]
    wanted = [(target.rule_id, target.target_id) for target in expected.targets]
    if len(set(wanted)) != len(wanted) or len(set(pairs)) != len(pairs) or set(pairs) != set(wanted):
        raise TemplateImportFailure('IMPORT_REVIEW_INCOMPLETE')
    if not set(target.rule_id for target in expected.targets) <= {rule.id for rule in expected.rules}:
        raise TemplateImportFailure('IMPORT_REVIEW_TARGET_INVALID')
    for span in expected.source_spans:
        if expected.source_texts.get(digest(span)) != source_slice(sources, span):
            raise TemplateImportFailure('IMPORT_REVIEW_EVIDENCE_CHANGED')
    for result in reply.results:
        for span in result.evidence:
            source_slice(sources, span)
    return reply


def reusable_receipt(operation, value, sources):
    checksum = digest(value)
    for receipt in operation.receipts:
        if receipt.review_input_hash == checksum and receipt.expected_checks == value.targets:
            validate_review_reply(receipt.reply.model_dump(mode='json', by_alias=True), value, sources)
            return receipt
    return None


def record_review(operation, attempt_id, sources, now, *, id_factory=identity):
    result = operation.model_copy(deep=True)
    attempt = attempt_in(result, attempt_id)
    stored = next((record for record in result.review_inputs if record.attempt_id == attempt_id), None)
    if (attempt.slot not in {'review', 'replacement_review'} or stored is None or stored.input_hash != attempt.input_hash
            or digest(stored.value) != attempt.input_hash or attempt.state not in {'returned', 'reconciled'}
            or attempt.outcome != 'completed' or attempt.cleanup.state != 'verified' or attempt.raw_return is None):
        raise TemplateImportFailure('IMPORT_REVIEW_ATTEMPT_INVALID')
    if sha256(attempt.raw_return.encode()) != attempt.raw_return_hash:
        raise TemplateImportFailure('IMPORT_REVIEW_ATTEMPT_INVALID')
    if attempt.review_receipt_id is not None:
        receipt = next((receipt for receipt in result.receipts if receipt.id == attempt.review_receipt_id), None)
        if receipt is None or receipt.review_input_hash != stored.input_hash:
            raise TemplateImportFailure('IMPORT_REVIEW_RECEIPT_INVALID')
        return result, receipt
    outer = strict_json(attempt.raw_return)
    if not isinstance(outer, dict) or set(outer) != {'payload'}:
        raise TemplateImportFailure('IMPORT_REVIEW_INCOMPLETE')
    reply = validate_review_reply(outer['payload'], stored.value, sources)
    receipt = ReviewReceipt(id=id_factory('review'), reviewInputHash=stored.input_hash,
        expectedChecks=stored.value.targets, reply=reply, attemptId=attempt_id, completedAt=now)
    result.receipts.append(receipt)
    attempt.review_receipt_id, attempt.state = receipt.id, 'reconciled'
    task = task_in(result, attempt.task_id)
    task.receipt_ids.append(receipt.id)
    return checked(result), receipt


@dataclass(frozen=True)
class ReviewDecision:
    admitted_cell_ids: tuple[str, ...]
    admitted_relation_ids: tuple[str, ...]
    feedback: tuple[dict, ...]
    unresolved_target_ids: tuple[str, ...]


def decide_review(value, receipt, proposal):
    if receipt.review_input_hash != digest(value) or receipt.expected_checks != value.targets:
        raise TemplateImportFailure('IMPORT_REVIEW_INPUT_CHANGED')
    results = receipt.reply.results
    pairs = [(result.rule_id, result.target_id) for result in results]
    if len(pairs) != len(set(pairs)) or set(pairs) != {(target.rule_id, target.target_id) for target in value.targets}:
        raise TemplateImportFailure('IMPORT_REVIEW_INCOMPLETE')
    failed = {result.target_id for result in results if result.disposition != 'satisfied'}
    targets = {target.target_id for target in value.targets}
    cells = {allocation.item_handle: allocation.cell_ids for allocation in value.handle_map}
    admitted_relations = {relation.id for relation in proposal.resolved_relations if relation.id in targets and relation.id not in failed}
    denied_subjects = {relation.subject_id for relation in proposal.resolved_relations
        if relation.kind in {'owned_by', 'extension_of'} and relation.id not in admitted_relations}
    admitted = []
    for field in proposal.resolved_fields:
        allocation = next(allocation for allocation in value.handle_map if allocation.item_handle == field.item_handle)
        cell_id = cells[field.item_handle][field.field_key]
        if cell_id in targets and cell_id not in failed and allocation.record_id not in denied_subjects:
            admitted.append(cell_id)
    feedback = tuple({'ruleId': result.rule_id, 'targetId': result.target_id, 'reason': result.reason}
        for result in results if result.disposition == 'violation' or result.disposition == 'uncertain'
            and result.actionable and result.reason.strip())
    return ReviewDecision(tuple(admitted), tuple(sorted(admitted_relations)), feedback, tuple(sorted(failed)))
