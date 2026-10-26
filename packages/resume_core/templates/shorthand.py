"""Short template authoring (schema_version 4): the parts a person edits, expanded to the canonical version 3.

Every shorthand is optional and the canonical form stays valid in its place. The expansion is a pure function of the
document, so a package recaptures the same definition from its original bytes.

- Field types: `text`, `date` or another content definition name; `string` is a non-empty string, and `boolean`,
  `integer` and `number` are plain types; `[X]` is a list of X; `{list: X, maxItems: 10}` adds array limits; a mapping
  is an object of fields, and `name?:` lets that field be null. A mapping with `type`, `$ref`, `anyOf`, `enum` or `const` is a JSON schema kept as written.
- Blocks: `region` and `order` place the block; `mode: model`, the whole source as input, no dependencies, no
  operation, no condition and an empty rewrite are defaults. `when: role-branch = technical` is a condition.
- Checks: every block gets its evidence and support checks; `review:` adds support instructions before the standard
  one; `checks:` as a mapping adds `kind: instruction` checks, as a list it is the full canonical list.
- Facts: `facts:` maps a fact type to the fields it records, `type (extension_of): [nested/field]` for a part linked
  to the item, `path=field` when the fact field has another name. Without `facts:` the item's own fields record
  the block's fact type.
- Assets: `id: path`, with role and type read from the file extension; a mapping overrides them.
"""

import copy
import re

from .projection import SchemaFailure

STANDARD_SUPPORT = ('Every interpretation and rewritten claim must be supported by its source; review absence/coverage '
    'for empty extraction.')
SCHEMA_KEYS = {'type', '$ref', 'anyOf', 'enum', 'const'}
SCALARS = ('string', 'boolean', 'integer', 'number')
EXTENSIONS = {'.ttf': ('font', 'font/ttf', 'allowed'), '.otf': ('font', 'font/otf', 'allowed'),
    '.png': ('icon', 'image/png', 'not_applicable'), '.jpg': ('icon', 'image/jpeg', 'not_applicable'),
    '.jpeg': ('icon', 'image/jpeg', 'not_applicable'), '.json': ('catalog', 'application/json', 'not_applicable'),
    '.txt': ('catalog', 'text/plain', 'not_applicable')}
RELATIONS = ('extension_of', 'owned_by', 'related_to')
BLOCK_KEYS = {'id', 'effort', 'mode', 'selectors', 'schema', 'content_schema', 'facts', 'bindings', 'extract', 'rewrite',
    'review', 'checks', 'depends_on', 'operation', 'when', 'region', 'order', 'placement', 'view'}
FACT_TYPE_KEYS = {'id', 'schema_version', 'fields', 'schema', 'builtin', 'builtin_kind', 'relations', 'builtin_fields'}


def fail(path, message):
    raise SchemaFailure(path, message)


def need(item, key, path):
    if not isinstance(item, dict) or key not in item:
        fail(path, 'missing ' + key)
    return item[key]


def qualified(name, path):
    if not isinstance(name, str) or not name.strip():
        fail(path, 'expected a fact type name')
    name = name.strip()
    return name if ':' in name else 'foldcv:' + name


def expand_schema(value, definitions, path, nullable=False):
    if isinstance(value, str):
        if value in SCALARS:
            kind = [value, 'null'] if nullable else value
            return {'type': kind, 'minLength': 1} if value == 'string' else {'type': kind}
        if nullable:
            fail(path, 'a named type decides null itself; drop the "?"')
        if value in definitions:
            return {'$ref': '#/$defs/' + value}
        fail(path, 'unknown field type: ' + value)
    if isinstance(value, list):
        if len(value) != 1 or nullable:
            fail(path, 'a list names exactly one item type')
        return {'type': 'array', 'items': expand_schema(value[0], definitions, path + '/0')}
    if not isinstance(value, dict) or not value:
        fail(path, 'expected a field type')
    if SCHEMA_KEYS & value.keys():
        if nullable:
            fail(path, 'write a JSON schema that allows null instead of an optional marker')
        return value
    if 'list' in value:
        if nullable:
            fail(path, 'a list cannot be optional')
        return {'type': 'array', **{key: item for key, item in value.items() if key != 'list'},
            'items': expand_schema(value['list'], definitions, path + '/list')}
    properties = {}
    for key, child in value.items():
        name = key[:-1] if isinstance(key, str) and key.endswith('?') else key
        if not isinstance(name, str) or not name or name in properties:
            fail(path, 'invalid field name: ' + str(key))
        properties[name] = expand_schema(child, definitions, path + '/' + name, nullable=name != key)
    return {'type': ['object', 'null'] if nullable else 'object', 'additionalProperties': False,
        'required': list(properties), 'properties': properties}


