"""Skill groups in the facts panel on the two-column F10 import (D136): each group lists its technologies, a technology
moves between groups or leaves one, and a group of the user's own follows the last group and goes with its last
technology; Undo restores each, and the export shows a new group as the template's own."""

import asyncio
import io
import re
import zipfile

import pytest
from pydantic import ValidationError

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.fields import field_key
from packages.resume_core.editing.panel import RichPanelRequest
from packages.resume_core.editing.template_panel_records import technology_targets
from packages.resume_core.editing.template_preparation import prepare_edit
from packages.resume_core.templates.materialize_nodes import literal
from packages.resume_core.templates.presentation_plan import editor_plan
from tests.templates.generic_fixtures import TABLES, export_through_service, generic_import
from tests.templates.test_focus_panel import applied, undone
from tests.templates.test_panel_records import lines, record, views
from tests.templates.test_template_preparation import response

pytestmark = pytest.mark.slow

PROGRAMMING, TOOLS, INFRASTRUCTURE = 'ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ', 'СУБД, ИНСТРУМЕНТЫ', 'ИНФРАСТРУКТУРА, ТАСК-МЕНЕДЖЕРЫ'


@pytest.fixture(scope='module')
def imported(tmp_path_factory):
    _fixture, result, workspace, originals = asyncio.run(generic_import(tmp_path_factory.mktemp('technology-groups'), 'F10'))
    assert result.state == 'published'
    return workspace, originals


@pytest.fixture
def before(imported):
    return imported[0].model_copy(deep=True)


def command(workspace, operation, *, record_id=None, kind=None, values=None, group=None, before=None, target=None,
        identifier='groups'):
    capture = {'sessionId': 'session', 'actionId': identifier, 'actionToken': 1, 'dependencies': []}
    value = {'operation': operation, 'recordId': record_id, 'recordKind': kind, 'jobId': None, 'periodId': None,
        'values': values or {}, 'factsRevision': workspace.project.facts.revision,
        'documentRevision': workspace.document_revision, 'capture': capture}
    if group is not None:
        value['groupId'] = group
    if before is not None:
        value['beforeRecordId'] = before
    operation_value = {'kind': 'builtin_panel', 'opId': 'panel', 'command': value}
    if target is not None:
        operation_value['placementContext'] = {'contextBlockId': target.block_id,
            'placement': target.placement.model_dump(mode='json', by_alias=True)}
    return TemplateEditPreparationV1(schemaVersion=1, clientMutationId=identifier, snapshot=response(workspace).snapshot,
        capture=capture, operations=[operation_value])


def groups(workspace):
    """(label, technology names) of each group the panel shows, in its order."""
    names = {value.id: value.display.raw_text for value in workspace.project.facts.records if value.kind == 'technology'}
    return [(value.label, [names[identifier] for identifier in value.records])
        for value in technology_targets(workspace.project) if value.job_id is None]


def group(workspace, label):
    return next(value for value in technology_targets(workspace.project) if value.job_id is None and value.label == label)


def technology(workspace, name, *, job=False):
    return record(workspace, 'technology', name, job=job)


def main_titles(workspace):
    return [''.join(part.text for part in block.content) for block in workspace.project.document.regions[2].blocks
        if block.type == 'heading']


def test_the_plan_lists_each_group_with_its_technologies_and_offers_a_group_of_ones_own(before):
    assert groups(before) == [(PROGRAMMING, ['Python', 'Perl']), (TOOLS, ['PostgreSQL']), (INFRASTRUCTURE, ['Docker'])]
    plan = editor_plan(before.project)
    assert plan['addTechnologyGroup'] is True
    assert [value.get('records', []) for value in plan['technologyTargets'] if value['jobId'] is None] == [
        value.records for value in technology_targets(before.project) if value.job_id is None]


def test_a_technology_moves_between_groups_before_another_or_to_the_end_and_undoes(before):
    perl, postgres = technology(before, 'Perl'), technology(before, 'PostgreSQL')
    after, result = applied(before, command(before, 'move_technology', record_id=perl.id, group='view:data_and_tools',
        before=postgres.id))
    assert lines(after, 'programming') == ['Python'] and lines(after, 'data_and_tools') == ['Perl, PostgreSQL']
    # The fact stays as it was; only its place in the resume changes.
    assert technology(after, 'Perl') == perl
    undone(before, after, result)
    after, _result = applied(before, command(before, 'move_technology', record_id=perl.id, group='view:data_and_tools'))
    assert lines(after, 'data_and_tools') == ['PostgreSQL, Perl']
    # Inside one group a move only reorders. Focus keeps a Python of its own, so the group's is read from its target.
    after, _result = applied(before, command(before, 'move_technology', record_id=perl.id, group='view:programming',
        before=group(before, PROGRAMMING).records[0]))
    assert lines(after, 'programming') == ['Perl, Python']


