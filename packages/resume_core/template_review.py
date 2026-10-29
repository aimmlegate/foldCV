"""Complete review receipts bind every semantic input before effective admission."""

from dataclasses import dataclass
import json
import re

from .models.template_import import (CheckTarget, ReferencedReviewReply, ReviewDisposition, ReviewInput, ReviewReceipt,
    ReviewReply, SettledCheck)
from .project_store import strict_json
from .template_identity import capture_span, empty_value, evidence_options, offered_evidence, payload_value, restore_evidence, source_slice
from .template_import import TemplateImportFailure, attempt_in, checked, digest, identity, task_in
from .templates.models import Check
from .templates.compiler import canonical, sha256
from .templates.projection import SchemaFailure, pointer_tokens, resolve, schema_at, validate_payload
from .templates.replies import FAILING_ONLY_PROTOCOLS, REVIEW_PROTOCOL, check_references, review_protocol, review_schema
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


def _verbatim(text, texts):
    pattern = re.compile(r'(?<!\w)' + re.escape(text) + r'(?!\w)')
    return any(pattern.search(value) for value in texts)


def _categorical(schema, pointer):
    """Whether the content schema at a payload pointer chooses from listed values (enum or const). Such a value is a
    category the model judges (D115): «not published» states the word published, not the category."""
    try:
        node = schema_at(schema, pointer)
    except SchemaFailure:
        return True
    def chooses(value, depth=0):
        if not isinstance(value, dict) or depth > 16:
            return False
        if 'enum' in value or 'const' in value:
            return True
        if '$ref' in value:
            try:
                return chooses(resolve(schema, value['$ref']), depth + 1)
            except SchemaFailure:
                return True
        return any(chooses(branch, depth + 1) for key in ('anyOf', 'oneOf', 'allOf') for branch in value.get(key) or [])
    return chooses(node)


def _within(span, scope):
    return any(other.source_id == span.source_id and other.unit_id == span.unit_id and other.start <= span.start
        and span.end <= other.end for other in scope)


def settled_checks(proposal, targets, allocations, sources, *, rewrite_fields, previous=None, scope=None, content_schema=None):
    """The checks the coordinator settles without the model (D115). A string value outside the rewritten fields that
    stands word for word in a cited source line satisfies every check on its cell: the coordinator bound it there.
    In a replacement review a value or relation the repair left as it was, same value and same evidence, keeps the
    earlier receipt's result for each of its checks, a finding included. The scope check is never settled.
    scope, for one entry of a block (D117), is the entry's lines: a value cited outside them stays with the model.
    content_schema is the block's: a value it lets choose from listed values (enum, const) stays with the model."""
    cells = {allocation.item_handle: allocation.cell_ids for allocation in allocations}
    settled = {}
    def settle(target, disposition, reason, evidence, actionable, origin):
        settled[(target.rule_id, target.target_id)] = SettledCheck(ruleId=target.rule_id, targetId=target.target_id,
            disposition=disposition, reason=reason, evidence=list(evidence), actionable=actionable, origin=origin)
    for field in proposal.resolved_fields:
        value = payload_value(proposal.reply.payload, field.pointer)
        if (not isinstance(value, str) or not value.strip() or field.item_handle not in cells
                or any(_matches(pattern, field.pointer) for pattern in rewrite_fields)
                or content_schema is not None and _categorical(content_schema, field.pointer)):
            continue
        if not _verbatim(value.strip(), [source_slice(sources, span) for span in field.evidence]):
            continue
        if scope is not None and not all(_within(span, scope) for span in field.evidence):
            continue
        cell = cells[field.item_handle][field.field_key]
        for target in targets:
            if target.target_id == cell:
                # Like an unlisted check of the model: satisfied, no reason, no cited refs (the field has its own).
                settle(target, 'satisfied', '', [], False, 'verbatim')
    if previous is not None:
        earlier, receipt = previous
        results = {(result.rule_id, result.target_id): result for result in receipt.reply.results}
        def fields_of(value):
            return {(field.item_handle, field.field_key): (canonical(payload_value(value.reply.payload, field.pointer)),
                frozenset(digest(span) for span in field.evidence)) for field in value.resolved_fields}
        def relations_of(value):
            return {resolved.id: (resolved.kind, resolved.subject_id, resolved.target_id,
                frozenset(digest(span) for span in proposed.evidence))
                for resolved, proposed in zip(value.resolved_relations, value.reply.relations, strict=True)}
        before, before_relations = fields_of(earlier), relations_of(earlier)
        unchanged = {cells[handle][key] for (handle, key), same in fields_of(proposal).items()
            if handle in cells and before.get((handle, key)) == same}
        unchanged |= {identifier for identifier, same in relations_of(proposal).items() if before_relations.get(identifier) == same}
        for target in targets:
            result = results.get((target.rule_id, target.target_id))
            if target.target_id in unchanged and result is not None and (target.rule_id, target.target_id) not in settled:
                settle(target, result.disposition, result.reason, result.evidence, result.actionable, 'reused')
    return [settled[(target.rule_id, target.target_id)] for target in targets if (target.rule_id, target.target_id) in settled]


