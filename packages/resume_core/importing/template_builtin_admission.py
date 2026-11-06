"""Admitted semantic fields become existing rich records without trusting worker IDs."""

from pydantic import TypeAdapter

from ..models.contracts import PartialDate
from ..models.evidence import EvidenceSpan
from ..models.rich_facts import RichFact, WorkingField, RecordTombstone
from ..editing.fact_mutations import _revise
from ..fields import working_field
from .template_identity import empty_value
from ..templates.source_spans import payload_value
from ..sources import source_slice
from ..import_failure import TemplateImportFailure
from ..editing.template_mutations import content
from ..templates.builtin_mapping import DATE_KEYS, bind_builtin_allocation


# The fields a new record of each supported kind starts with, all unknown.
FIELDS = {'employment': ['employer', 'role'], 'subproject': ['name', 'role'], 'claim': ['value'],
    'technology': ['display', 'canonicalId', 'experience'], 'candidate': ['name', 'title', 'location'],
    'education': ['institution', 'qualification', 'specialty', 'completion'], 'language': ['language', 'level'],
    'certification': ['name', 'issuer', 'date']}
SUPPORTED = set(FIELDS)
RECORD = TypeAdapter(RichFact)


def human_authority(record):
    if hasattr(record, 'cells'):
        from .template_replacements import has_human_authority
        return has_human_authority(record)
    fields = [value for key in type(record).model_fields if isinstance(value := getattr(record, key), WorkingField)]
    fields += [value for period in getattr(record, 'periods', []) for value in [period.start, period.end, period.present]]
    return record.origin == 'user' or record.user_corrected or any(value.user_corrected for value in fields)


def current_handles(operation, facts):
    from ..template_capture import item_identities
    records = {record.id: record for record in facts.records}
    result = {record.item_handle: record for record in facts.extensions}
    result.update({allocation.item_handle: records[allocation.record_id] for allocation in item_identities(operation)
        if allocation.record_id in records})
    return result


def unknown():
    return {'value': None, 'rawText': '', 'status': 'unknown', 'revision': 1, 'pendingRawText': None, 'userCorrected': False}


def admitted_field(raw, destination):
    value, text = raw, str(raw).lower() if isinstance(raw, bool) else raw
    if (destination.period_id is not None and not destination.field_key.endswith(':present')
            or destination.period_id is None and destination.field_key in DATE_KEYS):
        if not isinstance(raw, dict):
            raise ValueError('admitted date must contain its exact raw object')
        text, year, month = raw.get('raw'), raw.get('year'), raw.get('month')
        if text is not None and not isinstance(text, str):
            raise ValueError('date raw text must be a string or null')
        value = None if year is None else PartialDate(precision='day' if raw.get('day') is not None else
            'month' if month is not None else 'year', year=year, month=month, day=raw.get('day')).model_dump(by_alias=True)
        text = text if text is not None else ''
    return {'value': value, 'rawText': text, 'status': 'known' if value is not None else 'unresolved' if text else 'unknown',
        'revision': 1, 'pendingRawText': None, 'userCorrected': False}


class WithheldOwner(ValueError):
    """The owner a new record needs was not admitted: the record waits with it, the block's other values stay."""


def inferred_owner_relations(proposal, allocations, declarations, facts, sources, relations):
    """The employment a new subproject joins when its reply names none: in an entry request (D117) the outline may
    have cut the projects of an employer from the lines that name it, so the model cannot state the employer. A CV
    lists an employer's projects under it, so the subproject joins the nearest employment above its first cited line.
    The relations stand in for the reply's during admission only; the record keeps its owner as its job id."""
    from ..models.template_facts import Relation
    owned = {relation.subject_id for relation in relations if relation.active and relation.kind == 'owned_by'}
    known = {record.id for record in facts.records}
    order = {(source.id, unit.id): (index, position) for index, source in enumerate(sources)
        for position, unit in enumerate(source.units)}
    def position(source_id, unit_id, text=None, start=0):
        unit = next((unit for source in sources if source.id == source_id for unit in source.units if unit.id == unit_id), None)
        if unit is None or (source_id, unit_id) not in order:
            return None
        offset = unit.text.find(text) if text else start
        return (*order[(source_id, unit_id)], max(offset, 0))
    employments = []
    for record in facts.records:
        if record.kind != 'employment':
            continue
        starts = [place for span in record.evidence if (place := position(span.source_id, span.unit_id, span.text)) is not None]
        if starts:
            employments.append((min(starts), record.id))
    result = []
    for handle in dict.fromkeys(field.item_handle for field in proposal.resolved_fields):
        allocation = allocations[handle]
        if (declarations[allocation.semantic_type].builtin_kind != 'subproject' or allocation.record_id in known
                or allocation.record_id in owned):
            continue
        starts = [place for field in proposal.resolved_fields if field.item_handle == handle for span in field.evidence
            if (place := position(span.source_id, span.unit_id, start=span.start)) is not None]
        above = [(place, identifier) for place, identifier in employments if starts and place <= min(starts)]
        if above:
            result.append(Relation(id='relation-inferred-' + allocation.record_id, kind='owned_by',
                subjectId=allocation.record_id, targetId=max(above)[1], revision=1, active=True))
    return result


