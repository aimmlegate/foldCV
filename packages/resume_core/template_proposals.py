"""Raw proposals resolve through captured identities before semantic review."""

from .models.template_facts import Observation, Relation
from .models.template_import import ProposalRecord, ProposalReply, ReferencedProposalReply, RelationAllocation, DroppedValue
from .project_store import strict_json
from .rich_fields import field_key
from .template_identity import (_bound_root, allocate_discoveries, offered_evidence, offered_references, payload_value,
    resolve_fields, resolve_lineage, restore_evidence, source_slice)
from .template_import import TemplateImportFailure, attempt_in, checked, digest, identity, task_in
from .templates.compiler import canonical, sha256
from .templates.projection import pointer_tokens, reachable_schema, validate_payload
from .templates.replies import proposal_schema, strip_unoffered_bookkeeping
from .template_capture import item_identities
from .template_completion import complete_reply

import json

from pydantic import ValidationError

# Schema rules whose expected value comes from the schema and can be named back to the model.
NAMED_RULES = {'type': 'expected type', 'enum': 'expected one of', 'const': 'expected', 'format': 'expected format',
    'pattern': 'expected pattern', 'minItems': 'expected at least items:', 'maxItems': 'expected at most items:',
    'minLength': 'expected at least characters:', 'maxLength': 'expected at most characters:',
    'minimum': 'expected at least', 'maximum': 'expected at most'}


def reply_error(error):
    """A refusal by path and broken rule; payload values, which may quote the source, are left out."""
    if isinstance(error, ValidationError):
        first = error.errors(include_url=False, include_input=False, include_context=False)[0]
        return '/' + '/'.join(map(str, first['loc'])) + ': ' + first['msg']
    rule = getattr(error, 'rule', None)
    if rule is None:
        return str(error)
    validator, expected = rule
    if validator == 'required':
        reason = error.reason
    elif validator in NAMED_RULES:
        reason = NAMED_RULES[validator] + ' ' + json.dumps(expected, ensure_ascii=False)[:200]
    elif validator in {'anyOf', 'oneOf'}:
        reason = 'matches none of the allowed shapes'
    elif validator == 'additionalProperties':
        reason = 'has a property the schema does not allow'
    else:
        reason = 'breaks the ' + str(validator) + ' rule'
    return error.path + ': ' + reason


def restore_reply(reply, table, references, sources):
    """Fill each selected reference with its captured identity or span; the result is the resolved reply form."""
    offered = {'item': {value.ref: value.item_handle for value in references.items},
        'cell': {value.ref: value.cell_id for value in references.cells},
        'relation': {value.ref: value.relation_id for value in references.relations}}
    def identity(kind, ref):
        if ref not in offered[kind]:
            raise ValueError(kind + ' reference was not offered')
        return offered[kind][ref]
    def item(selector):
        if selector.kind == 'discovery_key':
            return {'kind': 'discovery_key', 'key': selector.key}
        return {'kind': 'handle', 'itemHandle': identity('item', selector.ref)}
    def spans(refs):
        return [span.model_dump(mode='json', by_alias=True) for span in restore_evidence(refs, table, sources)]
    def key(field):
        # Completion fills both for every entry at a compiled binding; any other pointer stays unresolved.
        if field.field_key is None or field.item is None:
            raise ValueError('fields entry at ' + field.pointer + ' matches no compiled binding')
        return field.field_key
    return ProposalReply.model_validate({'schemaVersion': 1, 'payload': reply.payload,
        'discoveries': [value.model_dump(mode='json', by_alias=True) for value in reply.discoveries or []],
        'fields': [{'fieldKey': key(field), 'item': item(field.item), 'pointer': field.pointer, 'evidence': spans(field.evidence),
            'effectiveCellIds': [identity('cell', ref) for ref in field.effective_cells or []]} for field in reply.fields],
        'lineage': [{'kind': value.kind, 'parents': [identity('item', ref) for ref in value.parents], 'children': value.children}
            for value in reply.lineage or []],
        'relations': [{'relation': {'kind': 'discovery_key', 'key': relation.relation.key} if relation.relation.kind == 'new'
                else {'kind': 'relation_id', 'relationId': identity('relation', relation.relation.ref)},
            'kind': relation.kind, 'subject': item(relation.subject), 'target': item(relation.target),
            'evidence': spans(relation.evidence)} for relation in reply.relations or []]}, strict=True)