def schema_types(schema):
    kind = schema.get('type') if isinstance(schema, dict) else None
    return set(kind) if isinstance(kind, list) else {kind}


def expand_inputs(values, path):
    if not isinstance(values, list):
        fail(path, 'expected a list of inputs')
    result = []
    for index, value in enumerate(values):
        if isinstance(value, dict):
            result.append(value)
            continue
        if not isinstance(value, str) or not value:
            fail(f'{path}/{index}', 'expected kind:id or a block id')
        kind, _, identifier = value.partition(':') if ':' in value else ('block', '', value)
        result.append({'kind': kind, 'id': identifier})
    return result


def expand_facts(facts, schema, block, path):
    items = 'array' in schema_types(schema)
    root = '/*' if items else ''
    if facts is None:
        target = schema.get('items') if items else schema
        properties = target.get('properties') if isinstance(target, dict) else None
        if not isinstance(properties, dict):
            fail(path, 'facts are needed when the item fields are not written out')
        facts = {block: list(properties)}
    if not isinstance(facts, dict):
        fail(path + '/facts', 'expected fact types and their fields')
    entries = []
    for key, fields in facts.items():
        match = re.fullmatch(r'\s*([^\s()]+)\s*(?:\(\s*([a-z_]+)\s*\))?\s*', str(key))
        if match is None or match.group(2) not in (None, *RELATIONS):
            fail(path + '/facts', 'expected "type" or "type (relation)": ' + str(key))
        relation = match.group(2)
        if relation and not items:
            fail(path + '/facts', 'a linked part needs a block of items')
        if not isinstance(fields, list) or not fields:
            fail(path + '/facts/' + str(key), 'expected the fields this fact type records')
        for spec in fields:
            if not isinstance(spec, str) or not spec:
                fail(path + '/facts/' + str(key), 'expected path or path=field')
            relative, _, field = spec.partition('=')
            segments = relative.strip('/').split('/')
            field = field or segments[-1]
            if field == '*' or not all(segments):
                fail(path + '/facts/' + str(key), 'name the fact field of ' + spec + ' with =field')
            entries.append((qualified(match.group(1), path + '/facts'), relation, root + '/' + '/'.join(segments), field))
    linked = any(relation for _type, relation, _pointer, _field in entries)
    bindings = []
    for semantic_type, relation, pointer, field in entries:
        binding = {'pointer': pointer, 'semantic_type': semantic_type, 'field': field,
            'relation': {'kind': relation, 'subject_pointer': root} if relation else None}
        if linked:
            binding['item_pointer'] = pointer.rsplit('/', 1)[0] if relation else root
        bindings.append(binding)
    return bindings


def standard_checks(block, review, extra, path):
    if not isinstance(review, list) or not all(isinstance(line, str) for line in review):
        fail(path + '/review', 'expected review instructions')
    if not isinstance(extra, dict):
        fail(path + '/checks', 'expected kind: instruction pairs or the full list of checks')
    checks = [{'id': block + '-evidence', 'kind': 'evidence_identity', 'version': 1, 'parameters': {'fields': [], 'instructions': []}},
        {'id': block + '-support', 'kind': 'semantic_support', 'version': 1,
            'parameters': {'fields': [], 'instructions': [*review, STANDARD_SUPPORT]}}]
    for kind, spec in extra.items():
        fields, instructions = [], spec
        if isinstance(spec, dict):
            fields, instructions = spec.get('fields', []), spec.get('instructions', [])
        if isinstance(instructions, str):
            instructions = [instructions]
        checks.append({'id': block + '-' + str(kind), 'kind': kind, 'version': 1,
            'parameters': {'fields': fields, 'instructions': instructions}})
    return checks


def expand_condition(value, path):
    if value is None or isinstance(value, dict):
        return value
    if not isinstance(value, str) or '=' not in value:
        fail(path, 'expected "operation = value"')
    operation, _, equals = value.partition('=')
    return {'operation': operation.strip(), 'equals': equals.strip()}


def expand_view(view, schema, path):
    if not isinstance(view, dict):
        fail(path, 'expected a view')
    return {'mode': 'items' if 'array' in schema_types(schema) else 'object', 'heading': 'plain', 'title': {},
        'inset': 0, 'item_gap': 0, **view}


