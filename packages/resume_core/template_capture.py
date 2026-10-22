"""Capture existing identities without inventing discovery attempts or admission."""

from .models.template_facts import BuiltinItemIdentity, CapturedItemIdentity
from .templates.builtin_mapping import bind_builtin_allocation
from .templates.compiler import canonical, sha256
from .templates.projection import reachable_schema


IDENTITY_FIELDS = ('semantic_type', 'item_handle', 'record_id', 'cell_ids', 'period_ids', 'canonical_fields')


def item_identities(operation):
    values = [*operation.captured_items, *operation.allocations]
    identifiers = [identifier for value in values
        for identifier in [value.item_handle, value.record_id, *value.cell_ids.values(), *value.period_ids.values()]]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('captured/discovered item identities collide')
    return values


def schema_hash(declaration, package):
    return sha256(canonical(reachable_schema(declaration.data_schema, package.definition.content_definitions)))


def builtin_identity(value, declaration, package):
    return BuiltinItemIdentity(**value.model_dump(by_alias=True, include=set(IDENTITY_FIELDS)),
        semanticSchemaHash=schema_hash(declaration, package))


def retain_builtin_identity(facts, value, declaration, package):
    identity = builtin_identity(value, declaration, package)
    old = next((item for item in facts.builtin_identities if item.record_id == identity.record_id), None)
    if old is not None and old != identity:
        raise ValueError('builtin identity mapping is immutable')
    if old is None:
        facts.builtin_identities.append(identity)


def check_builtin_periods(identity, record):
    if not {period.id for period in getattr(record, 'periods', [])} <= set(identity.period_ids.values()):
        raise ValueError('builtin preparation needs explicit existing period slots')


def prepare_builtin_identities(facts, package, previous, *, id_factory):
    result = facts.model_copy(deep=True)
    declarations = {value.id: value for value in package.definition.fact_types}
    existing = {value.record_id: value for value in result.builtin_identities}
    historical = {value.record_id: value for operation in previous for value in item_identities(operation)}
    for record in result.records:
        old = existing.get(record.id)
        if old is not None:
            declaration = declarations.get(old.semantic_type)
            if declaration is None or declaration.builtin_kind != record.kind or old.semantic_schema_hash != schema_hash(declaration, package):
                raise ValueError('incompatible retained builtin identity')
            bind_builtin_allocation(old, declaration, id_factory, new=False)
            check_builtin_periods(old, record)
            continue
        retained = historical.get(record.id)
        if retained is not None:
            declaration = declarations.get(retained.semantic_type)
            if declaration is None or declaration.builtin_kind != record.kind or not retained.canonical_fields:
                raise ValueError('incompatible historical builtin identity')
            bind_builtin_allocation(retained, declaration, id_factory, new=False)
            check_builtin_periods(retained, record)
            retain_builtin_identity(result, retained, declaration, package)
            continue
        candidates = [value for value in declarations.values() if value.builtin_kind == record.kind and value.builtin_fields]
        if len(candidates) != 1 or getattr(record, 'periods', []):
            raise ValueError('builtin preparation needs one declared mapping and explicit existing period slots')
        declaration = candidates[0]
        identity = BuiltinItemIdentity(semanticType=declaration.id, itemHandle=id_factory('item'), recordId=record.id,
            cellIds={}, canonicalFields={}, periodIds={}, semanticSchemaHash=schema_hash(declaration, package))
        identity = bind_builtin_allocation(identity, declaration, id_factory, new=True)
        result.builtin_identities.append(identity)
    if result.builtin_identities != facts.builtin_identities:
        result.revision += 1
    return type(facts).model_validate(result.model_dump(by_alias=True))


def capture_existing_items(facts, package, previous=()):
    declarations = {value.id: value for value in package.definition.fact_types}
    historical = {value.item_handle: value for operation in previous for value in item_identities(operation)}
    result = []
    for record in facts.extensions:
        if not record.active:
            continue
        declaration = declarations.get(record.semantic_type)
        if declaration is None or record.semantic_schema_hash != schema_hash(declaration, package):
            raise ValueError('incompatible captured extension identity')
        cells = {cell.field_key: cell.id for cell in record.cells}
        retained = historical.get(record.item_handle)
        if retained is not None:
            if (retained.record_id != record.id or retained.semantic_type != record.semantic_type
                    or any(retained.cell_ids.get(key) != identifier for key, identifier in cells.items())):
                raise ValueError('captured extension changes retained cell identities')
            cells = dict(retained.cell_ids)
        result.append(CapturedItemIdentity(itemHandle=record.item_handle, recordId=record.id, semanticType=record.semantic_type,
            semanticSchemaHash=record.semantic_schema_hash, recordRevision=record.revision,
            cellIds=cells, canonicalFields={}, periodIds={}))
    identities = {value.record_id: value for value in facts.builtin_identities}
    for record in facts.records:
        identity = identities.get(record.id)
        if identity is None:
            raise ValueError('builtin identity preparation is required')
        declaration = declarations.get(identity.semantic_type)
        if declaration is None or declaration.builtin_kind != record.kind or identity.semantic_schema_hash != schema_hash(declaration, package):
            raise ValueError('incompatible captured builtin identity')
        bind_builtin_allocation(identity, declaration, lambda _prefix: None, new=False)
        check_builtin_periods(identity, record)
        result.append(CapturedItemIdentity(**identity.model_dump(by_alias=True), recordRevision=record.revision))
    return result
