"""V02: F07 long project wording as one employment with 250 tasks through the real admission and assembly."""

from packages.resume_core.template_assembly import assemble_template
from packages.resume_core.template_identity import capture_span
from tests.templates.employment_fixtures import employment_package, employment_source
from tests.templates.pipeline_fixtures import source_draft
from tests.templates.test_builtin_admission import accept, proposed_from

ROLE = 'Principal Backend and Distributed Systems Engineer with a Long Source Title'


def long_lines(src):
    return [line for line in src.units[0].text.splitlines() if line.startswith('PROJECT-MARKER-')]


def long_proposal(src):
    unit = src.units[0]
    def span(text):
        offset = unit.text.index(text)
        return capture_span(src, unit, offset, offset + len(text)).model_dump(by_alias=True)
    tasks = long_lines(src)
    payload = [{'company': None, 'role': ROLE, 'period': {'raw': None, 'start': None, 'end': None, 'ongoing': None},
        'description': None, 'tasks': [{'value': text, 'classification': {'category': 'task', 'attribution': None}} for text in tasks],
        'results': [], 'technologies': []}]
    discoveries, fields, relations = [{'key': 'job', 'semanticType': 'employment', 'pointer': '/0'}], [], []
    def field(key, name, pointer, evidence):
        fields.append({'item': {'kind': 'discovery_key', 'key': key}, 'fieldKey': name, 'pointer': pointer,
            'evidence': evidence, 'effectiveCellIds': []})
    for name, pointer in [('company', '/0/company'), ('start', '/0/period/start'), ('end', '/0/period/end'), ('present', '/0/period/ongoing')]:
        field('job', name, pointer, [])
    field('job', 'role', '/0/role', [span(ROLE)])
    for index, text in enumerate(tasks):
        key, root, evidence = f'task-{index}', f'/0/tasks/{index}', [span(text)]
        discoveries += [{'key': key, 'semanticType': 'claim', 'pointer': root},
            {'key': key + '-classification', 'semanticType': 'claim-classification', 'pointer': root + '/classification'}]
        field(key, 'value', root + '/value', evidence)
        field(key + '-classification', 'category', root + '/classification/category', evidence)
        field(key + '-classification', 'attribution', root + '/classification/attribution', [])
        relations += [{'relation': {'kind': 'discovery_key', 'key': 'owner-' + key}, 'kind': 'owned_by',
            'subject': {'kind': 'discovery_key', 'key': key}, 'target': {'kind': 'discovery_key', 'key': 'job'}, 'evidence': evidence},
            {'relation': {'kind': 'discovery_key', 'key': 'class-' + key}, 'kind': 'extension_of',
            'subject': {'kind': 'discovery_key', 'key': key + '-classification'}, 'target': {'kind': 'discovery_key', 'key': key},
            'evidence': evidence}]
    return {'schemaVersion': 1, 'payload': payload, 'discoveries': discoveries, 'fields': fields,
        'lineage': [{'kind': 'add', 'parents': [], 'children': [value['key'] for value in discoveries]}], 'relations': relations}


def long_workspace():
    package = employment_package()
    src, raw = employment_source('F07')
    operation, facts, proposed, _package, _src = proposed_from(package, src, long_proposal(src))
    operation, facts = accept(operation, facts, proposed, package, src)
    return assemble_template(source_draft(operation, facts, captured=package, src=src), operation), {src.id: raw}
