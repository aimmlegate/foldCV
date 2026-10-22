"""One employment subset uses real captured assets and synthetic source wording."""

import json

from packages.resume_core.template_identity import capture_span
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.storage_fixtures import package, source_fixture


TEXT = {'type': ['string', 'null']}
DATE = {'type': ['object', 'null'], 'additionalProperties': False, 'required': ['raw', 'year', 'month'],
    'properties': {'raw': TEXT, 'year': {'type': ['integer', 'null']}, 'month': {'type': ['integer', 'null']}}}


def object_schema(properties, *, nullable=False):
    return {'type': ['object', 'null'] if nullable else 'object', 'additionalProperties': False,
        'required': list(properties), 'properties': properties}


def employment_package():
    config = package().definition.model_dump(mode='json', by_alias=True)
    config['template'].update(id='synthetic-employment', revision='2', name='Employment subset')
    classification = object_schema({'category': {'type': 'string', 'enum': ['description', 'task', 'result']}, 'attribution': TEXT})
    claim = object_schema({'value': TEXT, 'classification': classification})
    technology = object_schema({'display': TEXT})
    employment = object_schema({'company': TEXT, 'role': TEXT, 'start': DATE, 'end': DATE, 'present': {'type': ['boolean', 'null']}})
    config['fact_types'] = [
        {'id': 'employment', 'schema_version': '1', 'schema': employment, 'builtin_kind': 'employment', 'relations': [],
            'builtin_fields': {name: {'field': field, 'period': period} for name, field, period in [
                ('company', 'employer', None), ('role', 'role', None), ('start', 'start', 'employment-period'),
                ('end', 'end', 'employment-period'), ('present', 'present', 'employment-period')]}},
        {'id': 'claim', 'schema_version': '1', 'schema': object_schema({'value': TEXT}), 'builtin_kind': 'claim',
            'relations': [{'kind': 'owned_by', 'target_types': ['employment']}],
            'builtin_fields': {'value': {'field': 'value', 'period': None}}},
        {'id': 'claim-classification', 'schema_version': '1', 'schema': classification, 'builtin_kind': None,
            'relations': [{'kind': 'extension_of', 'target_types': ['claim']}]},
        {'id': 'technology', 'schema_version': '1', 'schema': technology, 'builtin_kind': 'technology',
            'relations': [{'kind': 'owned_by', 'target_types': ['employment']}],
            'builtin_fields': {'display': {'field': 'display', 'period': None}}},
    ]
    block = config['blocks'][0]
    block.update(id='employment-view', content_schema={'type': 'array', 'items': object_schema({
        'company': TEXT, 'role': TEXT,
        'period': object_schema({'raw': TEXT, 'start': DATE, 'end': DATE, 'ongoing': {'type': ['boolean', 'null']}}),
        'description': {**claim, 'type': ['object', 'null']},
        'tasks': {'type': 'array', 'items': claim}, 'results': {'type': 'array', 'items': claim},
        'technologies': {'type': 'array', 'items': technology}})}, bindings=[],
        extract=['Retain each employer, task, result and technology as a distinct source-backed item.'],
        rewrite={'fields': ['/*/description/value', '/*/tasks/*/value', '/*/results/*/value'],
            'instructions': ['Preserve attribution and exact numeric bounds. Do not invent results.']})
    for field, pointer in [('company', '/*/company'), ('role', '/*/role'), ('start', '/*/period/start'),
            ('end', '/*/period/end'), ('present', '/*/period/ongoing')]:
        block['bindings'].append({'pointer': pointer, 'semantic_type': 'employment', 'field': field,
            'item_pointer': '/*', 'relation': None})
    for root in ['/*/description', '/*/tasks/*', '/*/results/*']:
        block['bindings'].append({'pointer': root + '/value', 'semantic_type': 'claim', 'field': 'value',
            'item_pointer': root, 'relation': {'kind': 'owned_by', 'subject_pointer': '/*'}})
        for field in ['category', 'attribution']:
            block['bindings'].append({'pointer': root + '/classification/' + field, 'semantic_type': 'claim-classification',
                'field': field, 'item_pointer': root + '/classification',
                'relation': {'kind': 'extension_of', 'subject_pointer': root}})
    block['bindings'].append({'pointer': '/*/technologies/*/display', 'semantic_type': 'technology', 'field': 'display',
        'item_pointer': '/*/technologies/*', 'relation': {'kind': 'owned_by', 'subject_pointer': '/*'}})
    block['view'].update(heading='band', title={'en': 'PROJECTS'}, inset=10.5, item_gap=12.57, fallback_style='body', nodes=[
        {'type': 'text', 'field': '/company', 'style': 'project'},
        {'type': 'period', 'field': '/period', 'style': 'support'},
        {'type': 'tags', 'field': '/technologies', 'item_field': '/display', 'style': 'support', 'background': 'band'},
        {'type': 'text', 'field': '/description/value', 'style': 'body'},
        {'type': 'text', 'field': '/role', 'prefix': {'en': 'Role: '}, 'style': 'body'},
        {'type': 'bullets', 'field': '/tasks', 'item_field': '/value', 'style': 'body', 'label': {'en': 'Tasks:'}},
        {'type': 'bullets', 'field': '/results', 'item_field': '/value', 'style': 'body', 'label': {'en': 'Results:'}},
    ])
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def employment_source(name='F01'):
    return source_fixture(name)


