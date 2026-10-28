"""Focus rows from the facts panel (D113): add, remove, move and stated years change only the document and the
technology's experience; Undo restores both. Rows without an icon get the first-letter placeholder."""

import json

import pytest

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.template_inverse import inverse_template_mutation, semantic
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.presentation_plan import editor_plan
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.employment_fixtures import TEXT, employment_source, object_schema
from tests.templates.template_runtime_fixtures import EmploymentFixture
from tests.templates.test_template_preparation import response
from tests.templates.test_template_view_adapters import render, scripted, view_package
from tests.templates.test_transactions import authorization

FOCUS = [('Python', '10 months'), ('SQL', None), ('UnknownTool', '7 weeks')]


def technology_package(missing_icon='initial'):
    """The synthetic Focus view bound to the technology builtin, as the Generic template binds it."""
    config = view_package().definition.model_dump(mode='json', by_alias=True)
    focus = next(value for value in config['fact_types'] if value['id'] == 'focus')
    focus.update(builtin_kind='technology', schema=object_schema({'technology': TEXT, 'experience': TEXT}),
        builtin_fields={'technology': {'field': 'display', 'period': None}, 'experience': {'field': 'experience', 'period': None}})
    config['style']['focus']['missing_icon'] = missing_icon
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


async def imported(tmp_path, focus=FOCUS, missing_icon='initial'):
    src, raw = employment_source('F06')
    fixture = EmploymentFixture(tmp_path, captured=technology_package(missing_icon), src=src, original_bytes=raw,
        scripted=scripted(src, focus, [{'name': 'Portfolio', 'url': 'https://example.org'}]), cap=8, fallback=False)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.publication.state == 'saved'
    return fixture.current()


def panel(before, operation, record_id, *, values=None, before_id=None, identifier='focus-edit'):
    capture = {'sessionId': 'session', 'actionId': identifier, 'actionToken': 1, 'dependencies': []}
    command = {'operation': operation, 'recordId': record_id, 'recordKind': 'technology', 'jobId': None, 'periodId': None,
        'values': values or {}, 'factsRevision': before.project.facts.revision, 'documentRevision': before.document_revision,
        'capture': capture}
    if before_id is not None:
        command['beforeRecordId'] = before_id
    return TemplateEditPreparationV1(schemaVersion=1, clientMutationId=identifier, snapshot=response(before).snapshot,
        capture=capture, operations=[{'kind': 'builtin_panel', 'opId': 'panel', 'command': command}])


def applied(before, request):
    result = prepare_edit(response(before), request)
    assert result.mutation is not None
    after = apply_rich_mutation(before, result.mutation)[0]
    assert after == result.preview.workspace
    return after, result


