"""Rewrite a template in the short authoring form (schema_version 4).

Every part is shortened only when it expands back to exactly the same canonical definition, so the compiled package
keeps its hash. Usage: shorten_template.py <template.yaml> [output.yaml]
"""

from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.templates.loading import load_declared_definition
from packages.resume_core.templates.models import TemplateDefinition
from packages.resume_core.templates import shorthand as short

HEADER = '# yaml-language-server: $schema=../../contracts/template-source.schema.json\n'
# People edit the first sections; the rest is folded in the Settings editor.
ORDER = ('schema_version', 'template', 'model', 'blocks', 'style', 'layout', 'source', 'content_definitions',
    'fact_types', 'operations', 'assets', 'provenance')


def same(left, right):
    return canonical(left) == canonical(right)


def schema(value, definitions):
    """The short field type of a JSON schema, or the schema itself."""
    def attempt():
        if not isinstance(value, dict):
            return value
        if set(value) == {'$ref'} and value['$ref'].startswith('#/$defs/'):
            return value['$ref'].removeprefix('#/$defs/')
        if value == {'type': 'string', 'minLength': 1}:
            return 'string'
        if set(value) == {'type'} and value['type'] in short.SCALARS:
            return value['type']
        if value.get('type') == 'array' and 'items' in value:
            rest = {key: item for key, item in value.items() if key not in {'type', 'items'}}
            item = schema(value['items'], definitions)
            return {'list': item, **rest} if rest else [item]
        if (value.get('type') == 'object' and set(value) == {'type', 'additionalProperties', 'required', 'properties'}
                and value['additionalProperties'] is False and value['properties']
                and value['required'] == list(value['properties'])):
            return dict(field(child, name, definitions) for name, child in value['properties'].items())
        return value
    result = attempt()
    try:
        if same(short.expand_schema(result, definitions, ''), value):
            return result
    except short.SchemaFailure:
        pass
    return value


def field(value, name, definitions):
    """A property as a (key, short type) pair; `name?` when only null is added to an object or plain type."""
    kind = value.get('type') if isinstance(value, dict) else None
    if isinstance(kind, list) and len(kind) == 2 and kind[1] == 'null' and kind[0] in {'object', *short.SCALARS}:
        plain = {**value, 'type': kind[0]}
        result = schema(plain, definitions)
        if result is not plain and not (isinstance(result, dict) and short.SCHEMA_KEYS & result.keys()):
            return name + '?', result
    return name, schema(value, definitions)


def local(name):
    return name.removeprefix('foldcv:')


def inputs(values):
    result = []
    for value in values:
        if value['kind'] == 'block' and ':' not in value['id']:
            result.append(value['id'])
        else:
            result.append(value['kind'] + ':' + value['id'])
    return result


def fact_type(item, definitions):
    result = {'id': local(item['id'])}
    if item['schema_version'] != '1':
        result['schema_version'] = item['schema_version']
    fields = (schema(item['schema'], definitions))
    result['fields' if isinstance(fields, dict) and not short.SCHEMA_KEYS & fields.keys() else 'schema'] = fields
    if item.get('builtin_kind') is not None:
        result['builtin'] = item['builtin_kind']
    if item.get('relations'):
        result['relations'] = [relation['kind'] + ' ' + ', '.join(map(local, relation['target_types']))
            for relation in item['relations']]
    if item.get('builtin_fields'):
        result['builtin_fields'] = {key: value['field'] + (' @' + value['period'] if value.get('period') else '')
            for key, value in item['builtin_fields'].items()}
    return result


def facts(block, content):
    bindings = block['bindings']
    items = 'array' in short.schema_types(content)
    root = '/*' if items else ''
    try:
        if same(short.expand_facts(None, content, block['id'], ''), bindings):
            return None
    except short.SchemaFailure:
        pass
    groups = {}
    for binding in bindings:
        relation = binding['relation']['kind'] if binding.get('relation') else None
        key = local(binding['semantic_type']) + (f' ({relation})' if relation else '')
        path = binding['pointer'].removeprefix(root + '/')
        if path.rsplit('/', 1)[-1] != binding['field']:
            path += '=' + binding['field']
        groups.setdefault(key, []).append(path)
    try:
        if same(short.expand_facts(groups, content, block['id'], ''), bindings):
            return groups
    except short.SchemaFailure:
        pass
    return False


