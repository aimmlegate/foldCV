"""Reply locations never become persistent item identity."""

from itertools import count

import pytest

from packages.resume_core.models.template_import import HandleSelector, ProposalReply
from packages.resume_core.templates.models import Binding
from packages.resume_core.templates.projection import validate_payload
from packages.resume_core.rich_fields import field_key
from packages.resume_core.template_identity import (allocate_discoveries, capture_span, codepoint_offset,
    payload_value, resolve_fields, resolve_lineage, source_slice)
from tests.templates.storage_fixtures import source


SCHEMA = {'type': 'object', 'required': ['title'], 'additionalProperties': False,
    'properties': {'title': {'type': 'string'}, 'journal': {'type': 'string'}}}


def reply():
    src, _ = source()
    span = capture_span(src, src.units[0]).model_dump(by_alias=True)
    return ProposalReply(schemaVersion=1,
        payload=[{'title': 'Reliable Queues', 'journal': 'Systems Notes'},
                 {'title': 'Reliable Queues', 'journal': 'Queue Review'}],
        discoveries=[{'key': key, 'semanticType': 'papers', 'pointer': '/' + str(index)}
            for index, key in enumerate(['a', 'b'])],
        fields=[{'item': {'kind': 'discovery_key', 'key': key}, 'fieldKey': field,
            'pointer': '/' + str(index) + '/' + field, 'evidence': [span], 'effectiveCellIds': []}
            for index, key in enumerate(['a', 'b']) for field in ['title', 'journal']],
        lineage=[{'kind': 'add', 'parents': [], 'children': ['a', 'b']}])


def allocate(value, existing=(), id_factory=None):
    return allocate_discoveries(value, operation_id='operation', task_id='papers-task', attempt_id='attempt',
        existing=existing, type_schemas={'papers': SCHEMA}, id_factory=id_factory)


def resolve(value, allocations):
    src, _ = source()
    return resolve_fields(value, allocations, allowed_handles=[], sources=[src], effective_cells=[],
        type_schemas={'papers': SCHEMA}, handle_types={})


def test_discoveries_allocate_once_even_with_shared_titles_and_evidence():
    value = reply()
    serial = count()
    allocated = allocate(value, id_factory=lambda prefix: prefix + '-' + str(next(serial)))
    assert len({item.item_handle for item in allocated}) == 2
    assert allocate(value, allocated) == allocated
    assert len(resolve(value, allocated)) == 4
    lineage = resolve_lineage(value, allocated, allowed_parents=[], attempt_id='attempt')
    assert lineage[0].children == [item.item_handle for item in allocated]
    value.payload.reverse()
    value.discoveries.reverse()
    for discovery in value.discoveries:
        discovery.pointer = '/0' if discovery.key == 'b' else '/1'
    for field in value.fields:
        field.pointer = ('/0/' if field.item.key == 'b' else '/1/') + field.field_key
    reordered = allocate(value, allocated)
    assert {item.key: item.item_handle for item in reordered} == {item.key: item.item_handle for item in allocated}
    assert resolve(value, reordered)[0].item_handle == allocated[0].item_handle


def test_optional_present_field_requires_its_own_evidence_binding():
    value = reply()
    value.fields = [field for field in value.fields if field.field_key == 'title']
    with pytest.raises(ValueError, match='supplied field'):
        resolve(value, allocate(value))


def test_sidecar_cannot_take_another_items_same_shaped_field():
    value = reply()
    value.fields[0].pointer = '/1/title'
    with pytest.raises(ValueError, match='outside its discovered item'):
        resolve(value, allocate(value))


def test_application_identity_collisions_and_rebound_discovery_keys_fail():
    value = reply()
    with pytest.raises(ValueError, match='identities collide'):
        allocate(value, id_factory=lambda _prefix: 'reused')
    allocated = allocate(value)
    value.payload[0].pop('journal')
    with pytest.raises(ValueError, match='reused with different'):
        allocate(value, allocated)


def test_codepoint_source_spans_do_not_reuse_utf16_offsets():
    src, _ = source()
    unit = src.units[0]
    unit.text = 'A😀Бe\u0301Z'
    assert codepoint_offset(unit.text, 3) == 2
    span = capture_span(src, unit, 1, 3)
    assert source_slice([src], span) == '😀Б'
    with pytest.raises(ValueError, match='surrogate'):
        codepoint_offset(unit.text, 2)
    unit.text = 'changed'
    with pytest.raises(ValueError, match='hash mismatch'):
        source_slice([src], span)


@pytest.mark.parametrize('pointer', ['/01', '/-1', '/١', '/2'])
def test_noncanonical_or_out_of_range_array_pointer_fails(pointer):
    with pytest.raises(ValueError, match='does not resolve'):
        payload_value(['a', 'b'], pointer)