def expand_block(item, definitions, path):
    if not isinstance(item, dict):
        fail(path, 'expected a block')
    unknown = set(item) - BLOCK_KEYS
    if unknown:
        fail(path, 'unknown block keys: ' + ', '.join(sorted(map(str, unknown))))
    block = need(item, 'id', path)
    schema = expand_schema(item['schema'], definitions, path + '/schema') if 'schema' in item else need(item, 'content_schema', path)
    rewrite = item.get('rewrite', {})
    if not isinstance(rewrite, dict):
        fail(path + '/rewrite', 'expected fields and instructions')
    result = {'id': block}
    if 'effort' in item:
        result['effort'] = item['effort']
    result.update({'mode': item.get('mode', 'model'),
        'selectors': expand_inputs(item.get('selectors', ['source:all']), path + '/selectors'),
        'content_schema': schema,
        'bindings': item['bindings'] if 'bindings' in item else expand_facts(item.get('facts'), schema, block, path),
        'extract': item.get('extract', []),
        'rewrite': {'fields': rewrite.get('fields', []), 'instructions': rewrite.get('instructions', [])},
        'checks': item['checks'] if isinstance(item.get('checks'), list) else standard_checks(block, item.get('review', []),
            item.get('checks', {}), path),
        'depends_on': item.get('depends_on', []), 'operation': item.get('operation'),
        'when': expand_condition(item.get('when'), path + '/when'),
        'placement': item['placement'] if 'placement' in item else {'region': need(item, 'region', path),
            'order': need(item, 'order', path)},
        'view': expand_view(need(item, 'view', path), schema, path + '/view')})
    return result


def expand_relation(value, path):
    if isinstance(value, dict):
        return value
    match = re.fullmatch(r'\s*([a-z_]+)\s+(.+)', value) if isinstance(value, str) else None
    if match is None or match.group(1) not in RELATIONS:
        fail(path, 'expected "relation target"')
    return {'kind': match.group(1), 'target_types': [qualified(name, path) for name in match.group(2).split(',')]}


def expand_builtin_field(value, path):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        fail(path, 'expected field or "field @period"')
    field, _, period = value.partition('@')
    return {'field': field.strip(), 'period': period.strip() or None}


def expand_fact_type(item, definitions, path):
    if not isinstance(item, dict):
        fail(path, 'expected a fact type')
    unknown = set(item) - FACT_TYPE_KEYS
    if unknown:
        fail(path, 'unknown fact type keys: ' + ', '.join(sorted(map(str, unknown))))
    source = item['fields'] if 'fields' in item else need(item, 'schema', path)
    result = {'id': qualified(need(item, 'id', path), path), 'schema_version': item.get('schema_version', '1'),
        'schema': expand_schema(source, definitions, path + ('/fields' if 'fields' in item else '/schema')),
        'builtin_kind': item.get('builtin', item.get('builtin_kind')),
        'relations': [expand_relation(value, f'{path}/relations/{index}') for index, value in enumerate(item.get('relations', []))]}
    fields = item.get('builtin_fields', {})
    if not isinstance(item.get('relations', []), list) or not isinstance(fields, dict):
        fail(path, 'relations is a list and builtin_fields a mapping')
    if fields:
        result['builtin_fields'] = {key: expand_builtin_field(value, f'{path}/builtin_fields/{key}') for key, value in fields.items()}
    return result


def expand_assets(value, path):
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        fail(path, 'expected id: path pairs')
    result = []
    for identifier, spec in value.items():
        spec = {'path': spec} if isinstance(spec, str) else spec
        if not isinstance(spec, dict) or not isinstance(spec.get('path'), str):
            fail(f'{path}/{identifier}', 'expected a path')
        extension = re.search(r'\.[A-Za-z0-9]+$', spec['path'])
        role, mime, embedding = EXTENSIONS.get(extension.group(0).lower() if extension else '', (None, None, None))
        asset = {'id': identifier, 'path': spec['path'], 'role': spec.get('role', role), 'mime_type': spec.get('mime_type', mime),
            'embedding': spec.get('embedding', embedding)}
        if None in asset.values():
            fail(f'{path}/{identifier}', 'write role, mime_type and embedding for this file type')
        result.append(asset)
    return result


def expand_operation(item, path):
    if not isinstance(item, dict):
        fail(path, 'expected an operation')
    return {**item, 'version': item.get('version', 1), 'depends_on': item.get('depends_on', []),
        'inputs': expand_inputs(need(item, 'inputs', path), path + '/inputs')}


def expand(document):
    """The canonical version 3 definition of a short document; any other document is returned unchanged."""
    if not isinstance(document, dict) or document.get('schema_version') != 4:
        return document
    definitions = document.get('content_definitions', {})
    if not isinstance(definitions, dict):
        fail('/content_definitions', 'expected named field types')
    for key in ('fact_types', 'operations', 'blocks'):
        if not isinstance(document.get(key, []), list):
            fail('/' + key, 'expected a list')
    try:
        return expand_sections(document, definitions)
    except (TypeError, AttributeError, KeyError) as error:
        fail('/', 'invalid short template: ' + str(error))


