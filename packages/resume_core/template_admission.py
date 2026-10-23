"""Only complete coordinator receipts can promote a model's effective cells."""

from .models.template_facts import ExtensionCell, ExtensionRecord
from .template_identity import empty_value, payload_value
from .template_import import TemplateImportFailure, authorization, checked, digest, instant, task_in
from .template_replacements import apply_accepted_records
from .template_builtin_admission import apply_builtin_records, current_handles, human_authority, make_builtin_candidate
from .template_mutations import _set_builtin_owner
from .template_review import check_review_reply, decide_review
from .templates.compiler import canonical, sha256
from .templates.projection import reachable_schema
from .template_capture import item_identities, retain_builtin_identity
from .template_wording import display_raw_input


def admit_proposal(operation, proposal_id, receipt_id, package, sources, facts, *, expected_revisions,
                   expected_relation_revisions):
    result, working = operation.model_copy(deep=True), facts.model_copy(deep=True)
    proposal = next((value for value in result.proposals if value.id == proposal_id), None)
    receipt = next((value for value in result.receipts if value.id == receipt_id), None)
    review = next((value for value in result.review_inputs if receipt is not None and value.attempt_id == receipt.attempt_id), None)
    if (proposal is None or receipt is None or review is None or review.value.proposal_hash != proposal.proposal_hash
            or review.input_hash != digest(review.value) or receipt.review_input_hash != review.input_hash):
        raise TemplateImportFailure('IMPORT_ADMISSION_RECEIPT_INVALID')
    check_review_reply(receipt.reply, review.value, sources)
    if proposal.applied_receipt_id is not None:
        if proposal.applied_receipt_id != receipt_id:
            raise TemplateImportFailure('IMPORT_ADMISSION_ALREADY_APPLIED')
        return result, working
    authorization(result)
    if review.value.semantic_context.get('effectiveFactsHash', digest(facts)) != digest(facts):
        raise TemplateImportFailure('IMPORT_ADMISSION_FACTS_STALE')
    if package.package_hash != operation.capture.package_hash or review.value.package_hash != package.package_hash or (
            {source.id: source.byte_sha256 for source in sources} != operation.capture.source_hashes):
        raise TemplateImportFailure('IMPORT_CAPTURE_STALE')
    for identifier in [proposal.attempt_id, receipt.attempt_id]:
        attempt = next(value for value in operation.attempts if value.id == identifier)
        original_authority = next((value for value in operation.authorizations if value.id == attempt.authorization_id), None)
        if (original_authority is None or original_authority.state != 'active' or attempt.returned_at is None
                or attempt.dispatched_at is None or instant(attempt.returned_at) < instant(attempt.dispatched_at)
                or operation.expires_at is None or instant(attempt.returned_at) >= instant(operation.expires_at)):
            raise TemplateImportFailure('IMPORT_ADMISSION_ATTEMPT_EXPIRED')
    decision = decide_review(review.value, receipt, proposal)
    admitted_cells, admitted_relations = set(decision.admitted_cell_ids), set(decision.admitted_relation_ids)
    identities = item_identities(result)
    allocations = {value.item_handle: value for value in identities}
    declarations = {value.id: value for value in package.definition.fact_types}
    current = current_handles(result, working)
    human_subjects = {record.id for record in current.values() if human_authority(record)}
    admitted_relations.difference_update(relation.id for relation in proposal.resolved_relations if relation.subject_id in human_subjects)
    candidate_relations = {relation.id: relation for relation in working.relations}
    candidate_relations.update({relation.id: relation for relation in proposal.resolved_relations if relation.id in admitted_relations})
    observed = {(value.item_handle, value.field_key): value for value in working.observations
        if value.proposal_hash == proposal.proposal_hash}
    for field in proposal.resolved_fields:
        observation = observed[(field.item_handle, field.field_key)]
        cell_id = allocations[field.item_handle].cell_ids[field.field_key]
        observation.admission = 'accepted' if cell_id in admitted_cells else 'rejected' if any(
            value.target_id == cell_id and value.disposition == 'violation' for value in receipt.reply.results) else 'uncertain'
        observation.receipt_ids = [*observation.receipt_ids, receipt_id]
    records, builtins, builtin_cells, complete_handles, accepted_handles = [], {}, {}, set(), set()
    raw_texts = {allocations[field.item_handle].cell_ids[field.field_key]: display_raw_input(review.value, field,
        payload_value(proposal.reply.payload, field.pointer)) for field in proposal.resolved_fields
        if allocations[field.item_handle].cell_ids[field.field_key] in admitted_cells}
    for handle in dict.fromkeys(field.item_handle for field in proposal.resolved_fields):
        allocation = allocations[handle]
        declaration = declarations[allocation.semantic_type]
        fields = [field for field in proposal.resolved_fields if field.item_handle == handle]
        if declaration.builtin_kind is not None:
            record, applied = make_builtin_candidate(result, allocation, declaration, fields, proposal.reply.payload,
                admitted_cells, sources, working, declarations, list(candidate_relations.values()), raw_texts=raw_texts)
            if record is not None:
                builtins[handle], builtin_cells[handle] = record, applied
            if applied:
                accepted_handles.add(handle)
                if all(empty_value(payload_value(proposal.reply.payload, field.pointer)) or
                        allocation.cell_ids[field.field_key] in admitted_cells for field in fields):
                    complete_handles.add(handle)
            continue
        previous = current.get(handle)
        cells, full = [], True
        for field in fields:
            raw = payload_value(proposal.reply.payload, field.pointer)
            identifier = allocation.cell_ids[field.field_key]
            if empty_value(raw):
                continue
            if identifier not in admitted_cells:
                full = False
                continue
            observation = observed[(handle, field.field_key)]
            cells.append(ExtensionCell(id=identifier, fieldKey=field.field_key, revision=1,
                rawInput=raw_texts[identifier], typedValue=raw, state='admitted',
                origin='model', userCorrected=False, evidence=field.evidence, observationIds=[observation.id],
                admissionReceiptIds=[receipt_id], manualScopeId=None))
        records.append(ExtensionRecord(schemaVersion=1, id=allocation.record_id, itemHandle=handle, revision=1,
            semanticType=allocation.semantic_type,
            semanticSchemaHash=sha256(canonical(reachable_schema(declaration.data_schema, package.definition.content_definitions))),
            cells=cells, relations=previous.relations if previous else [],
            observationIds=[value.id for value in observed.values() if value.item_handle == handle], active=True,
            copyOfRecordId=previous.copy_of_record_id if previous else None))
        if cells:
            accepted_handles.add(handle)
        if cells and full:
            complete_handles.add(handle)
    lineage = list(proposal.lineage)
    supplied = {record.item_handle for record in records} | builtins.keys()
    covered = {handle for link in lineage for handle in link.children}
    blocked = set()
    for handle in supplied - current.keys() - covered:
        origin = next((link for retained in result.proposals for link in retained.lineage if handle in link.children), None)
        if origin is None:
            raise TemplateImportFailure('IMPORT_ADMISSION_LINEAGE_MISSING')
        if origin.kind == 'add':
            lineage.append(origin.model_copy(update={'children': [handle]}, deep=True))
        elif not set(origin.children) <= supplied:
            blocked.update(set(origin.children) & supplied)
            continue
        elif origin not in lineage:
            lineage.append(origin)
    protected_parents = set()
    for link in lineage:
        human_parents = {handle for handle in link.parents if handle in current and human_authority(current[handle])}
        protected_parents.update(human_parents)
        if link.kind in {'split', 'merge'} and (not set(link.children) <= complete_handles or any(
                value.target_id.startswith('scope-') and value.disposition != 'satisfied' for value in receipt.reply.results)
                or human_parents):
            accepted_handles.difference_update(link.children)
    protected_ids = {current[handle].id for handle in protected_parents}
    admitted_relations.difference_update(relation.id for relation in proposal.resolved_relations if relation.subject_id in protected_ids)
    accepted_handles.difference_update(blocked)
    records = [record for record in records if record.item_handle not in blocked]
    builtins = {handle: record for handle, record in builtins.items() if handle not in blocked}
    incoming = {**builtins, **{record.item_handle: record for record in records}}
    while True:
        before = set(accepted_handles)
        for link in lineage:
            if link.kind != 'add' and not set(link.children) <= accepted_handles:
                accepted_handles.difference_update(link.children)
        retiring = {current[parent].id for link in lineage if link.kind != 'add'
            and set(link.children) <= accepted_handles for parent in link.parents if parent in current}
        available = ({record.id for record in working.records} | {record.id for record in working.extensions if record.active}) - retiring
        available.update(record.id for handle, record in incoming.items() if handle in accepted_handles)
        for relation in proposal.resolved_relations:
            if relation.kind in {'owned_by', 'extension_of'} and (relation.id not in admitted_relations or relation.target_id not in available):
                accepted_handles.difference_update(handle for handle, record in incoming.items() if record.id == relation.subject_id)
        if before == accepted_handles:
            break
    for field in proposal.resolved_fields:
        withheld = field.item_handle not in accepted_handles or field.item_handle in builtin_cells and (
            allocations[field.item_handle].cell_ids[field.field_key] not in builtin_cells[field.item_handle])
        if withheld and observed[(field.item_handle, field.field_key)].admission == 'accepted':
            observed[(field.item_handle, field.field_key)].admission = 'uncertain'
    extension_handles = {record.item_handle for record in records}
    extension_lineage = []
    for link in lineage:
        if link.kind == 'add':
            children = [handle for handle in link.children if handle in extension_handles]
            if children:
                extension_lineage.append(link.model_copy(update={'children': children}))
        elif set(link.children) <= extension_handles:
            extension_lineage.append(link)
        elif set(link.children) & extension_handles:
            raise ValueError('replacement lineage crosses canonical record families')
    working = apply_accepted_records(working, records, identities, extension_lineage,
        accepted_handles=accepted_handles, expected_revisions=expected_revisions, action_id=proposal.id)
    working = apply_builtin_records(working, builtins, identities, lineage,
        accepted_handles=accepted_handles, expected_revisions=expected_revisions, action_id=proposal.id)
    for handle in builtins.keys() & accepted_handles:
        allocation = allocations[handle]
        retain_builtin_identity(working, allocation, declarations[allocation.semantic_type], package)
    active = {record.id for record in working.records} | {record.id for record in working.extensions if record.active}
    changed_relations = False
    for relation in proposal.resolved_relations:
        if relation.id not in admitted_relations or relation.subject_id not in active or relation.target_id not in active:
            continue
        old = next((value for value in working.relations if value.id == relation.id), None)
        if expected_relation_revisions.get(relation.id) != getattr(old, 'revision', None):
            raise TemplateImportFailure('IMPORT_RELATION_CAPTURE_STALE')
        updated = relation.model_copy(deep=True)
        if old is not None:
            updated.revision = old.revision + 1
            working.relations[working.relations.index(old)] = updated
        else:
            working.relations.append(updated)
        _set_builtin_owner(working, updated)
        changed_relations = True
    for record in working.extensions:
        mirrored = [relation for relation in working.relations if relation.subject_id == record.id]
        if record.relations != mirrored:
            record.revision += 1
            record.relations = mirrored
    if changed_relations:
        working.revision += 1
    applied = {cell.id for record in working.extensions if record.item_handle in accepted_handles for cell in record.cells
        if receipt_id in cell.admission_receipt_ids}
    applied.update(cell for handle, cells in builtin_cells.items() if handle in accepted_handles for cell in cells)
    proposal.applied_receipt_id = receipt_id
    proposal.admitted_cell_ids = sorted(applied)
    proposal.admitted_relation_ids = sorted(relation.id for relation in working.relations
        if relation.id in admitted_relations and relation.active)
    before_records = {record.id: record.revision for record in [*facts.records, *facts.extensions]}
    proposal.admitted_record_revisions = {record.id: record.revision for record in [*working.records, *working.extensions]
        if before_records.get(record.id) != record.revision}
    before_relations = {relation.id: relation.revision for relation in facts.relations}
    proposal.admitted_relation_revisions = {relation.id: relation.revision for relation in working.relations
        if before_relations.get(relation.id) != relation.revision}
    proposal.state = 'accepted' if applied or proposal.admitted_relation_ids else 'rejected'
    task = task_in(result, next(attempt.task_id for attempt in result.attempts if attempt.id == proposal.attempt_id))
    task.expected_checks = review.value.targets
    return checked(result), type(facts).model_validate(working.model_dump(by_alias=True))
