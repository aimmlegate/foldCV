"""Complete review receipts bind every semantic input before effective admission."""

from dataclasses import dataclass
import json

from .models.template_import import CheckTarget, ReferencedReviewReply, ReviewInput, ReviewReceipt, ReviewReply
from .project_store import strict_json
from .template_identity import capture_span, evidence_options, offered_evidence, payload_value, restore_evidence, source_slice
from .template_import import TemplateImportFailure, attempt_in, checked, digest, identity, task_in
from .templates.models import Check
from .templates.compiler import sha256
from .templates.projection import pointer_tokens, validate_payload
from .templates.replies import REVIEW_PROTOCOL, check_references, review_protocol, review_schema
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


def review_texts(review):
    """Every evidence span a review input offers, with its captured text, in either input version."""
    if review.schema_version == 1:
        return [(span, review.source_texts.get(digest(span))) for span in review.source_spans]
    return [(option.span, option.text) for option in review.evidence]


def review_checks(task, proposal, allocations, targets, refs):
    """One entry per check ref: its rule and target, with the payload value and evidence refs the target cites."""
    by_handle = {allocation.item_handle: allocation for allocation in allocations}
    # Discovery keys are reply-local: only this attempt's allocations map to the reply's item pointers.
    pointers = {discovery.key: discovery.pointer for discovery in proposal.reply.discoveries}
    records = {allocation.record_id: pointers[allocation.key] if getattr(allocation, 'discovery_attempt_id', None)
        == proposal.attempt_id and allocation.key in pointers else allocation.item_handle for allocation in allocations}
    fields = {by_handle[field.item_handle].cell_ids[field.field_key]: field for field in proposal.resolved_fields}
    relations = {resolved.id: (resolved, proposed)
        for resolved, proposed in zip(proposal.resolved_relations, proposal.reply.relations, strict=True)}
    checks = []
    for index, target in enumerate(targets, 1):
        entry = {'check': 'C' + str(index), 'ruleId': target.rule_id, 'targetId': target.target_id}
        if target.target_id in fields:
            field = fields[target.target_id]
            entry.update(kind='field', semanticType=by_handle[field.item_handle].semantic_type, fieldKey=field.field_key,
                pointer=field.pointer, value=payload_value(proposal.reply.payload, field.pointer),
                evidence=[refs[digest(span)] for span in field.evidence])
        elif target.target_id in relations:
            resolved, proposed = relations[target.target_id]
            entry.update(kind='relation', relation=resolved.kind, subject=records.get(resolved.subject_id, resolved.subject_id),
                target=records.get(resolved.target_id, resolved.target_id),
                evidence=[refs[digest(span)] for span in proposed.evidence])
        else:
            entry.update(kind='scope', block=task.block_id)
        checks.append(entry)
    return checks


def grouped_checks(checks):
    """Each target once with its value and evidence, then {check ref: rule} for every check of it.

    LIVE-05: 477 per-check entries repeated each value, internal id and rule name (130k characters per review input,
    stored again with every attempt); a field is checked by up to seven rules, so grouping states each value once.
    The coordinator restores rules and targets from the captured targets by check ref, never from these entries."""
    groups = {}
    for check in checks:
        kind = check.get('kind')
        if kind == 'field':
            head = {'pointer': check.get('pointer'), 'value': check.get('value'), 'evidence': check.get('evidence', [])}
        elif kind == 'relation':
            head = {'relation': check.get('relation'), 'subject': check.get('subject'), 'target': check.get('target'),
                'evidence': check.get('evidence', [])}
        else:
            head = {'scope': check.get('block')}
        key = json.dumps(head, ensure_ascii=False, sort_keys=True)
        groups.setdefault(key, {**head, 'checks': {}})['checks'][check['check']] = check['ruleId']
    return list(groups.values())


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
    # References the proposal request offered keep their names, so the proposal reads the same in review.
    evidence = evidence_options(spans, sources, base=list((offered_evidence(attempt.request_value) or {}).values()))
    refs = {digest(option.span): option.ref for option in evidence}
    shown = proposal.reply.model_dump(mode='json', by_alias=True)
    for dumped, field in zip(shown['fields'], proposal.reply.fields, strict=True):
        dumped['evidence'] = [refs[digest(span)] for span in field.evidence]
    shown['relations'] = [{**relation.model_dump(mode='json', by_alias=True),
        'evidence': [refs[digest(span)] for span in relation.evidence]} for relation in proposal.reply.relations]
    # The proposal is shown in its resolved form with evidence named by the review's references.
    context = {**semantic_context, 'replyProtocol': REVIEW_PROTOCOL, 'proposal': shown,
        'checks': grouped_checks(review_checks(task, proposal, allocations, targets, refs))}
    if not operation.capture.allow_text_rewrite:
        context['sourceWordingPointers'] = sorted({field.pointer for field in proposal.resolved_fields
            if any(_matches(pattern, field.pointer) for pattern in block.rewrite.fields)})
    return ReviewInput(schemaVersion=2, protocol='template_import_v1', proposalHash=proposal.proposal_hash,
        targets=targets, handleMap=allocations, rules=rules, sourceSpans=[], sourceTexts={}, evidence=evidence,
        effectiveCells=effective_cells, relations=proposal.resolved_relations, packageHash=package.package_hash,
        allowTextRewrite=operation.capture.allow_text_rewrite, semanticContext=context, policy=policy,
        occurrenceContext=occurrence_context, occurrenceIndependent=occurrence_independent)