def employment_proposal(src, *, unsupported=False):
    unit = src.units[0]
    detailed = '03.2020' in unit.text
    start, end = ('03.2020', '11.2023') if detailed else ('2020', '2023')
    result = 'Our team reduced median latency from 800 ms to 500 ms.'
    has_result = result in unit.text
    def span(text):
        offset = unit.text.index(text)
        return capture_span(src, unit, offset, offset + len(text)).model_dump(by_alias=True)
    payload = [{'company': 'Example Labs', 'role': 'backend engineer',
        'period': {'raw': start + '–' + end, 'start': {'raw': start, 'year': 2020, 'month': 3 if detailed else None},
            'end': {'raw': end, 'year': 2023, 'month': 11 if detailed else None}, 'ongoing': False},
        'description': None, 'tasks': [{'value': 'Implemented queue processing.',
            'classification': {'category': 'task', 'attribution': None}}],
        'results': [{'value': 'I reduced median latency by 80%.' if unsupported else result,
            'classification': {'category': 'result', 'attribution': 'individual' if unsupported else 'team'}}] if has_result else [],
        'technologies': [{'display': 'Python'}]}]
    discoveries, fields, relations = [], [], []
    def discover(key, semantic, pointer):
        discoveries.append({'key': key, 'semanticType': semantic, 'pointer': pointer})
    def field(key, name, pointer, evidence):
        fields.append({'item': {'kind': 'discovery_key', 'key': key}, 'fieldKey': name,
            'pointer': pointer, 'evidence': evidence, 'effectiveCellIds': []})
    def relation(key, kind, subject, target, evidence):
        relations.append({'relation': {'kind': 'discovery_key', 'key': key}, 'kind': kind,
            'subject': {'kind': 'discovery_key', 'key': subject}, 'target': {'kind': 'discovery_key', 'key': target},
            'evidence': evidence})
    discover('job', 'employment', '/0')
    for name, pointer, text in [('company', '/0/company', 'Example Labs'), ('role', '/0/role', 'backend engineer'),
            ('start', '/0/period/start', start), ('end', '/0/period/end', end), ('present', '/0/period/ongoing', start + '–' + end)]:
        field('job', name, pointer, [span(text)])
    for group, text in [('tasks', 'Implemented queue processing.'), ('results', result)]:
        if not payload[0][group]:
            continue
        root, key = '/0/' + group + '/0', group + '-entry'
        evidence = [span(text)]
        discover(key, 'claim', root)
        field(key, 'value', root + '/value', evidence)
        relation('owner-' + key, 'owned_by', key, 'job', evidence)
        discover(key + '-classification', 'claim-classification', root + '/classification')
        for name in ['category', 'attribution']:
            field(key + '-classification', name, root + '/classification/' + name,
                evidence if payload[0][group][0]['classification'][name] is not None else [])
        relation('class-' + key, 'extension_of', key + '-classification', key, evidence)
    discover('technology', 'technology', '/0/technologies/0')
    field('technology', 'display', '/0/technologies/0/display', [span('Python')])
    relation('technology-owner', 'owned_by', 'technology', 'job', [span('Python')])
    return {'schemaVersion': 1, 'payload': payload, 'discoveries': discoveries, 'fields': fields,
        'lineage': [{'kind': 'add', 'parents': [], 'children': [value['key'] for value in discoveries]}], 'relations': relations}
