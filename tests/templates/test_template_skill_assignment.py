"""Skill assignment shows each canonical technology once among the active groups, old-project technologies included."""

import json
from types import SimpleNamespace

import pytest

from packages.resume_core.template_identity import capture_span
from packages.resume_core.template_import import spent_calls
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.models import SkillsOperation
from packages.resume_core.templates.operations import OperationContext, assign_skills, derive_task, runnable
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.employment_fixtures import TEXT, employment_package, employment_source, object_schema
from tests.templates.template_runtime_fixtures import EmploymentFixture
from tests.templates.test_template_operations import history_proposal
from tests.templates.test_template_role_branch import FAMILY, branch


EXPECTED = json.loads(open('tests/fixtures/synthetic/templates/expected.json').read())
GROUPS = {'tech-a': ('technical', 'A: '), 'tech-b': ('technical', 'B: '), 'role-tools': ('skills_and_tools', 'T: ')}


def technology(identifier, display, canonical=None):
    return SimpleNamespace(id=identifier, kind='technology', active=True, display=SimpleNamespace(raw_text=display),
        canonical_id=SimpleNamespace(value=canonical))


def skills(identifier='technical-skills', groups=('tech-a', 'tech-b'), uncertain='tech-b'):
    return SkillsOperation.model_validate({'id': identifier, 'kind': 'assign_skills', 'version': 1,
        'inputs': [{'kind': 'block', 'id': block} for block in ['employment-view', *groups]], 'depends_on': ['role-branch'],
        'parameters': {'groups': list(groups), 'uncertain_group': uncertain}})


def context(branch_value, records, producers):
    blocks = {name: SimpleNamespace(id=name, when=SimpleNamespace(operation='role-branch', equals=equals))
        for name, (equals, _prefix) in GROUPS.items()}
    return OperationContext(None, SimpleNamespace(records=records), handles={record.id: 'item-' + record.id for record in records},
        producers=producers, cells={record.id: ('cell-' + record.id,) for record in records},
        results={'role-branch': {'branch': branch_value}}, blocks=blocks)


def test_first_active_group_keeps_a_canonical_technology_and_unassigned_project_ones_join_the_fallback_group():
    records = [technology('a-python', 'Python'), technology('b-python', 'Python 3.12'), technology('b-tool', 'UnknownTool'),
        technology('b-tool-2', ' unknowntool '), technology('job-perl', 'Perl'), technology('job-python', 'python'),
        technology('job-perl-2', 'PERL'), technology('elsewhere', 'Go')]
    producers = {'a-python': 'tech-a', 'b-python': 'tech-b', 'b-tool': 'tech-b', 'b-tool-2': 'tech-b',
        'job-perl': 'employment-view', 'job-python': 'employment-view', 'job-perl-2': 'employment-view', 'elsewhere': 'summary'}
    result = assign_skills(skills(), context('technical', records, producers))
    assert result.value == {'active': ['tech-a', 'tech-b'], 'kept': {'tech-a': ['a-python'], 'tech-b': ['b-tool']},
        'hidden': {'tech-a': [], 'tech-b': ['b-python', 'b-tool-2']}, 'added': ['job-perl'], 'uncertainGroup': 'tech-b'}
    assert [(issue.code, issue.target_ids) for issue in result.issues] == [('IMPORT_SKILL_GROUP_UNCERTAIN', ('cell-job-perl',))]
    assert result.item_handles == ('item-a-python', 'item-b-tool', 'item-job-perl')


def test_an_assignment_for_the_other_branch_shows_nothing_and_reports_nothing():
    records = [technology('job-perl', 'Perl')]
    result = assign_skills(skills(), context('skills_and_tools', records, {'job-perl': 'employment-view'}))
    assert result.value['active'] == [] and result.value['added'] == [] and result.issues == ()