def test_captured_repair_reorders_by_handle_and_requires_complete_supplied_bindings():
    value = reply()
    allocated = allocate(value)
    value.discoveries = []
    value.lineage = []
    value.payload.reverse()
    value.payload[0]['journal'] = 'Corrected journal'
    for field in value.fields:
        key = field.item.key
        field.item = HandleSelector(kind='handle', itemHandle=allocated[0 if key == 'a' else 1].item_handle)
        field.pointer = ('/1/' if key == 'a' else '/0/') + field.field_key
    value = ProposalReply.model_validate(value.model_dump(by_alias=True))
    src, _ = source()
    arguments = {'allowed_handles': [a.item_handle for a in allocated], 'sources': [src], 'effective_cells': [],
        'type_schemas': {'papers': SCHEMA}, 'handle_types': {a.item_handle: 'papers' for a in allocated}}
    resolved = resolve_fields(value, [], **arguments)
    assert resolved[1].item_handle == allocated[0].item_handle and resolved[1].pointer == '/1/journal'
    assert resolve_fields(value, [], **arguments) == resolved
    value.fields = [field for field in value.fields if field.pointer != '/0/journal']
    with pytest.raises(ValueError, match='supplied captured field'):
        resolve_fields(value, [], **arguments)


def test_compiled_aliases_bind_raw_fields_to_semantic_cells_without_position_identity():
    value = reply()
    for item in value.payload:
        item['display_title'] = item.pop('title')
    for field in value.fields:
        if field.field_key == 'title':
            field.pointer = field.pointer.replace('/title', '/display_title')
    bindings = [Binding(pointer='/*/display_title', semantic_type='papers', field='title', relation=None),
        Binding(pointer='/*/journal', semantic_type='papers', field='journal', relation=None)]
    allocated = allocate_discoveries(value, operation_id='operation', task_id='papers-task', attempt_id='attempt',
        existing=[], type_schemas={'papers': SCHEMA}, bindings=bindings)
    assert set(allocated[0].cell_ids) == {'title', 'journal'}
    src, _ = source()
    arguments = {'allowed_handles': [], 'sources': [src], 'effective_cells': [], 'type_schemas': {'papers': SCHEMA},
        'handle_types': {}, 'bindings': bindings}
    assert len(resolve_fields(value, allocated, **arguments)) == 4
    value.fields.pop()
    with pytest.raises(ValueError, match='coverage is incomplete'):
        resolve_fields(value, allocated, **arguments)


def test_unavailable_values_do_not_require_fabricated_evidence_and_empty_is_not_identity():
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['title', 'journal'],
        'properties': {'title': {'type': ['string', 'null']}, 'journal': {'type': ['string', 'null']}}}
    value = reply()
    value.payload[0]['journal'] = None
    value.fields[1].evidence = []
    allocated = allocate_discoveries(value, operation_id='operation', task_id='papers-task', attempt_id='attempt',
        existing=[], type_schemas={'papers': schema})
    src, _ = source()
    assert len(resolve_fields(value, allocated, allowed_handles=[], sources=[src], effective_cells=[],
        type_schemas={'papers': schema}, handle_types={})) == 4
    empty = ProposalReply(schemaVersion=1, payload={'title': None, 'journal': None}, discoveries=[], fields=[], lineage=[])
    assert resolve_fields(empty, [], allowed_handles=[], sources=[src], effective_cells=[],
        type_schemas={'papers': schema}, handle_types={}, bindings=[
            Binding(pointer='/title', semantic_type='papers', field='title', relation=None),
            Binding(pointer='/journal', semantic_type='papers', field='journal', relation=None)]) == []


def test_application_builtin_cell_allocator_is_captured_once():
    value = reply()
    calls = []
    def canonical_cell(semantic_type, record_id, key):
        calls.append((semantic_type, record_id, key))
        return field_key(record_id, key)
    options = {'operation_id': 'operation', 'task_id': 'task', 'attempt_id': 'attempt',
        'type_schemas': {'papers': SCHEMA}, 'cell_id_factory': canonical_cell}
    allocated = allocate_discoveries(value, existing=[], **options)
    assert allocated[0].cell_ids['title'] == field_key(allocated[0].record_id, 'title')
    assert len(calls) == 4
    assert allocate_discoveries(value, existing=allocated, **options) == allocated
    assert len(calls) == 4


def test_absent_optional_fields_reserve_identity_without_inserting_values():
    value = reply()
    for item in value.payload:
        item.pop('journal')
    value.fields = [field for field in value.fields if field.field_key == 'title']
    allocated = allocate(value)
    assert set(allocated[0].cell_ids) == {'title', 'journal'}
    assert 'journal' not in value.payload[0]
    assert len(resolve(value, allocated)) == 2