def relation_evidence(operation, proposal):
    if proposal.reply is None:
        return {}
    discovered = {value.key: value.relation_id for value in operation.relation_allocations
        if value.discovery_attempt_id == proposal.attempt_id}
    return {(value.relation.relation_id if value.relation.kind == 'relation_id' else discovered[value.relation.key]):
        value.evidence for value in proposal.reply.relations}


def resolve_relations(reply, operation, task, attempt, allocations, declarations, sources, *, captured_relations,
                      id_factory=identity, bindings=()):
    by_local = {allocation.key: allocation for allocation in allocations}
    allowed = set(task.allowed_handles) | {allocation.item_handle for allocation in allocations}
    by_handle = {allocation.item_handle: allocation for allocation in item_identities(operation) if allocation.item_handle in allowed}
    by_handle.update({allocation.item_handle: allocation for allocation in allocations})
    durable = {(value.operation_id, value.task_id, value.discovery_attempt_id, value.key): value
        for value in operation.relation_allocations}
    existing = {relation.id: relation for relation in captured_relations}
    seen, selected, subjects, resolved, allocated = set(), set(), set(), [], []
    def select(selector):
        value = by_local.get(selector.key) if selector.kind == 'discovery_key' else by_handle.get(selector.item_handle)
        if value is None:
            raise ValueError('relation selector is outside captured task handles')
        return value
    def selector_key(selector):
        return (selector.kind, selector.key if selector.kind == 'discovery_key' else selector.item_handle)
    roots = {('discovery_key', discovery.key): pointer_tokens(discovery.pointer) for discovery in reply.discoveries}
    required_roots = {}
    for field in reply.fields:
        allocation = select(field.item)
        if not bindings:
            continue
        root = _bound_root(field.pointer, allocation.semantic_type, field.field_key, bindings)
        key = selector_key(field.item)
        if key in roots and roots[key] != root:
            raise ValueError('relation item root differs from its field roots')
        roots[key] = root
        actual = pointer_tokens(field.pointer)
        for binding in bindings:
            pattern = pointer_tokens(binding.pointer)
            if (binding.semantic_type != allocation.semantic_type or binding.field != field.field_key
                    or binding.relation is None or binding.item_pointer is None or len(pattern) != len(actual)
                    or any(expected != '*' and expected != value for expected, value in zip(pattern, actual, strict=True))):
                continue
            target = pointer_tokens(binding.relation.subject_pointer)
            resolved_root = []
            for index, token in enumerate(target):
                if token == '*':
                    if index >= len(pattern) or pattern[index] != '*':
                        raise ValueError('relation root wildcard is not captured by the subject field')
                    token = actual[index]
                resolved_root.append(token)
            required_roots.setdefault((key, binding.relation.kind), set()).add(tuple(resolved_root))
    for proposed in reply.relations:
        selection = (proposed.relation.kind, proposed.relation.key if proposed.relation.kind == 'discovery_key'
            else proposed.relation.relation_id)
        if selection in selected:
            raise ValueError('duplicate relationship selector')
        selected.add(selection)
        subject, target = select(proposed.subject), select(proposed.target)
        constraints = required_roots.get((selector_key(proposed.subject), proposed.kind), set())
        if constraints and (len(constraints) != 1 or tuple(roots.get(selector_key(proposed.target), [])) not in constraints):
            raise ValueError('proposed relation target differs from its configured subject root')
        declaration = declarations[subject.semantic_type]
        if not any(relation.kind == proposed.kind and target.semantic_type in relation.target_types for relation in declaration.relations):
            raise ValueError('undeclared or incompatible proposed relationship')
        if proposed.subject == proposed.target:
            raise ValueError('self relationship is unsupported')
        previous = None
        if proposed.relation.kind == 'relation_id':
            previous = existing.get(proposed.relation.relation_id)
            if previous is None or previous.subject_id != subject.record_id or previous.kind != proposed.kind:
                raise ValueError('relation repair changes uncaptured identity')
            identifier = previous.id
        else:
            key = (operation.id, task.id, attempt.id, proposed.relation.key)
            allocation = durable.get(key)
            if allocation is None:
                allocation = RelationAllocation(operationId=operation.id, taskId=task.id, discoveryAttemptId=attempt.id,
                    key=proposed.relation.key, relationId=id_factory('relation'), kind=proposed.kind,
                    subjectId=subject.record_id, targetId=target.record_id)
                if allocation.relation_id in existing or any(value.relation_id == allocation.relation_id
                        for value in [*operation.relation_allocations, *allocated]):
                    raise ValueError('allocated relationship identity collides')
            elif (allocation.kind, allocation.subject_id, allocation.target_id) != (proposed.kind, subject.record_id, target.record_id):
                raise ValueError('relation discovery key was rebound')
            allocated.append(allocation)
            identifier = allocation.relation_id
        if identifier in seen or proposed.kind in {'owned_by', 'extension_of'} and (subject.record_id, proposed.kind) in subjects:
            raise ValueError('duplicate proposed relationship')
        seen.add(identifier)
        subjects.add((subject.record_id, proposed.kind))
        if not proposed.evidence and (previous is None or previous.target_id != target.record_id):
            raise ValueError('proposed ownership needs source evidence')
        for span in proposed.evidence:
            source_slice(sources, span)
        resolved.append(Relation(id=identifier, kind=proposed.kind, subjectId=subject.record_id,
            targetId=target.record_id, revision=previous.revision if previous else 1, active=True))
    for (key, kind), _roots in required_roots.items():
        subject = by_local.get(key[1]) if key[0] == 'discovery_key' else by_handle.get(key[1])
        if not any(relation.subject_id == subject.record_id and relation.kind == kind for relation in resolved):
            raise ValueError('configured item relationship is missing')
    return resolved, allocated