def test_the_last_technology_takes_its_group_title_and_the_group_comes_back_where_the_import_puts_it(before):
    docker = technology(before, 'Docker')
    gone, _result = applied(before, command(before, 'move_technology', record_id=docker.id, group='view:programming'))
    assert 'infrastructure' not in views(gone) and INFRASTRUCTURE not in main_titles(gone)
    assert lines(gone, 'programming') == ['Python, Perl, Docker']
    assert groups(gone)[-1] == (INFRASTRUCTURE, []) and group(gone, INFRASTRUCTURE).block_id == 'view:infrastructure'
    back, result = applied(gone, command(gone, 'move_technology', record_id=docker.id, group='view:infrastructure',
        identifier='groups-back'))
    assert lines(back, 'infrastructure') == ['Docker'] and lines(back, 'programming') == ['Python, Perl']
    assert main_titles(back)[-3:] == [PROGRAMMING, TOOLS, INFRASTRUCTURE]
    undone(gone, back, result)
    with pytest.raises(ValueError, match='TECHNOLOGY_TARGET_MISSING'):
        prepare_edit(response(gone), command(gone, 'move_technology', record_id=docker.id, group='view:infrastructure',
            before=technology(gone, 'Python').id))


def test_a_group_of_ones_own_follows_the_last_group_takes_technologies_and_goes_with_its_last(before):
    after, result = applied(before, command(before, 'add_technology_group', values={'title': '  Облака ', 'display': 'AWS'}))
    assert main_titles(after)[-4:] == [PROGRAMMING, TOOLS, INFRASTRUCTURE, 'Облака']
    # The new group copies the last group's view, so the page and the export show it as that group.
    assert lines(after, 'infrastructure') == ['Docker', 'AWS']
    own = group(after, 'Облака')
    assert groups(after)[-1] == ('Облака', ['AWS']) and not own.block_id.startswith('view:')
    aws = technology(after, 'AWS')
    assert aws.job_id is None and aws.origin == 'user'
    undone(before, after, result)
    more, _result = applied(after, command(after, 'add', kind='technology', values={'display': 'GCP'}, target=own,
        identifier='groups-more'))
    perl = technology(more, 'Perl')
    moved, _result = applied(more, command(more, 'move_technology', record_id=perl.id, group=own.block_id,
        before=technology(more, 'GCP').id, identifier='groups-moved'))
    assert groups(moved)[0] == (PROGRAMMING, ['Python']) and groups(moved)[-1] == ('Облака', ['AWS', 'Perl', 'GCP'])
    # Taking a user's technology out of a group shown nowhere else takes its fact too.
    taken, _result = applied(moved, command(moved, 'remove', record_id=technology(moved, 'AWS').id, group=own.block_id,
        identifier='groups-taken'))
    assert not any(value.kind == 'technology' and value.display.raw_text == 'AWS' for value in taken.project.facts.records)
    emptied = taken
    for name in ['Perl', 'GCP']:
        emptied, _result = applied(emptied, command(emptied, 'remove', record_id=technology(emptied, name).id,
            group=own.block_id, identifier='groups-' + name))
    # No title of an empty group stays behind, and the template's groups are as before.
    assert 'Облака' not in main_titles(emptied) and [label for label, _names in groups(emptied)] == [
        PROGRAMMING, TOOLS, INFRASTRUCTURE]
    assert lines(emptied, 'infrastructure') == ['Docker']


def test_a_group_of_ones_own_can_start_with_a_technology_from_another_group(before):
    postgres = technology(before, 'PostgreSQL')
    after, _result = applied(before, command(before, 'add_technology_group', record_id=postgres.id,
        values={'title': 'Базы данных'}))
    assert TOOLS not in main_titles(after) and main_titles(after)[-1] == 'Базы данных'
    # The emptied group of the template stays offered in its place; a group of one's own comes after the template's.
    assert groups(after) == [(PROGRAMMING, ['Python', 'Perl']), (TOOLS, []), (INFRASTRUCTURE, ['Docker']),
        ('Базы данных', ['PostgreSQL'])]
    assert technology(after, 'PostgreSQL') == postgres