def undone(before, after, result):
    inverse = inverse_template_mutation(before, after, origin_action_id=result.mutation.action_id,
        mutation_id='undo-focus', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(after, inverse, history_authorization=authorization(after, inverse))
    assert semantic(restored.project.document) == semantic(before.project.document)
    assert semantic(restored.project.facts.records) == semantic(before.project.facts.records)
    return restored


def rows(workspace):
    """Focus rows in order as (name, detail lines)."""
    shown = []
    for block in workspace.project.document.blocks():
        if block.type == 'section' and block.presentation.view_key == 'focus':
            lines = [''.join(part.text for part in child.content) for child in block.children]
            shown.append((lines[0], lines[1:]))
    return shown


def headings(workspace):
    return [block for block in workspace.project.document.blocks()
        if block.type == 'heading' and block.presentation.view_key == 'focus']


def technology(workspace, name):
    return next(record for record in workspace.project.facts.records
        if record.kind == 'technology' and record.display.raw_text == name)


@pytest.mark.asyncio
async def test_years_edit_sets_the_stated_experience_and_its_line_and_undoes(tmp_path):
    before = await imported(tmp_path)
    assert rows(before) == [('Python', ['10 months']), ('SQL', []), ('UnknownTool', ['7 weeks'])]
    sql = technology(before, 'SQL')
    after, result = applied(before, panel(before, 'edit', sql.id, values={'experience': '3'}))
    # A bare number is whole years in the template's language; the line is bound to the experience field.
    assert rows(after)[1] == ('SQL', ['3 years'])
    assert technology(after, 'SQL').experience.raw_text == '3 years'
    line = next(block for block in after.project.document.blocks() if block.type == 'section'
        and block.props.record_id == sql.id).children[1]
    assert [(part.type, part.field_key) for part in line.content] == [('fact_field', 'experience')]
    undone(before, after, result)


@pytest.mark.asyncio
async def test_clearing_years_hides_the_line_and_keeps_every_other_row(tmp_path):
    before = await imported(tmp_path)
    python = technology(before, 'Python')
    after, result = applied(before, panel(before, 'edit', python.id, values={'experience': ''}))
    assert rows(after) == [('Python', []), ('SQL', []), ('UnknownTool', ['7 weeks'])]
    assert technology(after, 'Python').experience.raw_text == ''
    undone(before, after, result)
    # The same value again changes nothing.
    assert prepare_edit(response(before), panel(before, 'edit', python.id, values={'experience': '10 months'})).mutation is None


@pytest.mark.asyncio
async def test_removing_rows_keeps_facts_and_the_last_one_takes_the_heading_which_returns_with_an_add(tmp_path):
    before = await imported(tmp_path, focus=[('Python', '10 months')])
    python = technology(before, 'Python')
    after, result = applied(before, panel(before, 'remove_from_focus', python.id))
    assert rows(after) == [] and headings(after) == []
    assert semantic(after.project.facts.records) == semantic(before.project.facts.records)
    undone(before, after, result)
    again, _ = applied(after, panel(after, 'add_to_focus', python.id, identifier='focus-add'))
    assert rows(again) == [('Python', ['10 months'])]
    assert [block.content[0].text for block in headings(again)] == ['FOCUS']
    # The heading comes back before the next view of the region, as the import places it.
    order = [block.presentation.view_key for block in again.project.document.regions[1].blocks]
    assert order.index('focus') < len(order) and order == sorted(order, key=lambda key: key != 'focus')


@pytest.mark.asyncio
async def test_adding_a_technology_appends_its_row_and_refuses_a_duplicate(tmp_path):
    before = await imported(tmp_path)
    removed, _ = applied(before, panel(before, 'remove_from_focus', technology(before, 'SQL').id))
    after, result = applied(removed, panel(removed, 'add_to_focus', technology(before, 'SQL').id, identifier='focus-add'))
    assert rows(after) == [('Python', ['10 months']), ('UnknownTool', ['7 weeks']), ('SQL', [])]
    undone(removed, after, result)
    with pytest.raises(ValueError):
        prepare_edit(response(after), panel(after, 'add_to_focus', technology(before, 'SQL').id, identifier='focus-again'))


@pytest.mark.asyncio
async def test_moving_a_row_reorders_only_focus_and_undoes(tmp_path):
    before = await imported(tmp_path)
    tool, python = technology(before, 'UnknownTool'), technology(before, 'Python')
    after, result = applied(before, panel(before, 'move_focus', tool.id, before_id=python.id))
    assert [name for name, _detail in rows(after)] == ['UnknownTool', 'Python', 'SQL']
    undone(before, after, result)
    last, _ = applied(before, panel(before, 'move_focus', python.id, identifier='focus-last'))
    assert [name for name, _detail in rows(last)] == ['SQL', 'UnknownTool', 'Python']
    assert prepare_edit(response(before), panel(before, 'move_focus', tool.id, identifier='focus-same')).mutation is None


@pytest.mark.asyncio
async def test_a_row_without_an_icon_gets_its_first_letter_in_the_editor_and_docx(tmp_path):
    before = await imported(tmp_path)
    plan = editor_plan(before.project)
    icons = [entry['focus']['icon'] for entry in plan['blocks'].values() if entry.get('focus')]
    # Python has its catalog icon; SQL and UnknownTool have none and get distinct letters.
    assert icons[0] == 'python' and icons[1].startswith('initial-') and icons[2].startswith('initial-') and icons[1] != icons[2]
    assert set(plan['iconFiles']) == set(icons)
    content = render(before, tmp_path)
    from tests.templates.test_captured_docx import parts
    assert len([name for name in parts(content) if name.startswith('word/media/')]) >= 3


@pytest.mark.asyncio
async def test_a_text_only_package_keeps_rows_without_an_icon_as_text(tmp_path):
    before = await imported(tmp_path, missing_icon='text_only')
    icons = [entry['focus']['icon'] for entry in editor_plan(before.project)['blocks'].values() if entry.get('focus')]
    assert icons == ['python', None, None]