def owner_values(record_id, operation, facts, declarations, relations):
    from ..template_capture import item_identities
    records = {record.id: record for record in facts.records}
    allocations = {allocation.record_id: allocation for allocation in item_identities(operation)}
    def kind(identifier):
        if identifier in records:
            return records[identifier].kind
        allocation = allocations.get(identifier)
        return declarations[allocation.semantic_type].builtin_kind if allocation else None
    def owner(identifier):
        values = [relation.target_id for relation in relations if relation.active and relation.kind == 'owned_by'
            and relation.subject_id == identifier]
        if len(values) > 1:
            raise ValueError('multiple proposed builtin owners')
        return values[0] if values else None
    target = owner(record_id)
    if target is None:
        previous = records.get(record_id)
        return getattr(previous, 'job_id', None), getattr(previous, 'subproject_id', None)
    if kind(target) == 'employment':
        return target, None
    if kind(target) == 'subproject':
        job = owner(target) or getattr(records.get(target), 'job_id', None)
        if job is None:
            raise WithheldOwner('subproject requires its admitted employment owner')
        if kind(job) != 'employment':
            raise ValueError('subproject requires its admitted employment owner')
        return job, target
    raise ValueError('incompatible canonical builtin owner')


def make_builtin_candidate(operation, allocation, declaration, fields, payload, admitted_cells, sources, facts,
                           declarations, relations, *, raw_texts=None):
    if declaration.builtin_kind not in SUPPORTED or not declaration.builtin_fields:
        raise TemplateImportFailure('IMPORT_BUILTIN_ADAPTER_REQUIRED')
    bind_builtin_allocation(allocation, declaration, lambda _prefix: None, new=False)
    previous = next((record for record in facts.records if record.id == allocation.record_id), None)
    if previous is not None and previous.kind != declaration.builtin_kind:
        raise ValueError('builtin replacement changes canonical type')
    kind = declaration.builtin_kind
    if previous is None:
        if not any(allocation.canonical_fields[field.field_key].cell_id in admitted_cells
                and not empty_value(payload_value(payload, field.pointer)) for field in fields):
            return None, set()
        data = {'id': allocation.record_id, 'revision': 1, 'origin': 'source', 'evidence': [],
            'userCorrected': False, 'kind': kind}
        data.update({name: unknown() for name in FIELDS[kind]})
        if kind in {'employment', 'subproject'}:
            data['periods'] = []
        if kind in {'claim', 'technology', 'subproject'}:
            try:
                job, project = owner_values(allocation.record_id, operation, facts, declarations, relations)
            except WithheldOwner:
                return None, set()
            if kind == 'subproject' and job is None:
                return None, set()
            if kind == 'subproject' and project is not None:
                raise ValueError('new subproject needs a direct employment owner')
            data['jobId'] = job
            if kind != 'subproject':
                data['subprojectId'] = project
    else:
        data = previous.model_dump(mode='json', by_alias=True)
    applied = set()
    for field in fields:
        target = allocation.canonical_fields[field.field_key]
        raw = payload_value(payload, field.pointer)
        if empty_value(raw) or target.cell_id not in admitted_cells:
            continue
        old_field = working_field(previous, target.field_key) if previous is not None else None
        if previous is not None and (previous.origin == 'user' or previous.user_corrected or old_field is not None
                and (old_field.user_corrected or old_field.status == 'pending')):
            continue
        value = admitted_field(raw, target)
        if isinstance(raw, str) and raw_texts is not None:
            value['rawText'] = raw_texts[target.cell_id]
        if old_field is not None:
            value['revision'] = old_field.revision
        if target.period_id is not None:
            period = next((period for period in data['periods'] if period['id'] == target.period_id), None)
            if period is None:
                period = {'id': target.period_id, 'revision': 1, 'start': unknown(), 'end': unknown(),
                    'present': unknown(), 'evidence': []}
                data['periods'].append(period)
            period[target.field_key.rsplit(':', 1)[1]] = value
        else:
            data[target.field_key] = value
        applied.add(target.cell_id)
        evidence = [EvidenceSpan(sourceId=span.source_id, sourceRevision=span.source_revision, unitId=span.unit_id,
            unitRevision=span.unit_revision, text=source_slice(sources, span)).model_dump(by_alias=True)
            for span in field.evidence if span.end > span.start]
        if previous is None:
            for span in evidence:
                if span not in data['evidence']:
                    data['evidence'].append(span)
        if target.period_id is not None and (previous is None or not any(
                period.id == target.period_id for period in previous.periods)):
            period['evidence'] = list({str(span): span for span in [*period['evidence'], *evidence]}.values())
    if previous is None and not applied:
        return None, set()
    return RECORD.validate_python(data), applied


