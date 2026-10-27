"""The role branch reads one admitted role-family classification; a block for the other branch makes no model call."""

import json
from types import SimpleNamespace

import pytest

from packages.resume_core.template_identity import capture_span
from packages.resume_core.template_import import spent_calls
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.loading import load_definition
from packages.resume_core.templates.models import RoleOperation
from packages.resume_core.templates.operations import OperationContext, derive_task, select_role_branch
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.employment_fixtures import TEXT, employment_source, object_schema
from tests.templates.template_runtime_fixtures import EmploymentFixture


FAMILY = {'type': ['string', 'null'], 'enum': ['business_analyst', 'tester', 'other', None]}
NOTES = {'technical-view': 'Python — 10 months', 'analyst-view': 'SQL — about 2.5 years'}


def branch(classification=True):
    parameters = {'role_families': ['business_analyst', 'tester'], 'matched': 'skills_and_tools', 'otherwise': 'technical'}
    if classification:
        parameters['classification'] = {'semantic_type': 'role-family', 'field': 'family'}
    return RoleOperation.model_validate({'id': 'role-branch', 'kind': 'select_role_branch', 'version': 1,
        'inputs': [{'kind': 'block', 'id': 'role-view'}], 'depends_on': [], 'parameters': parameters})


def classified(*values, state='admitted'):
    return SimpleNamespace(extensions=[SimpleNamespace(id='record-' + str(index), item_handle='item-' + str(index), active=True,
        semantic_type='role-family', cells=[SimpleNamespace(id='cell-' + str(index), field_key='family', state=state,
            typed_value=value, evidence=['span-' + str(index)])]) for index, value in enumerate(values)])


@pytest.mark.parametrize(('values', 'selected', 'issue'), [
    (['business_analyst'], 'skills_and_tools', False), (['tester', 'tester'], 'skills_and_tools', False),
    (['other'], 'technical', False), ([], 'technical', True), (['tester', 'other'], 'technical', True)])
def test_branch_follows_one_admitted_family_and_reports_missing_or_conflicting_ones(values, selected, issue):
    result = select_role_branch(branch(), OperationContext(None, classified(*values)))
    assert result.value['branch'] == selected
    assert [value.code for value in result.issues] == (['IMPORT_ROLE_FAMILY_UNCERTAIN'] if issue else [])
    if issue and values:
        # A conflict names the competing cells; a missing value has no cell to name.
        assert result.issues[0].target_ids == ('cell-0', 'cell-1')
    assert result.source_spans == tuple('span-' + str(index) for index in range(len(values)))


def test_raw_human_text_or_an_undeclared_classification_never_selects_the_matched_branch():
    raw = select_role_branch(branch(), OperationContext(None, classified(None, state='human_raw')))
    assert raw.value == {'branch': 'technical', 'family': None} and len(raw.issues) == 1
    retained = select_role_branch(branch(classification=False), OperationContext(None, classified('business_analyst')))
    assert retained.value['branch'] == 'technical' and len(retained.issues) == 1
    assert 'classification' not in branch(classification=False).model_dump(mode='json', by_alias=True)['parameters']


def generic(change):
    config = load_definition(BUNDLED_TEMPLATE.read_bytes())
    change(config)
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def role_operation(config):
    return next(value for value in config['operations'] if value['id'] == 'role-branch')


@pytest.mark.parametrize(('change', 'reason'), [
    (lambda config: role_operation(config)['parameters']['role_families'].append('architect'), 'enumerate every role family'),
    (lambda config: role_operation(config).update(inputs=[{'kind': 'block', 'id': 'summary'}]), 'input block that binds it'),
    (lambda config: role_operation(config)['parameters']['classification'].update(semantic_type='foldcv:unknown'), 'unknown reference')])
def test_compiler_requires_a_bound_classification_that_names_every_family(change, reason):
    assert generic(lambda _config: None).definition.operations[1].parameters.classification.field == 'family'
    with pytest.raises(SchemaFailure, match=reason):
        generic(change)