@pytest.mark.parametrize('raw_name', ['publication', 'publication_alias'])
def test_mapped_nullable_ancestor_remains_explicit_without_fabricated_field_evidence(raw_name):
    nested = {'type': ['object', 'null'], 'additionalProperties': False, 'required': ['journal'],
        'properties': {'journal': {'type': 'string'}}}
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['title', 'publication'],
        'properties': {'title': {'type': 'string'}, 'publication': nested}}
    raw_schema = {**schema, 'required': ['title', raw_name], 'properties': {'title': {'type': 'string'}, raw_name: nested}}
    value = reply()
    value.payload = [{'title': 'Paper', raw_name: None}]
    value.discoveries = value.discoveries[:1]
    value.fields = value.fields[:1]
    value.lineage[0].children = ['a']
    validate_payload({'type': 'array', 'items': raw_schema}, value.payload)
    bindings = [Binding(pointer='/*/title', semantic_type='papers', field='title', relation=None),
        Binding(pointer='/*/' + raw_name + '/journal', semantic_type='papers', field='publication.journal', relation=None)]
    options = {'operation_id': 'operation', 'task_id': 'task', 'attempt_id': 'attempt',
        'existing': [], 'type_schemas': {'papers': schema}, 'bindings': bindings}
    allocated = allocate_discoveries(value, **options)
    assert set(allocated[0].cell_ids) == {'title', 'publication.journal'}
    src, _ = source()
    arguments = {'sources': [src], 'effective_cells': [], 'type_schemas': {'papers': schema}, 'bindings': bindings}
    resolved = resolve_fields(value, allocated, allowed_handles=[], handle_types={}, **arguments)
    assert len(resolved) == 1 and resolved[0].field_key == 'title'
    value.discoveries, value.lineage = [], []
    value.fields[0].item = HandleSelector(kind='handle', itemHandle=allocated[0].item_handle)
    assert resolve_fields(value, [], allowed_handles=[allocated[0].item_handle],
        handle_types={allocated[0].item_handle: 'papers'}, **arguments) == resolved
    value.payload[0][raw_name] = {'journal': 'Needs its own sidecar'}
    with pytest.raises(ValueError):
        resolve_fields(value, [], allowed_handles=[allocated[0].item_handle],
            handle_types={allocated[0].item_handle: 'papers'}, **arguments)


@pytest.mark.parametrize('wrapper_depth', [1, 2])
def test_nullable_wrapper_maps_absence_to_a_flat_semantic_field(wrapper_depth):
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['title', 'journal'],
        'properties': {'title': {'type': 'string'}, 'journal': {'type': ['string', 'null']}}}
    wrapped = {'type': ['object', 'null'], 'required': ['journal'], 'additionalProperties': False,
        'properties': {'journal': {'type': ['string', 'null']}}}
    for _ in range(wrapper_depth - 1):
        wrapped = {'type': ['object', 'null'], 'required': ['nested'], 'additionalProperties': False,
            'properties': {'nested': wrapped}}
    raw_schema = {'type': 'array', 'items': {'type': 'object', 'required': ['title', 'publication'],
        'additionalProperties': False, 'properties': {'title': {'type': 'string'}, 'publication': wrapped}}}
    value = reply()
    value.payload = [{'title': 'Paper', 'publication': None}]
    value.discoveries, value.fields = value.discoveries[:1], value.fields[:1]
    value.lineage[0].children = ['a']
    validate_payload(raw_schema, value.payload)
    bindings = [Binding(pointer='/*/title', semantic_type='papers', field='title', relation=None),
        Binding(pointer='/*/publication' + '/nested' * (wrapper_depth - 1) + '/journal',
            semantic_type='papers', field='journal', relation=None)]
    allocated = allocate_discoveries(value, operation_id='operation', task_id='task', attempt_id='attempt',
        existing=[], type_schemas={'papers': schema}, bindings=bindings)
    src, _ = source()
    options = {'sources': [src], 'effective_cells': [], 'type_schemas': {'papers': schema}, 'bindings': bindings}
    resolved = resolve_fields(value, allocated, allowed_handles=[], handle_types={}, **options)
    assert len(resolved) == 1 and resolved[0].field_key == 'title'
    assert set(allocated[0].cell_ids) == {'title', 'journal'}
    assert value.payload == [{'title': 'Paper', 'publication': None}]
    value.discoveries, value.lineage = [], []
    value.fields[0].item = HandleSelector(kind='handle', itemHandle=allocated[0].item_handle)
    assert resolve_fields(value, [], allowed_handles=[allocated[0].item_handle],
        handle_types={allocated[0].item_handle: 'papers'}, **options) == resolved