def make_review_input(operation, proposal, package, sources, policy, *, effective_cells, semantic_context,
                      occurrence_context=None, occurrence_independent=True, previous=None):
    """The review of a proposal. previous, for a replacement review, is the reviewed proposal the repair corrects with
    its receipt: the checks of what the repair left unchanged reuse that receipt (D115). The proposal of one entry of
    a block (D117) settles verbatim values only within the entry's lines."""
    if proposal.state != 'provisional' or proposal.reply is None:
        raise TemplateImportFailure('IMPORT_PROPOSAL_NOT_REVIEWABLE')
    attempt = attempt_in(operation, proposal.attempt_id)
    task = task_in(operation, attempt.task_id)
    block = next(block for block in package.definition.blocks if block.id == task.block_id)
    rules = required_rules(block)
    handles = set(task.allowed_handles) | {field.item_handle for field in proposal.resolved_fields}
    allocations = [allocation for allocation in item_identities(operation) if allocation.item_handle in handles]
    targets = expected_checks(task, proposal, allocations, rules)
    settled = settled_checks(proposal, targets, allocations, sources, previous=previous,
        rewrite_fields=block.rewrite.fields if operation.capture.allow_text_rewrite else [],
        scope=task.entry.spans if task.entry is not None else None,
        content_schema=next(value.full_schema for value in package.blocks if value.id == block.id))
    asked = {(value.rule_id, value.target_id) for value in settled}
    asked = [target for target in targets if (target.rule_id, target.target_id) not in asked]
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
        'checks': grouped_checks(review_checks(task, proposal, allocations, asked, refs))}
    if not operation.capture.allow_text_rewrite:
        context['sourceWordingPointers'] = sorted({field.pointer for field in proposal.resolved_fields
            if any(_matches(pattern, field.pointer) for pattern in block.rewrite.fields)})
    return ReviewInput(schemaVersion=2, protocol='template_import_v1', proposalHash=proposal.proposal_hash,
        targets=targets, handleMap=allocations, rules=rules, sourceSpans=[], sourceTexts={}, evidence=evidence,
        effectiveCells=effective_cells, relations=proposal.resolved_relations, packageHash=package.package_hash,
        allowTextRewrite=operation.capture.allow_text_rewrite, semanticContext=context, policy=policy,
        occurrenceContext=occurrence_context, occurrenceIndependent=occurrence_independent, settled=settled)


def with_settled(reply, expected):
    """The reply with the checks the coordinator settled, in the order of the expected targets; an entry the targets
    do not name stays, so the completeness check still refuses it."""
    if not expected.settled:
        return reply
    entries = {(result.rule_id, result.target_id): result for result in reply.results}
    entries.update({(value.rule_id, value.target_id): ReviewDisposition(ruleId=value.rule_id, targetId=value.target_id,
        disposition=value.disposition, reason=value.reason, evidence=value.evidence, actionable=value.actionable)
        for value in expected.settled})
    wanted = [(target.rule_id, target.target_id) for target in expected.targets]
    return ReviewReply(results=[entries[pair] for pair in wanted if pair in entries]
        + [result for pair, result in entries.items() if pair not in set(wanted)])


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
        return check_review_reply(with_settled(ReviewReply.model_validate(value, strict=True), expected), expected, sources)
    referenced = ReferencedReviewReply.model_validate(value, strict=True)
    if review_protocol(expected) in FAILING_ONLY_PROTOCOLS:
        # Protocol 3 lists failing checks only; a check the reply does not list holds. Restored in check order, so a
        # receipt lists every check as protocol 2 did. A check listed twice (LIVE-11/12 summary: a violation and an
        # uncertain entry for the same target) merges into the worse disposition; an unknown check is refused by the
        # schema's enum.
        merged = {}
        for result in referenced.results:
            entry = result.model_dump(mode='json', by_alias=True)
            merged[entry['check']] = merge_dispositions(merged[entry['check']], entry) if entry['check'] in merged else entry
        entries = list(merged.values())
        listed = set(merged)
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
    return check_review_reply(with_settled(reply, expected), expected, sources)