def check_review_reply(reply, expected, sources):
    """Coverage, rule and evidence checks of a resolved reply; shared by new replies and receipt reuse."""
    pairs = [(result.rule_id, result.target_id) for result in reply.results]
    wanted = [(target.rule_id, target.target_id) for target in expected.targets]
    if len(set(wanted)) != len(wanted) or len(set(pairs)) != len(pairs) or set(pairs) != set(wanted):
        raise TemplateImportFailure('IMPORT_REVIEW_INCOMPLETE')
    if not set(target.rule_id for target in expected.targets) <= {rule.id for rule in expected.rules}:
        raise TemplateImportFailure('IMPORT_REVIEW_TARGET_INVALID')
    for span, text in review_texts(expected):
        if text != source_slice(sources, span):
            raise TemplateImportFailure('IMPORT_REVIEW_EVIDENCE_CHANGED')
    for result in reply.results:
        for span in result.evidence:
            source_slice(sources, span)
    return reply


def validate_review_reply(value, expected, sources):
    """Raw-before-decode validation of a provider review; version 2 replies select checks and evidence by reference."""
    validate_payload(review_schema(expected), value)
    if expected.schema_version == 1:
        return check_review_reply(ReviewReply.model_validate(value, strict=True), expected, sources)
    referenced = ReferencedReviewReply.model_validate(value, strict=True)
    if review_protocol(expected) == REVIEW_PROTOCOL['version']:
        # Protocol 3 lists failing checks only; a check the reply does not list holds. Restored in check order, so a
        # receipt lists every check as protocol 2 did; a repeated or unknown check still makes the reply incomplete.
        entries = [result.model_dump(mode='json', by_alias=True) for result in referenced.results]
        listed = {entry['check'] for entry in entries}
        entries += [{'check': check, 'disposition': 'satisfied', 'reason': '', 'evidence': [], 'actionable': False}
            for check in check_references(expected) if check not in listed]
        order = {check: index for index, check in enumerate(check_references(expected))}
        referenced = ReferencedReviewReply.model_validate({'results': sorted(entries,
            key=lambda entry: order.get(entry['check'], len(order)))}, strict=True)
    checks, table = check_references(expected), {option.ref: option for option in expected.evidence}
    reply = ReviewReply.model_validate({'results': [{'ruleId': checks[result.check].rule_id,
        'targetId': checks[result.check].target_id, 'disposition': result.disposition, 'reason': result.reason,
        'evidence': [span.model_dump(mode='json', by_alias=True) for span in restore_evidence(result.evidence, table, sources)],
        'actionable': result.actionable} for result in referenced.results]}, strict=True)
    return check_review_reply(reply, expected, sources)


def reusable_receipt(operation, value, sources):
    checksum = digest(value)
    for receipt in operation.receipts:
        if receipt.review_input_hash == checksum and receipt.expected_checks == value.targets:
            check_review_reply(receipt.reply, value, sources)
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
