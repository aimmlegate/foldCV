"""Canonical cells, nested extension roots and explicit owners share one allocation."""

from itertools import count
from types import SimpleNamespace

import pytest

from packages.resume_core.models.template_import import ProposalReply
from packages.resume_core.rich_fields import field_key
from packages.resume_core.template_identity import allocate_discoveries, capture_span, resolve_fields
from packages.resume_core.template_proposals import resolve_relations
from packages.resume_core.templates.projection import reachable_schema
from tests.templates.storage_fixtures import source
from tests.templates.test_compiler_versions import compile_config, nested_config


def mapped_reply(tmp_path):
    config = nested_config()
    date = {'type': 'object', 'additionalProperties': False, 'required': ['raw', 'year', 'month'],
        'properties': {'raw': {'type': ['string', 'null']}, 'year': {'type': ['integer', 'null']},
            'month': {'type': ['integer', 'null']}}}
    employment = config['fact_types'][0]
    employment['schema']['required'].append('start')
    employment['schema']['properties']['start'] = date
    employment['builtin_fields']['start'] = {'field': 'start', 'period': 'employment-period'}
    content = config['blocks'][0]['content_schema']['items']
    content['required'].append('period')
    content['properties']['period'] = {'type': 'object', 'additionalProperties': False, 'required': ['start'],
        'properties': {'start': date}}
    config['blocks'][0]['bindings'].append({'pointer': '/*/period/start', 'semantic_type': 'employment', 'field': 'start',
        'item_pointer': '/*', 'relation': None})
    package = compile_config(config, tmp_path)
    src, _raw = source()
    span = capture_span(src, src.units[0]).model_dump(by_alias=True)
    discoveries, fields, relations, payload = [], [], [], []
    for index, name in enumerate(['a', 'b']):
        payload.append({'company': 'Example ' + name, 'details': {'scope': 'Scope ' + name}, 'tasks': [],
            'period': {'start': {'raw': '2020', 'year': 2020, 'month': None}}})
        for key, semantic, root, parts in [('job-' + name, 'employment', '/' + str(index),
                [('company', '/company'), ('start', '/period/start')]),
            ('extras-' + name, 'extras', '/' + str(index) + '/details', [('scope', '/scope')])]:
            discoveries.append({'key': key, 'semanticType': semantic, 'pointer': root})
            fields.extend({'item': {'kind': 'discovery_key', 'key': key}, 'fieldKey': field,
                'pointer': '/' + str(index) + suffix if field == 'start' else root + suffix,
                'evidence': [span], 'effectiveCellIds': []} for field, suffix in parts)
        relations.append({'relation': {'kind': 'discovery_key', 'key': 'attachment-' + name}, 'kind': 'extension_of',
            'subject': {'kind': 'discovery_key', 'key': 'extras-' + name},
            'target': {'kind': 'discovery_key', 'key': 'job-' + name}, 'evidence': [span]})
    reply = ProposalReply(schemaVersion=1, payload=payload, discoveries=discoveries, fields=fields,
        lineage=[{'kind': 'add', 'parents': [], 'children': [value['key'] for value in discoveries]}], relations=relations)
    declarations = {value.id: value for value in package.definition.fact_types}
    schemas = {key: reachable_schema(value.data_schema, {}) for key, value in declarations.items()}
    serial = count()
    options = {'operation_id': 'operation', 'task_id': 'task', 'attempt_id': 'attempt', 'type_schemas': schemas,
        'bindings': package.definition.blocks[0].bindings, 'type_declarations': declarations,
        'id_factory': lambda prefix: prefix + '-' + str(next(serial))}
    allocated = allocate_discoveries(reply, existing=[], **options)
    return package, src, reply, allocated, options


def test_canonical_date_cell_and_application_period_survive_replay_and_reordering(tmp_path):
    _package, _src, reply, allocated, options = mapped_reply(tmp_path)
    jobs = [value for value in allocated if value.semantic_type == 'employment']
    assert jobs[0].period_ids != jobs[1].period_ids
    for allocation in jobs:
        period = allocation.period_ids['employment-period']
        target = allocation.canonical_fields['start']
        assert target.field_key == 'period:' + period + ':start'
        assert target.period_id == period
        assert allocation.cell_ids['start'] == target.cell_id == field_key(allocation.record_id, target.field_key)
        assert allocation.cell_ids['company'] == field_key(allocation.record_id, 'employer')
    reply.discoveries.reverse()
    reply.fields.reverse()
    replayed = allocate_discoveries(reply, existing=allocated, **options)
    assert {value.key: value for value in replayed} == {value.key: value for value in allocated}


def test_changed_mapping_or_missing_period_cannot_rebind_a_captured_allocation(tmp_path):
    _package, _src, reply, allocated, options = mapped_reply(tmp_path)
    changed = [value.model_copy(deep=True) for value in allocated]
    changed[0].canonical_fields['company'].cell_id = 'replacement-cell'
    with pytest.raises(ValueError, match='field map changed'):
        allocate_discoveries(reply, existing=changed, **options)
    changed = [value.model_copy(deep=True) for value in allocated]
    changed[0].period_ids = {}
    with pytest.raises(ValueError, match='period map changed'):
        allocate_discoveries(reply, existing=changed, **options)


@pytest.mark.parametrize('swap', [False, True])
def test_nested_extension_has_a_distinct_root_and_cannot_take_another_item_field(tmp_path, swap):
    _package, src, reply, allocated, options = mapped_reply(tmp_path)
    if swap:
        next(field for field in reply.fields if field.field_key == 'scope').pointer = '/1/details/scope'
        with pytest.raises(ValueError, match='discovered item|compiled item scope'):
            resolve_fields(reply, allocated, allowed_handles=[], sources=[src], effective_cells=[],
                type_schemas=options['type_schemas'], handle_types={}, bindings=options['bindings'])
    else:
        fields = resolve_fields(reply, allocated, allowed_handles=[], sources=[src], effective_cells=[],
            type_schemas=options['type_schemas'], handle_types={}, bindings=options['bindings'])
        assert len(fields) == 6 and len({value.item_handle for value in fields}) == 4


@pytest.mark.parametrize('failure', [None, 'wrong_owner', 'missing_owner'])
def test_extension_attachment_needs_the_explicit_matching_parent(tmp_path, failure):
    _package, src, reply, allocated, options = mapped_reply(tmp_path)
    if failure == 'wrong_owner':
        reply.relations[0].target.key = 'job-b'
    elif failure == 'missing_owner':
        reply.relations.pop(0)
    operation = SimpleNamespace(id='operation', captured_items=[], allocations=[], relation_allocations=[])
    task, attempt = SimpleNamespace(id='task', allowed_handles=[]), SimpleNamespace(id='attempt')
    arguments = {'captured_relations': [], 'bindings': options['bindings'], 'id_factory': options['id_factory']}
    declarations = {value.id: value for value in _package.definition.fact_types}
    if failure:
        with pytest.raises(ValueError, match='configured subject root|relationship is missing'):
            resolve_relations(reply, operation, task, attempt, allocated, declarations, [src], **arguments)
    else:
        relations, _allocated = resolve_relations(reply, operation, task, attempt, allocated, declarations, [src], **arguments)
        by_key = {value.key: value.record_id for value in allocated}
        assert [(value.subject_id, value.target_id) for value in relations] == [
            (by_key['extras-a'], by_key['job-a']), (by_key['extras-b'], by_key['job-b'])]