def skill_package(*, operations=None):
    config = employment_package().definition.model_dump(mode='json', by_alias=True)
    config['template'].update(id='synthetic-skill-groups', name='Skill groups')
    config['fact_types'] += [{'id': identifier, 'schema_version': '1', 'schema': schema, 'builtin_kind': None, 'relations': []}
        for identifier, schema in [('role', object_schema({'title': TEXT})), ('role-family', object_schema({'family': FAMILY}))]]
    def block(identifier, order, content, bindings, view, when=None):
        return {'id': identifier, 'mode': 'model', 'selectors': [{'kind': 'source', 'id': 'all'}], 'content_schema': content,
            'bindings': bindings, 'extract': [], 'rewrite': {'fields': [], 'instructions': []}, 'checks': [], 'depends_on': [],
            'operation': None, 'when': when, 'placement': {'region': 'main', 'order': order}, 'view': view}
    config['blocks'].append(block('role-view', 2, object_schema({'title': TEXT, 'role': object_schema({'family': FAMILY})}),
        [{'pointer': '/title', 'semantic_type': 'role', 'field': 'title', 'relation': None},
            {'pointer': '/role/family', 'semantic_type': 'role-family', 'field': 'family', 'relation': None}],
        {'mode': 'object', 'heading': 'none', 'title': {}, 'inset': 0, 'item_gap': 6,
            'nodes': [{'type': 'text', 'style': 'body', 'field': '/title'}]}))
    for order, (name, (equals, prefix)) in enumerate(GROUPS.items(), 3):
        config['blocks'].append(block(name, order, {'type': 'array', 'items': object_schema({'display': TEXT})},
            [{'pointer': '/*/display', 'semantic_type': 'technology', 'field': 'display', 'item_pointer': '/*', 'relation': None}],
            {'mode': 'items', 'heading': 'none', 'title': {}, 'inset': 0, 'item_gap': 6,
                'nodes': [{'type': 'text', 'style': 'body', 'field': '/display', 'prefix': {'en': prefix}}]},
            {'operation': 'role-branch', 'equals': equals}))
    role = branch().model_dump(mode='json', by_alias=True)
    role['parameters']['classification']['semantic_type'] = 'role-family'
    # A declared period format keeps the ongoing job structured, so no source fallback hides cells citing its line.
    periods = {'id': 'source-periods', 'kind': 'format_period', 'version': 1, 'inputs': [{'kind': 'source', 'id': 'all'}],
        'depends_on': [], 'parameters': {'separator': ' – ', 'ongoing_label': {'en': 'present'}}}
    config['operations'] = [role, periods, *(operations or [skills().model_dump(mode='json', by_alias=True),
        skills('role-skills', ('role-tools',), 'role-tools').model_dump(mode='json', by_alias=True)])]
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def test_assignment_runs_only_with_input_groups_one_condition_one_active_assignment_and_a_display_binding():
    definition = skill_package().definition
    assert all(runnable(value, definition) for value in definition.operations)
    def changed(update):
        value = skills().model_dump(mode='json', by_alias=True)
        update(value)
        return SkillsOperation.model_validate(value)
    assert not runnable(changed(lambda value: value.update(inputs=[{'kind': 'block', 'id': 'employment-view'}])), definition)
    assert not runnable(changed(lambda value: value['parameters'].update(groups=['tech-a', 'role-tools'])), definition)
    assert not runnable(skills('second-technical'), definition)
    assert not runnable(skills('second', ('role-view',), 'role-view'), definition)


def scripted(src, family, groups):
    def span(text):
        unit = src.units[0]
        offset = unit.text.index(text)
        return capture_span(src, unit, offset, offset + len(text)).model_dump(by_alias=True)
    def script(_request, value):
        if 'targets' in value:
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
                'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}
        block = value['declaration']['id']
        if block == 'employment-view':
            return history_proposal(src)
        if block == 'role-view':
            return {'schemaVersion': 1, 'payload': {'title': 'engineer', 'role': {'family': family}},
                'discoveries': [{'key': 'role', 'semanticType': 'role', 'pointer': ''},
                    {'key': 'family', 'semanticType': 'role-family', 'pointer': '/role'}],
                'fields': [{'item': {'kind': 'discovery_key', 'key': 'role'}, 'fieldKey': 'title', 'pointer': '/title',
                    'evidence': [span('engineer')], 'effectiveCellIds': []},
                    {'item': {'kind': 'discovery_key', 'key': 'family'}, 'fieldKey': 'family', 'pointer': '/role/family',
                        'evidence': [span('engineer')], 'effectiveCellIds': []}],
                'lineage': [{'kind': 'add', 'parents': [], 'children': ['role', 'family']}], 'relations': []}
        names = groups[block]
        return {'schemaVersion': 1, 'payload': [{'display': name} for name in names],
            'discoveries': [{'key': 'tech-' + str(index), 'semanticType': 'technology', 'pointer': '/' + str(index)}
                for index in range(len(names))],
            'fields': [{'item': {'kind': 'discovery_key', 'key': 'tech-' + str(index)}, 'fieldKey': 'display',
                'pointer': '/' + str(index) + '/display', 'evidence': [span(name)], 'effectiveCellIds': []}
                for index, name in enumerate(names)],
            'lineage': [{'kind': 'add', 'parents': [], 'children': ['tech-' + str(index) for index in range(len(names))]}],
            'relations': []}
    return script


@pytest.mark.asyncio
@pytest.mark.parametrize(('family', 'groups', 'shown'), [
    ('other', {'tech-a': ['Python'], 'tech-b': ['Python']}, {'A: Python', 'B: Perl'}),
    ('business_analyst', {'role-tools': ['Python']}, {'T: Python', 'T: Perl'})])
async def test_each_known_technology_appears_once_among_the_active_groups(tmp_path, family, groups, shown):
    src, raw = employment_source('F04')
    fixture = EmploymentFixture(tmp_path, captured=skill_package(), src=src, original_bytes=raw, cap=8, fallback=False)
    fixture.pipeline.derive = derive_task
    fixture.transport.scripted = scripted(src, family, groups)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.publication.state == 'saved' and spent_calls(result) == 2 * (2 + len(groups))
    states = {task.block_id: task.state for task in result.tasks}
    assert {block for block in GROUPS if states[block] == 'accepted'} == set(groups)
    assert {block for block in GROUPS if states[block] == 'empty'} == set(GROUPS) - set(groups)
    texts = [''.join(part.text for part in block.content) for block in fixture.current().project.document.blocks()]
    grouped = [text for text in texts if text[:3] in {prefix for _equals, prefix in GROUPS.values()}]
    assert sorted(grouped) == sorted(shown) and sorted(text[3:] for text in grouped) == EXPECTED['F04']['allSkills']
    project = fixture.current().project
    assert [issue.code for issue in project.import_issues] == ['IMPORT_SKILL_GROUP_UNCERTAIN'] and project.import_issues[0].block_ids
    # Replaying every deterministic task from the durable import gives its stored result.
    stored = project.template_operations[-1]
    for task in stored.tasks:
        if task.kind == 'derive':
            assert derive_task(stored, task, project).value == next(value.value for value in stored.task_results if value.task_id == task.id)