def apply_builtin_records(facts, incoming, allocations, lineage, *, accepted_handles, expected_revisions, action_id):
    result = facts.model_copy(deep=True)
    by_id = {record.id: record for record in result.records}
    existing = {allocation.item_handle: by_id[allocation.record_id] for allocation in allocations
        if allocation.record_id in by_id}
    allocated = {allocation.item_handle: allocation for allocation in allocations}
    groups = [(link.parents, link.children) for link in lineage if link.kind != 'add' and set(link.children) & incoming.keys()]
    groups += [([], [handle]) for link in lineage if link.kind == 'add' for handle in link.children if handle in incoming]
    groups += [([], [handle]) for handle in incoming if handle in existing and not any(handle in link.children for link in lineage)]
    for parents, children in groups:
        if not set(children) <= set(accepted_handles):
            continue
        if not set(children) <= incoming.keys() or any(handle not in existing for handle in parents):
            raise ValueError('builtin lineage crosses canonical record families')
        if any(human_authority(existing[handle]) for handle in parents):
            continue
        if len({allocated[handle].semantic_type for handle in [*parents, *children]}) != 1:
            raise ValueError('builtin lineage changes semantic type')
        retiring = {existing[handle].id for handle in parents}
        if any(relation.active and relation.target_id in retiring and relation.subject_id not in retiring
                and relation.kind in {'owned_by', 'extension_of'} for relation in result.relations) or any(
            (getattr(record, 'job_id', None) in retiring or getattr(record, 'subproject_id', None) in retiring)
                and record.id not in retiring for record in result.records):
            raise ValueError('builtin replacement leaves an owned dependent without its owner')
        for handle in [*parents, *[child for child in children if child in existing]]:
            if expected_revisions.get(handle) != existing[handle].revision:
                raise ValueError('stale builtin replacement capture')
        for handle in children:
            candidate, prior = incoming[handle], existing.get(handle)
            if candidate.id != allocated[handle].record_id or prior is not None and (
                    candidate.kind, candidate.origin, candidate.evidence) != (prior.kind, prior.origin, prior.evidence):
                raise ValueError('builtin replacement changes retained identity or source evidence')
            if prior is not None and content(candidate) == content(prior):
                continue
            updated = _revise(candidate, prior, prior.revision if prior else 0)
            position = next((index for index, record in enumerate(result.records) if record.id == candidate.id), None)
            if position is None:
                result.records.append(updated)
            else:
                result.records[position] = updated
        for handle in parents:
            parent = existing[handle]
            position = next(index for index, record in enumerate(result.records) if record.id == parent.id)
            result.records.pop(position)
            result.tombstones.append(RecordTombstone(recordId=parent.id, revision=parent.revision + 1,
                actionId=action_id, orderIndex=position))
        for relation in result.relations:
            if relation.active and (relation.subject_id in retiring or relation.target_id in retiring):
                relation.active = False
                relation.revision += 1
    for record in result.extensions:
        mirrored = [relation for relation in result.relations if relation.subject_id == record.id]
        if record.relations != mirrored:
            record.relations = mirrored
            record.revision += 1
    if result.records != facts.records or result.relations != facts.relations:
        result.revision += 1
    return result