def role_package():
    config = load_definition(BUNDLED_TEMPLATE.read_bytes())
    config['template'] = {'id': 'synthetic-role-branch', 'revision': '1', 'name': 'Role branch', 'default_locale': 'en'}
    config['content_definitions'] = {}
    config['fact_types'] = [{'id': identifier, 'schema_version': '1', 'schema': schema, 'builtin_kind': None, 'relations': []}
        for identifier, schema in [('role', object_schema({'title': TEXT})), ('role-family', object_schema({'family': FAMILY})),
            ('note', object_schema({'note': TEXT}))]]
    def block(identifier, order, properties, bindings, when):
        return {'id': identifier, 'mode': 'model', 'selectors': [{'kind': 'source', 'id': 'all'}],
            'content_schema': object_schema(properties), 'bindings': [{'pointer': '/' + pointer, 'semantic_type': semantic,
                'field': pointer.split('/')[-1], 'relation': None} for semantic, pointer in bindings],
            'extract': [], 'rewrite': {'fields': [], 'instructions': []}, 'checks': [], 'depends_on': [], 'operation': None,
            'when': when, 'placement': {'region': 'main', 'order': order},
            'view': {'mode': 'object', 'heading': 'none', 'title': {}, 'inset': 0, 'item_gap': 6,
                'nodes': [{'type': 'text', 'style': 'body', 'field': '/' + bindings[0][1]}]}}
    config['blocks'] = [block('role-view', 1, {'title': TEXT, 'role': object_schema({'family': FAMILY})},
            [('role', 'title'), ('role-family', 'role/family')], None),
        block('technical-view', 2, {'note': TEXT}, [('note', 'note')], {'operation': 'role-branch', 'equals': 'technical'}),
        block('analyst-view', 3, {'note': TEXT}, [('note', 'note')], {'operation': 'role-branch', 'equals': 'skills_and_tools'})]
    config['operations'] = [branch().model_dump(mode='json', by_alias=True)]
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def scripted(src, family):
    def span(text):
        unit = src.units[0]
        offset = unit.text.index(text)
        return capture_span(src, unit, offset, offset + len(text)).model_dump(by_alias=True)
    def script(_request, value):
        if 'targets' in value:
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
                'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}
        block = value['declaration']['id']
        if block != 'role-view':
            return {'schemaVersion': 1, 'payload': {'note': NOTES[block]},
                'discoveries': [{'key': 'note', 'semanticType': 'note', 'pointer': ''}],
                'fields': [{'item': {'kind': 'discovery_key', 'key': 'note'}, 'fieldKey': 'note', 'pointer': '/note',
                    'evidence': [span(NOTES[block])], 'effectiveCellIds': []}],
                'lineage': [{'kind': 'add', 'parents': [], 'children': ['note']}], 'relations': []}
        # The family is its own item, so it has its own root inside the payload.
        return {'schemaVersion': 1, 'payload': {'title': 'Business analyst', 'role': {'family': family}},
            'discoveries': [{'key': 'role', 'semanticType': 'role', 'pointer': ''},
                {'key': 'family', 'semanticType': 'role-family', 'pointer': '/role'}],
            'fields': [{'item': {'kind': 'discovery_key', 'key': key}, 'fieldKey': pointer.split('/')[-1], 'pointer': '/' + pointer,
                'evidence': [span('Business analyst')] if value_ is not None else [], 'effectiveCellIds': []}
                for key, pointer, value_ in [('role', 'title', 'Business analyst'), ('family', 'role/family', family)]],
            'lineage': [{'kind': 'add', 'parents': [], 'children': ['role', 'family']}], 'relations': []}
    return script


@pytest.mark.asyncio
@pytest.mark.parametrize(('family', 'selected', 'skipped'), [
    ('business_analyst', 'analyst-view', 'technical-view'), ('other', 'technical-view', 'analyst-view'),
    (None, 'technical-view', 'analyst-view')])
async def test_only_the_selected_branch_calls_the_model_and_an_unclassified_role_is_an_issue(tmp_path, family, selected, skipped):
    src, raw = employment_source('F06')
    fixture = EmploymentFixture(tmp_path, captured=role_package(), src=src, original_bytes=raw, cap=4, fallback=False)
    fixture.pipeline.derive = derive_task
    fixture.transport.scripted = scripted(src, family)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.publication.state == 'saved' and spent_calls(result) == 4
    assert {value['declaration']['id'] for value in fixture.transport.calls if 'declaration' in value} == {'role-view', selected}
    tasks = {task.block_id: task for task in result.tasks}
    assert {block: task.state for block, task in tasks.items()} == {'role-view': 'accepted', 'role-branch': 'accepted',
        selected: 'accepted', skipped: 'empty'}
    stored = {task.block_id: value for task in result.tasks for value in result.task_results if value.task_id == task.id}
    assert stored['role-branch'].value['family'] == family and stored[skipped].value == {'branch': stored['role-branch'].value['branch']}
    assert stored[skipped].item_handles == [] and not tasks[skipped].attempt_ids
    texts = [''.join(part.text for part in block.content) for block in fixture.current().project.document.blocks()]
    assert NOTES[selected] in texts and NOTES[skipped] not in texts
    issues = fixture.current().project.import_issues
    if family is None:
        assert [(issue.code, issue.category, issue.target_ids) for issue in issues] == [
            ('IMPORT_ROLE_FAMILY_UNCERTAIN', 'uncertain_interpretation', ['scope-' + tasks['role-branch'].id])]
        assert issues[0].block_ids and tasks['role-branch'].issue_ids == [issues[0].id]
    else:
        assert issues == []