def transport_refusal(attempt, package, block_id):
    """Why the transport refused a returned reply, by path and rule; None when there is no reply to check."""
    if attempt.raw_return is None:
        return None
    compiled = next(block for block in package.blocks if block.id == block_id)
    try:
        outer = strict_json(attempt.raw_return)
        if not isinstance(outer, dict) or set(outer) != {'payload'}:
            return 'the reply needs its exact payload envelope'
        table = offered_evidence(attempt.request_value)
        references = offered_references(attempt.request_value) if table is not None else None
        outer['payload'] = strip_unoffered_bookkeeping(outer['payload'], references)
        validate_payload(proposal_schema(compiled.full_schema, None if table is None else list(table), references), outer['payload'])
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        return reply_error(error)
    return None


def parse_proposal(operation, attempt_id, package, sources, facts, *, captured_relations=(), id_factory=identity):
    result, working = operation.model_copy(deep=True), facts.model_copy(deep=True)
    attempt = attempt_in(result, attempt_id)
    task = task_in(result, attempt.task_id)
    if attempt.proposal_record_id is not None:
        prior = next((proposal for proposal in result.proposals if proposal.id == attempt.proposal_record_id), None)
        if prior is None or prior.input_hash != attempt.input_hash or prior.raw_return_hash != attempt.raw_return_hash:
            raise TemplateImportFailure('IMPORT_PROPOSAL_RECORD_INVALID')
        return result, working, prior
    if (attempt.slot not in {'initial', 'primary_repair', 'fallback_repair'} or attempt.state != 'returned'
            or attempt.outcome != 'completed' or attempt.cleanup.state != 'verified' or attempt.raw_return is None
            or sha256(attempt.raw_return.encode()) != attempt.raw_return_hash):
        raise TemplateImportFailure('IMPORT_PROPOSAL_ATTEMPT_INVALID')
    compiled = next(block for block in package.blocks if block.id == task.block_id)
    block = next(block for block in package.definition.blocks if block.id == task.block_id)
    proposal = ProposalRecord(id=id_factory('proposal'), attemptId=attempt.id, inputHash=attempt.input_hash,
        rawReturn=attempt.raw_return, rawReturnHash=attempt.raw_return_hash, reply=None, resolvedFields=[], lineage=[],
        state='invalid', errors=[], proposalHash=digest({'rawReturnHash': attempt.raw_return_hash, 'inputHash': attempt.input_hash}))
    try:
        outer = strict_json(attempt.raw_return)
        if not isinstance(outer, dict) or set(outer) != {'payload'}:
            raise ValueError('proposal needs its exact payload envelope')
        # The raw reply is checked against the schema of its own captured request before decoding.
        table = offered_evidence(attempt.request_value)
        references = offered_references(attempt.request_value) if table is not None else None
        outer['payload'] = strip_unoffered_bookkeeping(outer['payload'], references)
        validate_payload(proposal_schema(compiled.full_schema, None if table is None else list(table), references), outer['payload'])
        if table is None:
            reply = ProposalReply.model_validate(outer['payload'], strict=True)
        else:
            # Protocol 5: bookkeeping the payload implies is derived before the reply is restored.
            allowed = {(declaration.id, relation.kind, target) for declaration in package.definition.fact_types
                for relation in declaration.relations for target in relation.target_types}
            # A repair that still states a value no source line states loses that value and keeps the block (I4).
            dropped = [] if attempt.slot in {'primary_repair', 'fallback_repair'} else None
            # One entry of a block (D117) cites its own lines first.
            lines = {digest(span) for span in task.entry.spans} if task.entry is not None else set()
            preferred = {ref: option for ref, option in table.items() if digest(option.span) in lines} or None
            completed = complete_reply(outer['payload'], block.bindings, table, references, allowed, dropped=dropped,
                preferred=preferred, previous=attempt.request_value.get('previousReply'))
            proposal.dropped_values = [DroppedValue.model_validate(value) for value in dropped or []]
            reply = restore_reply(ReferencedProposalReply.model_validate(completed, strict=True), table, references, sources)
        declarations = {declaration.id: declaration for declaration in package.definition.fact_types}
        schemas = {key: reachable_schema(declaration.data_schema, package.definition.content_definitions)
            for key, declaration in declarations.items()}
        def cell_id(semantic_type, record_id, key):
            return field_key(record_id, key) if declarations[semantic_type].builtin_kind is not None else id_factory('cell')
        allocations = allocate_discoveries(reply, operation_id=result.id, task_id=task.id, attempt_id=attempt.id,
            existing=result.allocations, type_schemas=schemas, bindings=block.bindings, id_factory=id_factory, cell_id_factory=cell_id,
            type_declarations=declarations, reserved=result.captured_items)
        handle_types = {allocation.item_handle: allocation.semantic_type for allocation in item_identities(result)}
        frozen = next((value.value for value in result.task_inputs if value.task_id == task.id), {})
        effective_cells = [value['id'] for value in frozen.get('effectiveCells', [])]
        fields = resolve_fields(reply, allocations, allowed_handles=task.allowed_handles, sources=sources,
            effective_cells=effective_cells, type_schemas=schemas, handle_types=handle_types, bindings=block.bindings)
        lineage = resolve_lineage(reply, allocations, allowed_parents=task.allowed_handles, attempt_id=attempt.id)
        relations, relation_allocations = resolve_relations(reply, result, task, attempt, allocations, declarations,
            sources, captured_relations=captured_relations, id_factory=id_factory, bindings=block.bindings)
        all_allocations = {allocation.item_handle: allocation for allocation in [*item_identities(result), *allocations]}
        proposal.reply, proposal.resolved_fields, proposal.lineage = reply, fields, lineage
        proposal.resolved_relations = relations
        proposal.proposal_hash = digest({'reply': reply, 'fields': fields, 'lineage': lineage, 'relations': relations})
        proposal.state = 'provisional'
        result.allocations += [allocation for allocation in allocations if allocation not in result.allocations]
        result.relation_allocations += [allocation for allocation in relation_allocations if allocation not in result.relation_allocations]
        for field in fields:
            raw = payload_value(reply.payload, field.pointer)
            record_id = all_allocations[field.item_handle].record_id
            working.observations.append(Observation(id=id_factory('observation'), itemHandle=field.item_handle,
                fieldKey=field.field_key, rawInput=raw if isinstance(raw, str) else canonical(raw).decode(), typedValue=raw,
                evidence=field.evidence, ownerRelations=[relation for relation in relations if relation.subject_id == record_id],
                proposalHash=proposal.proposal_hash, admission='provisional', receiptIds=[]))
        task.allowed_handles = list(dict.fromkeys([*task.allowed_handles, *[allocation.item_handle for allocation in allocations]]))
        task.proposal_hash, task.state = proposal.proposal_hash, 'proposed'
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        proposal.errors = [reply_error(error)]
        attempt.outcome = 'invalid_payload'
        attempt.error_code = attempt.error_code or 'IMPORT_PROPOSAL_INVALID'
    result.proposals.append(proposal)
    attempt.proposal_record_id, attempt.state = proposal.id, 'reconciled'
    return checked(result), type(facts).model_validate(working.model_dump(by_alias=True)), proposal
