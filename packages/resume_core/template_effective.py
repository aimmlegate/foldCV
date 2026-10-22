"""Project current builtin authority into shared cells without duplicating storage."""

from .models.template_facts import ExtensionCell
from .rich_fields import builtin_cell_values
from .template_builtin_admission import admitted_field
from .template_import import digest
from .template_identity import payload_value
from .template_review import decide_review
from .template_capture import item_identities
from .template_wording import display_raw_input


def _receipt_cells(facts, operations):
    observations = {(value.proposal_hash, value.item_handle, value.field_key): value
        for value in facts.observations if value.admission == 'accepted'}
    result = {}
    for operation in operations:
        allocations = {value.item_handle: value for value in item_identities(operation)}
        receipts = {value.id: value for value in operation.receipts}
        inputs = {value.attempt_id: value for value in operation.review_inputs}
        for proposal in operation.proposals:
            receipt = receipts.get(proposal.applied_receipt_id)
            review = inputs.get(receipt.attempt_id) if receipt else None
            if (proposal.state != 'accepted' or receipt is None or review is None
                    or review.input_hash != receipt.review_input_hash or digest(review.value) != review.input_hash
                    or review.value.proposal_hash != proposal.proposal_hash):
                continue
            allowed = set(decide_review(review.value, receipt, proposal).admitted_cell_ids)
            captured = {value.item_handle: value for value in review.value.handle_map}
            for field in proposal.resolved_fields:
                allocation = allocations.get(field.item_handle)
                destination = allocation.canonical_fields.get(field.field_key) if allocation else None
                observation = observations.get((proposal.proposal_hash, field.item_handle, field.field_key))
                if (destination is None or destination.cell_id not in proposal.admitted_cell_ids or observation is None
                        or receipt.id not in observation.receipt_ids or destination.cell_id not in allowed
                        or captured.get(field.item_handle) != allocation or proposal.reply is None
                        or observation.typed_value != payload_value(proposal.reply.payload, field.pointer)
                        or observation.evidence != field.evidence):
                    continue
                projected = admitted_field(observation.typed_value, destination)
                if isinstance(observation.typed_value, str):
                    projected['rawText'] = display_raw_input(review.value, field, observation.typed_value)
                result.setdefault(destination.cell_id, []).append((projected, observation, receipt.id))
    return result


def builtin_effective_cells(facts, operations, record_ids=None, *, include_raw=False):
    selected = set(record_ids) if record_ids is not None else None
    receipts = _receipt_cells(facts, operations)
    result = []
    for identifier, (record, key, value) in builtin_cell_values(facts.records).items():
        if selected is not None and record.id not in selected:
            continue
        human = record.origin == 'user' or value.user_corrected
        scope_id = facts.builtin_manual_scopes.get(identifier)
        typed = value.model_dump(mode='json', by_alias=True)['value']
        if human:
            pending = value.status == 'pending'
            result.append(ExtensionCell(id=identifier, fieldKey=key, revision=value.revision,
                rawInput='' if scope_id else value.pending_raw_text if pending else value.raw_text,
                typedValue=typed if value.status == 'known' else None,
                state='pending_manual' if scope_id else 'admitted' if value.status == 'known' else 'human_raw',
                origin='human', userCorrected=True, evidence=[], observationIds=[], admissionReceiptIds=[],
                manualScopeId=scope_id))
            continue
        matches = [(observation, receipt) for projected, observation, receipt in receipts.get(identifier, [])
            if (projected['value'], projected['rawText'], projected['status']) == (typed, value.raw_text, value.status)]
        if not matches or value.status != 'known' and not (include_raw and value.status == 'unresolved' and value.raw_text):
            continue
        observation, receipt = matches[-1]
        result.append(ExtensionCell(id=identifier, fieldKey=key, revision=value.revision, rawInput=value.raw_text,
            typedValue=typed, state='admitted' if value.status == 'known' else 'uncertain', origin='source', userCorrected=False,
            evidence=observation.evidence, observationIds=[observation.id], admissionReceiptIds=[receipt], manualScopeId=None))
    return result


def effective_cells(facts, operations, record_ids=None):
    selected = set(record_ids) if record_ids is not None else None
    return [cell.model_copy(deep=True) for record in facts.extensions if record.active
        and (selected is None or record.id in selected) for cell in record.cells
        if cell.state in {'admitted', 'human_raw', 'pending_manual'}] + builtin_effective_cells(facts, operations, selected)
