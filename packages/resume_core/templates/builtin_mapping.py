"""Explicit semantic fields map to existing closed rich-record fields."""

from .projection import SchemaFailure, pointer_tokens, schema_at


TEXT_FIELDS = {
    'candidate': {'name', 'title', 'location'}, 'detail': {'value'},
    'employment': {'employer', 'role'}, 'subproject': {'name', 'role'},
    'technology': {'display', 'canonicalId', 'experience'},
    'education': {'institution', 'qualification', 'specialty'},
    'language': {'language', 'level'}, 'certification': {'name', 'issuer'},
    'claim': {'value'},
}
DATE_FIELDS = {'education': {'completion'}, 'certification': {'date'}}
PERIOD_FIELDS = {'start', 'end', 'present'}


def types_at(schema, pointer):
    node = schema_at(schema, pointer)
    value = node.get('type')
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return set(value)
    branches = node.get('anyOf')
    if isinstance(branches, list):
        return set().union(*(types_at({**branch, '$defs': schema.get('$defs', {})}, '') for branch in branches))
    return set()


def validate_builtin_mapping(declaration, schema):
    if not declaration.builtin_fields:
        return
    kind, seen = declaration.builtin_kind, set()
    if kind is None:
        raise SchemaFailure('/fact_types/' + declaration.id, 'extension type cannot map builtin fields')
    for key, binding in declaration.builtin_fields.items():
        pointer = '/' + '/'.join(token.replace('~', '~0').replace('/', '~1') for token in key.split('.'))
        field_types = types_at(schema, pointer)
        period = kind in {'employment', 'subproject'} and binding.field in PERIOD_FIELDS
        if period != (binding.period is not None):
            raise SchemaFailure(pointer, 'period slot belongs only to start/end/present fields')
        destination = (binding.field, binding.period)
        if destination in seen:
            raise SchemaFailure(pointer, 'duplicate canonical builtin destination')
        seen.add(destination)
        date = period and binding.field != 'present' or binding.field in DATE_FIELDS.get(kind, set())
        expected = {'object', 'null'} if date or kind in {'metric', 'leadership'} and binding.field == 'value' else (
            {'boolean', 'null'} if period else {'string', 'null'} if binding.field in TEXT_FIELDS.get(kind, set()) else set())
        if not expected or not field_types or not field_types <= expected:
            raise SchemaFailure(pointer, 'incompatible or unsupported canonical builtin field')
        if date and 'object' in field_types:
            node = schema_at(schema, pointer)
            if not {'raw', 'year', 'month'} <= set(node.get('properties', {})):
                raise SchemaFailure(pointer, 'date mapping requires raw/year/month object fields')
            for member, allowed in [('raw', {'string', 'null'}), ('year', {'integer', 'null'}), ('month', {'integer', 'null'})]:
                member_types = types_at(schema, pointer + '/' + member)
                if not member_types or not member_types <= allowed:
                    raise SchemaFailure(pointer, 'incompatible canonical date component')


def validate_item_pointer(schema, binding):
    if binding.item_pointer is None:
        return
    root, field = pointer_tokens(binding.item_pointer), pointer_tokens(binding.pointer)
    if len(root) >= len(field) or field[:len(root)] != root:
        raise SchemaFailure(binding.pointer, 'item_pointer must be an unambiguous field ancestor')
    kinds = types_at(schema, binding.item_pointer)
    if 'object' not in kinds or not kinds <= {'object', 'null'}:
        raise SchemaFailure(binding.item_pointer, 'item_pointer must select an object')


def bind_builtin_allocation(allocation, declaration, id_factory, *, new):
    if not declaration.builtin_fields:
        return allocation
    from ..models.template_facts import CanonicalFieldBinding
    from ..rich_fields import field_key
    result = allocation.model_copy(deep=True)
    slots = {binding.period for binding in declaration.builtin_fields.values() if binding.period is not None}
    if new:
        result.period_ids = {slot: id_factory('period') for slot in sorted(slots)}
    if set(result.period_ids) != slots:
        raise ValueError('captured builtin period map changed')
    canonical = {}
    for key, binding in declaration.builtin_fields.items():
        period = result.period_ids[binding.period] if binding.period is not None else None
        target = 'period:' + period + ':' + binding.field if period is not None else binding.field
        canonical[key] = CanonicalFieldBinding(fieldKey=target, cellId=field_key(result.record_id, target), periodId=period)
    if not new and result.canonical_fields != canonical:
        raise ValueError('captured canonical builtin field map changed')
    result.canonical_fields = canonical
    result.cell_ids = {key: value.cell_id for key, value in canonical.items()}
    return type(allocation).model_validate(result.model_dump(by_alias=True))
