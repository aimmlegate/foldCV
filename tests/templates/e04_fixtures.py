"""E04: two identically worded tasks and a second employer through the real employment admission."""

from packages.resume_core.template_assembly import assemble_template
from packages.resume_core.template_identity import capture_span
from tests.templates.employment_fixtures import employment_package, employment_source
from tests.templates.pipeline_fixtures import source_draft
from tests.templates.test_builtin_admission import accept, proposed_from

TASK = 'Implemented queue processing.'
RESULT = 'Our team reduced median latency from 800 ms to 500 ms.'


def e04_proposal(src):
    unit = src.units[0]
    def span(text, occurrence=0):
        offset = -1
        for _ in range(occurrence + 1):
            offset = unit.text.index(text, offset + 1)
        return capture_span(src, unit, offset, offset + len(text)).model_dump(by_alias=True)
    def claim(value, category, attribution=None):
        return {'value': value, 'classification': {'category': category, 'attribution': attribution}}
    payload = [
        {'company': 'Example Labs', 'role': 'Backend Engineer', 'period': {'raw': '03.2020–11.2023',
            'start': {'raw': '03.2020', 'year': 2020, 'month': 3}, 'end': {'raw': '11.2023', 'year': 2023, 'month': 11},
            'ongoing': False}, 'description': None, 'tasks': [claim(TASK, 'task'), claim(TASK, 'task')],
            'results': [claim(RESULT, 'result', 'team')], 'technologies': [{'display': 'Python'}]},
        {'company': 'Second Works', 'role': 'engineer', 'period': {'raw': '2024–present',
            'start': {'raw': '2024', 'year': 2024, 'month': None}, 'end': None, 'ongoing': True},
            'description': None, 'tasks': [], 'results': [], 'technologies': []}]
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
    for name, pointer, evidence in [('company', '/0/company', [span('Example Labs')]),
            ('role', '/0/role', [span('Backend Engineer', 1)]), ('start', '/0/period/start', [span('03.2020')]),
            ('end', '/0/period/end', [span('11.2023')]), ('present', '/0/period/ongoing', [span('03.2020–11.2023')])]:
        field('job', name, pointer, evidence)
    discover('job-b', 'employment', '/1')
    for name, pointer, evidence in [('company', '/1/company', [span('Second Works')]), ('role', '/1/role', [span('engineer')]),
            ('start', '/1/period/start', [span('2024')]), ('end', '/1/period/end', []), ('present', '/1/period/ongoing', [span('2024–present')])]:
        field('job-b', name, pointer, evidence)
    for key, root, text, occurrence, attributed in [('task-1', '/0/tasks/0', TASK, 0, False),
            ('task-2', '/0/tasks/1', TASK, 1, False), ('result', '/0/results/0', RESULT, 0, True)]:
        evidence = [span(text, occurrence)]
        discover(key, 'claim', root)
        field(key, 'value', root + '/value', evidence)
        relation('owner-' + key, 'owned_by', key, 'job', evidence)
        discover(key + '-classification', 'claim-classification', root + '/classification')
        field(key + '-classification', 'category', root + '/classification/category', evidence)
        field(key + '-classification', 'attribution', root + '/classification/attribution', evidence if attributed else [])
        relation('class-' + key, 'extension_of', key + '-classification', key, evidence)
    discover('technology', 'technology', '/0/technologies/0')
    field('technology', 'display', '/0/technologies/0/display', [span('Python')])
    relation('technology-owner', 'owned_by', 'technology', 'job', [span('Python')])
    return {'schemaVersion': 1, 'payload': payload, 'discoveries': discoveries, 'fields': fields,
        'lineage': [{'kind': 'add', 'parents': [], 'children': [value['key'] for value in discoveries]}], 'relations': relations}


def e04_workspace():
    package = employment_package()
    src, raw = employment_source('F09')
    operation, facts, proposed, _package, _src = proposed_from(package, src, e04_proposal(src))
    operation, facts = accept(operation, facts, proposed, package, src)
    return assemble_template(source_draft(operation, facts, captured=package, src=src), operation), {src.id: raw}