def expand_sections(document, definitions):
    result = {}
    for key, value in document.items():
        if key == 'schema_version':
            result[key] = 3
        elif key == 'content_definitions':
            result[key] = {name: expand_schema(item, definitions, '/content_definitions/' + name) for name, item in value.items()}
        elif key == 'assets':
            result[key] = expand_assets(value, '/assets')
        elif key == 'fact_types':
            result[key] = [expand_fact_type(item, definitions, f'/fact_types/{index}') for index, item in enumerate(value)]
        elif key == 'operations':
            result[key] = [expand_operation(item, f'/operations/{index}') for index, item in enumerate(value)]
        elif key == 'blocks':
            result[key] = [expand_block(item, definitions, f'/blocks/{index}') for index, item in enumerate(value)]
        else:
            result[key] = value
    return result


def source_schema(definition):
    """Editor hints for both forms: the canonical keys plus every shorthand. The compiler stays the authority."""
    schema = copy.deepcopy(definition)
    defs, properties = schema['$defs'], schema['properties']
    word = {'type': 'string'}
    field_type = {'description': 'A type (text, date, string, boolean, integer, number or a content definition), [type] '
        'for a list, {list: type, maxItems: n}, a mapping of fields with "name?" for an optional object, or a JSON schema.'}
    schema['title'] = 'TemplateSource'
    schema['required'] = ['schema_version', 'template']
    properties['schema_version'] = {'enum': [3, 4], 'description': '4 is the short form; 3 is the full form.'}
    properties['content_definitions'] = {'type': 'object', 'additionalProperties': field_type}
    asset = {key: value for key, value in defs['AssetDeclaration']['properties'].items() if key != 'id'}
    properties['assets'] = {'anyOf': [properties['assets'], {'type': 'object', 'description': 'id: path; role and type '
        'follow the file extension (.ttf font, .png icon, .json/.txt catalog).', 'additionalProperties': {'anyOf': [word,
        {'type': 'object', 'additionalProperties': False, 'required': ['path'], 'properties': asset}]}}]}
    defs['InputRefObject'] = defs['InputRef']
    defs['InputRef'] = {'anyOf': [{**word, 'description': 'A block id, or kind:id such as source:all.'},
        {'$ref': '#/$defs/InputRefObject'}]}
    for value in defs.values():
        if 'inputs' in value.get('properties', {}) and 'kind' in value['properties']:
            value['required'] = [key for key in value['required'] if key not in {'version', 'depends_on'}]
    fact = defs['FactType']['properties']
    defs['FactType'] = {'type': 'object', 'additionalProperties': False, 'required': ['id'], 'properties': {**fact,
        'id': {**word, 'description': 'The fact type name; foldcv: is added when no prefix is written.'},
        'fields': field_type, 'schema': field_type, 'builtin': fact['builtin_kind'],
        'relations': {'type': 'array', 'items': {'anyOf': [{**word, 'description': 'relation target, such as '
            'extension_of projects.'}, {'$ref': '#/$defs/RelationDeclaration'}]}},
        'builtin_fields': {'type': 'object', 'additionalProperties': {'anyOf': [{**word, 'description': 'field, or '
            'field @period'}, {'$ref': '#/$defs/BuiltinFieldBinding'}]}}}}
    block = defs['Block']['properties']
    placement = defs['Placement']['properties']
    defs['Block'] = {'type': 'object', 'additionalProperties': False, 'required': ['id', 'view'], 'properties': {**block,
        'region': placement['region'], 'order': placement['order'], 'schema': field_type,
        'facts': {'type': 'object', 'description': 'Fact type (or "type (relation)") → the fields it records; path=field '
            'when names differ. Without it the item fields record the block\'s own fact type.',
            'additionalProperties': {'type': 'array', 'items': word}},
        'review': {'type': 'array', 'items': word, 'description': 'Extra support review instructions.'},
        'checks': {'anyOf': [block['checks'], {'type': 'object', 'description': 'Check kind → instruction; evidence and '
            'support checks are always added.', 'additionalProperties': {'anyOf': [word, {'type': 'array', 'items': word},
            {'type': 'object'}]}}]},
        'when': {'anyOf': [{**word, 'description': 'operation = value'}, block['when']]}}}
    defs['View']['required'] = ['nodes']
    defs['Rewrite']['required'] = []
    return schema