def test_a_job_technology_leaves_a_group_but_stays_with_its_job(before):
    # The import puts a job's technology no group admitted into the uncertain group, as assign_skills does.
    docker = technology(before, 'Docker', job=True)
    changed = before.model_copy(deep=True)
    line = next(block for block in changed.project.document.blocks() if block.type == 'paragraph'
        and block.presentation is not None and block.presentation.view_key == 'data_and_tools')
    sample = next(part for part in line.content if getattr(part, 'field_key', None) == 'display')
    line.content += [literal(', ', sample.presentation), sample.model_copy(update={'record_id': docker.id, 'text': 'Docker',
        'binding_id': 'moved-docker', 'binding_root_id': 'moved-docker', 'occurrence_id': 'moved-docker',
        'cell_id': field_key(docker.id, 'display')})]
    assert groups(changed)[1] == (TOOLS, ['PostgreSQL', 'Docker'])
    chips = [value for value in lines(changed, 'projects') if 'Docker' in value]
    after, _result = applied(changed, command(changed, 'remove', record_id=docker.id, group='view:data_and_tools'))
    assert lines(after, 'data_and_tools') == ['PostgreSQL'] and [value for value in lines(after, 'projects') if 'Docker' in value] == chips
    assert technology(after, 'Docker', job=True) == docker
    # A move takes it from the group it is in, never from its job.
    moved, _result = applied(changed, command(changed, 'move_technology', record_id=docker.id, group='view:programming'))
    assert lines(moved, 'programming') == ['Python, Perl, Docker'] and lines(moved, 'data_and_tools') == ['PostgreSQL']
    assert [value for value in lines(moved, 'projects') if 'Docker' in value] == chips


def test_group_commands_are_checked(before):
    perl = technology(before, 'Perl')
    refusals = [
        ('TECHNOLOGY_GROUP_TITLE_REQUIRED', command(before, 'add_technology_group', values={'title': '  ', 'display': 'AWS'})),
        ('TECHNOLOGY_GROUP_DUPLICATE', command(before, 'add_technology_group', values={'title': 'субд, инструменты',
            'display': 'AWS'})),
        ('TECHNOLOGY_DUPLICATE', command(before, 'add_technology_group', values={'title': 'Языки', 'display': 'perl'})),
        ('TECHNOLOGY_GROUP_MISSING', command(before, 'move_technology', record_id=perl.id, group='view:summary')),
        ('TECHNOLOGY_TARGET_MISSING', command(before, 'move_technology', record_id=perl.id, group='view:data_and_tools',
            before=technology(before, 'Python').id)),
        ('TECHNOLOGY_TARGET_MISSING', command(before, 'remove', record_id=perl.id, group='view:data_and_tools')),
    ]
    for code, value in refusals:
        with pytest.raises(ValueError, match=code):
            prepare_edit(response(before), value)
    base = {'factsRevision': 1, 'documentRevision': 1, 'capture': {'sessionId': 's', 'actionId': 'a', 'actionToken': 1,
        'dependencies': []}}
    for value in [{'operation': 'edit', 'recordId': perl.id, 'groupId': 'view:programming', 'values': {'display': 'x'}},
            {'operation': 'add_technology_group', 'values': {'display': 'AWS'}},
            {'operation': 'add_technology_group', 'recordId': perl.id, 'values': {'title': 'T', 'display': 'AWS'}},
            {'operation': 'move_focus', 'recordId': perl.id, 'groupId': 'view:programming'}]:
        with pytest.raises(ValidationError):
            RichPanelRequest.model_validate({**base, **value})


def test_the_export_shows_a_group_of_ones_own_as_the_template_shows_its_groups(imported, tmp_path):
    workspace, originals = imported
    after, _result = applied(workspace, command(workspace, 'add_technology_group', values={'title': 'Облака', 'display': 'AWS'}))
    package = asyncio.run(export_through_service(tmp_path, after, originals))
    xml = zipfile.ZipFile(io.BytesIO(package)).read('word/document.xml').decode()
    paragraphs = re.findall(r'<w:p[ >].*?</w:p>', xml, re.S)
    def look(text):
        found = next(value for value in paragraphs if text in value)
        return [re.search(pattern, found, re.S).group(0) for pattern in (r'<w:pPr>.*?</w:pPr>', r'<w:rPr>.*?</w:rPr>')]
    assert look('Облака') == look(INFRASTRUCTURE) and any('AWS' in value for value in paragraphs)


@pytest.fixture(scope='module')
def unrewritten(tmp_path_factory):
    # Without Perl in its own group, the old job's Perl joins the fallback group with a remark (as in the F10-off import).
    table = {**TABLES['F10'](False), 'programming': ({'items': ['Python']}, {})}
    _fixture, result, workspace, _originals = asyncio.run(generic_import(tmp_path_factory.mktemp('groups-remark'), 'F10',
        rewrite=False, table=table))
    assert result.state == 'published'
    return workspace


def test_moving_a_technology_out_of_its_uncertain_group_retires_its_remark(unrewritten):
    before = unrewritten.model_copy(deep=True)
    remark = next(issue for issue in before.project.import_issues if issue.code == 'IMPORT_SKILL_GROUP_UNCERTAIN')
    perl = technology(before, 'Perl', job=True)
    assert perl.id in group(before, TOOLS).records and remark.state == 'active'
    after, _result = applied(before, command(before, 'move_technology', record_id=perl.id, group='view:programming'))
    assert next(issue for issue in after.project.import_issues if issue.id == remark.id).state == 'retired'