SEVERITY = {'satisfied': 0, 'uncertain': 1, 'violation': 2}


def merge_dispositions(first, second):
    """One entry for a check the reply listed twice: the worse disposition, every reason and every cited ref."""
    worse = second if SEVERITY[second['disposition']] > SEVERITY[first['disposition']] else first
    reasons = [reason for reason in (first['reason'], second['reason']) if reason]
    return {'check': first['check'], 'disposition': worse['disposition'], 'reason': ' '.join(dict.fromkeys(reasons)),
        'evidence': list(dict.fromkeys([*first['evidence'], *second['evidence']])),
        'actionable': first['actionable'] or second['actionable']}


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
    # A repair reads the reviewed reply as previousReply; a field finding names its place there.
    pointers = {cells[field.item_handle][field.field_key]: field.pointer for field in proposal.resolved_fields}
    feedback = tuple({'ruleId': result.rule_id, 'targetId': result.target_id, 'reason': result.reason,
            **({'pointer': pointers[result.target_id]} if result.target_id in pointers else {})}
        for result in results if result.disposition == 'violation' or result.disposition == 'uncertain'
            and result.actionable and result.reason.strip())
    return ReviewDecision(tuple(admitted), tuple(sorted(admitted_relations)), feedback, tuple(sorted(failed)))


@dataclass(frozen=True)
class ShownValue:
    item_handle: str
    semantic_type: str
    field_key: str
    text: str
    units: frozenset
    reworded: bool


def _text_key(value):
    # Spelling only: "Node.js" and "NodeJS" are one value, "Kafka 4.0.x" and "Kafka" are not.
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return ''.join(character for character in text.casefold() if character.isalnum())


def shown_values(proposal, cell_ids, allocations, rewrite_fields):
    """The non-empty values a proposal admits, comparable with another reply of the same block."""
    by_handle = {allocation.item_handle: allocation for allocation in allocations}
    values = []
    for field in proposal.resolved_fields:
        allocation = by_handle[field.item_handle]
        value = payload_value(proposal.reply.payload, field.pointer)
        if allocation.cell_ids[field.field_key] not in cell_ids or empty_value(value):
            continue
        values.append(ShownValue(field.item_handle, allocation.semantic_type, field.field_key, _text_key(value),
            frozenset((span.source_id, span.unit_id) for span in field.evidence),
            any(_matches(pattern, field.pointer) for pattern in rewrite_fields)))
    return values


def _same_value(left, right):
    # A reworded value is the same claim when both cite a common source line.
    return (left.semantic_type, left.field_key) == (right.semantic_type, right.field_key) and (left.text == right.text
        or left.reworded and right.reworded and bool(left.units & right.units))


def repair_wins(first, first_failed, repair, repair_failed):
    """Whether a repair replaces the admitted reply: what shows after it (repair) keeps every admitted value, it adds
    no failing value, and it fixes a finding or adds a value. LIVE-09: a repair failed 142 checks where the first
    reply failed 7. D107: a repair that added ZeroMQ tied on one coverage finding and was dropped; one that fixed a
    claim wrote over another."""
    if any(not any(_same_value(value, other) for other in repair) for value in first):
        return False
    def values(failed):
        return {target for target in failed if not target.startswith('scope-')}
    if len(values(repair_failed)) > len(values(first_failed)):
        return False
    return len(set(repair_failed)) < len(set(first_failed)) or any(
        not any(_same_value(value, other) for other in first) for value in repair)