def checks(block):
    values = block['checks']
    if len(values) >= 2:
        evidence, support, *extra = values
        lines = support['parameters']['instructions']
        review = lines[:-1] if lines and lines[-1] == short.STANDARD_SUPPORT else None
        mapping = {}
        for check in extra:
            parameters = check['parameters']
            value = parameters['instructions'][0] if len(parameters['instructions']) == 1 else parameters['instructions']
            mapping[check['kind']] = {'fields': parameters['fields'], 'instructions': parameters['instructions']} \
                if parameters['fields'] else value
        if review is not None:
            try:
                if same(short.standard_checks(block['id'], review, mapping, ''), values):
                    return review, mapping
            except short.SchemaFailure:
                pass
    return None, values


def view(block, content):
    value = dict(block['view'])
    defaults = {'mode': 'items' if 'array' in short.schema_types(content) else 'object', 'heading': 'plain', 'title': {},
        'inset': 0, 'item_gap': 0}
    for key, default in defaults.items():
        if key in value and value[key] == default:
            del value[key]
    ordered = {key: value.pop(key) for key in ('mode', 'heading', 'title', 'inset', 'item_gap') if key in value}
    return {**ordered, **value}


def block(item, definitions):
    content = item['content_schema']
    result = {'id': item['id'], 'region': item['placement']['region'], 'order': item['placement']['order']}
    if item['mode'] != 'model':
        result['mode'] = item['mode']
    if item.get('effort') is not None:
        result['effort'] = item['effort']
    if item['when'] is not None:
        result['when'] = item['when']['operation'] + ' = ' + item['when']['equals']
    if item['depends_on']:
        result['depends_on'] = item['depends_on']
    if item['operation'] is not None:
        result['operation'] = item['operation']
    selectors = inputs(item['selectors'])
    if selectors != ['source:all']:
        result['selectors'] = selectors
    result['schema'] = (schema(content, definitions))
    bound = facts(item, content)
    if bound is False:
        result['bindings'] = item['bindings']
    elif bound is not None:
        result['facts'] = bound
    if item['extract']:
        result['extract'] = item['extract']
    rewrite = {key: value for key, value in item['rewrite'].items() if value}
    if rewrite:
        result['rewrite'] = rewrite
    review, extra = checks(item)
    if review:
        result['review'] = review
    if extra:
        result['checks'] = extra
    result['view'] = view(item, content)
    return result


def asset(item):
    extension = Path(item['path']).suffix.lower()
    role, mime, embedding = short.EXTENSIONS.get(extension, (None, None, None))
    rest = {key: item[key] for key, inferred in (('role', role), ('mime_type', mime), ('embedding', embedding))
        if item[key] != inferred}
    return {'path': item['path'], **rest} if rest else item['path']


def operation(item):
    result = {key: value for key, value in item.items() if key not in {'version', 'depends_on', 'inputs'}}
    if item['version'] != 1:
        result['version'] = item['version']
    result['inputs'] = inputs(item['inputs'])
    if item['depends_on']:
        result['depends_on'] = item['depends_on']
    return result


def shorten(document):
    definitions = document['content_definitions']
    result = {'schema_version': 4}
    for key, value in document.items():
        if key == 'schema_version':
            continue
        if key == 'content_definitions':
            result[key] = {name: (schema(item, definitions)) for name, item in value.items()}
        elif key == 'fact_types':
            result[key] = [fact_type(item, definitions) for item in value]
        elif key == 'blocks':
            result[key] = [block(item, definitions) for item in value]
        elif key == 'assets':
            result[key] = {item['id']: asset(item) for item in value}
        elif key == 'operations':
            result[key] = [operation(item) for item in value]
        else:
            result[key] = value
    return {key: result[key] for key in sorted(result, key=lambda key: ORDER.index(key) if key in ORDER else len(ORDER))}


class Dumper(yaml.SafeDumper):
    pass


def represent_list(dumper, value):
    # Short lists of plain words read best on one line: [text], [source:all].
    flow = len(value) <= 4 and all(isinstance(item, (str, int)) and len(str(item)) <= 24 and ' ' not in str(item)
        for item in value)
    return dumper.represent_sequence('tag:yaml.org,2002:seq', value, flow_style=flow)


Dumper.add_representer(list, represent_list)


def main():
    source = Path(sys.argv[1])
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else source
    raw = source.read_bytes()
    document = load_declared_definition(raw, 'yaml')
    expected = TemplateDefinition.model_validate(document)
    result = shorten(document)
    text = HEADER + yaml.dump(result, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=118)
    actual = TemplateDefinition.model_validate(load_declared_definition(text.encode(), 'yaml'))
    if not same(actual, expected):
        raise SystemExit('the short form does not expand to the same definition')
    target.write_text(text, encoding='utf-8')
    print(f'{len(raw.splitlines())} -> {len(text.splitlines())} lines')


if __name__ == '__main__':
    main()
