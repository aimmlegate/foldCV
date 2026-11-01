"""Facts panel edits outside employment on the two-column F10 import (D113): record fields, technologies in their lines,
education and language removal; Undo restores each, and an action without an adapter is refused with a public code."""

import asyncio
import json

import pytest

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import FieldOccurrence
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_dependencies import placements
from packages.resume_core.rich_fields import field_key
from packages.resume_core.templates.materialize_nodes import literal
from packages.resume_core.template_panel_records import technology_targets
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.presentation_plan import editor_plan
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.generic_fixtures import generic_import, generic_package
from tests.templates.test_focus_panel import applied, undone
from tests.templates.test_template_preparation import response

pytestmark = pytest.mark.slow


@pytest.fixture(scope='module')
def imported(tmp_path_factory):
    _fixture, result, workspace, _originals = asyncio.run(generic_import(tmp_path_factory.mktemp('panel-records'), 'F10'))
    assert result.state == 'published'
    return workspace


@pytest.fixture
def before(imported):
    return imported.model_copy(deep=True)


@pytest.fixture(scope='module')
def ongoing(tmp_path_factory):
    _fixture, result, workspace, _originals = asyncio.run(generic_import(tmp_path_factory.mktemp('panel-ongoing'), 'F04'))
    assert result.state == 'published'
    return workspace


def request(before, operation, *, record_id=None, kind=None, job_id=None, values=None, line=None, target=None,
        identifier='records'):
    capture = {'sessionId': 'session', 'actionId': identifier, 'actionToken': 1, 'dependencies': []}
    operation_value = {'kind': 'builtin_panel', 'opId': 'panel', 'command': {'operation': operation, 'recordId': record_id,
        'recordKind': kind, 'jobId': job_id, 'periodId': None, 'values': values or {},
        'factsRevision': before.project.facts.revision, 'documentRevision': before.document_revision, 'capture': capture}}
    if line is not None:
        parent, previous, _owner = placements(before.project.document)[line]
        operation_value['placementContext'] = {'contextBlockId': line, 'placement': {'parentId': parent, 'afterId': previous}}
    if target is not None:
        operation_value['placementContext'] = {'contextBlockId': target.block_id,
            'placement': target.placement.model_dump(mode='json', by_alias=True)}
    return TemplateEditPreparationV1(schemaVersion=1, clientMutationId=identifier, snapshot=response(before).snapshot,
        capture=capture, operations=[operation_value])


def record(workspace, kind, text=None, *, job=False):
    return next(value for value in workspace.project.facts.records if value.kind == kind and (text is None or {
        'candidate': lambda: value.name.raw_text, 'technology': lambda: value.display.raw_text,
        'education': lambda: value.institution.raw_text, 'language': lambda: value.language.raw_text,
        'claim': lambda: value.value.raw_text}[kind]() == text) and (kind != 'technology' or bool(value.job_id) == job))


def lines(workspace, view):
    """The text of each paragraph of one view, in document order."""
    return [''.join(getattr(part, 'text', '') for part in block.content) for block in workspace.project.document.blocks()
        if block.type == 'paragraph' and block.presentation is not None and block.presentation.view_key == view]


def views(workspace):
    return {block.presentation.view_key for block in workspace.project.document.blocks() if block.presentation is not None}


def job_line(workspace):
    return lines(workspace, 'projects')[2]


def group(workspace, label):
    return next(value for value in technology_targets(workspace.project) if value.job_id is None and value.label == label)


def main_views(workspace):
    """The views of the main region in document order, each once."""
    keys = [block.presentation.view_key for block in workspace.project.document.regions[2].blocks if block.presentation is not None]
    return list(dict.fromkeys(keys))


def shown_in(workspace, view):
    """The technology record of the first name span in a view; the two-column Focus and group views keep records of their own."""
    return next(part.record_id for block in workspace.project.document.blocks() if block.presentation is not None
        and block.presentation.view_key == view and isinstance(block.content, list)
        for part in block.content if getattr(part, 'field_key', None) == 'display')


def test_candidate_and_item_fields_change_their_document_text_and_undo(before):
    candidate = record(before, 'candidate')
    after, result = applied(before, request(before, 'edit', record_id=candidate.id, values={'name': 'Alex Sample',
        'title': 'Backend engineer'}))
    assert lines(after, 'identity') == ['Alex Sample', 'Backend engineer']
    assert record(after, 'candidate').name.raw_text == 'Alex Sample'
    undone(before, after, result)
    education = record(before, 'education')
    after, result = applied(before, request(before, 'edit', record_id=education.id, values={'institution': 'Example University'}))
    assert lines(after, 'education') == ['Example University']
    undone(before, after, result)
    language = record(before, 'language')
    after, _result = applied(before, request(before, 'edit', record_id=language.id, values={'language': 'German'}))
    assert lines(after, 'languages') == ['German']
    # The same values again change nothing.
    assert prepare_edit(response(before), request(before, 'edit', record_id=language.id,
        values={'language': 'English'})).mutation is None


def test_a_technology_rename_changes_only_its_own_line_or_focus_row_and_refuses_a_duplicate(before):
    grouped = shown_in(before, 'programming')
    after, result = applied(before, request(before, 'edit', record_id=grouped, values={'display': 'Python 3'}))
    assert lines(after, 'programming') == ['Python 3, Perl']
    # The Focus row and the job keep records of their own.
    assert lines(after, 'focus') == ['Python', '3 years'] and job_line(after) == 'Python PostgreSQL Docker'
    renamed = next(value for value in after.project.facts.records if value.id == grouped)
    assert renamed.canonical_id.value == 'python'
    undone(before, after, result)
    focus = shown_in(before, 'focus')
    after, result = applied(before, request(before, 'edit', record_id=focus, values={'display': 'Python 3', 'experience': '5'}))
    assert lines(after, 'focus') == ['Python 3', '5 лет'] and lines(after, 'programming') == ['Python, Perl']
    undone(before, after, result)
    with pytest.raises(ValueError, match='TECHNOLOGY_DUPLICATE'):
        prepare_edit(response(before), request(before, 'edit', record_id=grouped, values={'display': 'perl'}))


def test_removing_a_job_technology_takes_its_separator_and_undoes(before):
    postgres = record(before, 'technology', 'PostgreSQL', job=True)
    after, result = applied(before, request(before, 'remove', record_id=postgres.id))
    assert job_line(after) == 'Python Docker'
    assert postgres.id not in {value.id for value in after.project.facts.records}
    # The general PostgreSQL stays in its group.
    assert lines(after, 'data_and_tools') == ['PostgreSQL']
    undone(before, after, result)
    first = record(before, 'technology', 'Python', job=True)
    after, _result = applied(before, request(before, 'remove', record_id=first.id))
    assert job_line(after) == 'PostgreSQL Docker'


def test_the_last_technology_of_a_group_takes_the_group_title_and_its_focus_row(before):
    postgres = record(before, 'technology', 'PostgreSQL')
    after, result = applied(before, request(before, 'remove', record_id=postgres.id))
    assert 'data_and_tools' not in views(after)
    assert {'programming', 'infrastructure'} <= views(after)
    undone(before, after, result)
    after, result = applied(before, request(before, 'remove', record_id=shown_in(before, 'focus')))
    # Python was the only Focus row: the row and the Focus title go; the group's own Python stays.
    assert 'focus' not in views(after) and lines(after, 'programming') == ['Python, Perl']
    undone(before, after, result)
    after, _result = applied(before, request(before, 'remove', record_id=shown_in(before, 'programming')))
    assert lines(after, 'programming') == ['Perl'] and lines(after, 'focus') == ['Python', '3 years']


def test_clearing_a_job_removes_its_line_and_adding_brings_the_line_back(before):
    job = next(value for value in before.project.facts.records if value.kind == 'employment'
        and value.employer.raw_text == 'Example Labs')
    after, result = applied(before, request(before, 'clear_technologies', kind='technology', job_id=job.id))
    assert len(lines(after, 'projects')) == len(lines(before, 'projects')) - 1
    assert not [value for value in after.project.facts.records if value.kind == 'technology' and value.job_id == job.id]
    undone(before, after, result)
    section = next(block for block in after.project.document.blocks() if block.type == 'section'
        and block.props.record_id == job.id)
    assert [(value.block_id, value.job_id) for value in technology_targets(after.project) if value.job_id] == [(section.id, job.id)]
    added, added_result = applied(after, request(after, 'add', kind='technology', job_id=job.id, values={'display': ' Kafka '},
        line=section.id, identifier='records-add'))
    assert lines(added, 'projects')[2] == 'Kafka'
    line = next(block for block in added.project.document.blocks() if block.type == 'paragraph'
        and block.presentation.view_key == 'projects' and block.presentation.node_index == 2)
    assert editor_plan(added.project)['blocks'][line.id].get('chips')
    undone(after, added, added_result)


def test_adding_a_general_technology_needs_its_group_and_joins_that_line(before):
    groups = [value for value in technology_targets(before.project) if value.job_id is None]
    assert [value.label for value in groups] == ['ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ', 'СУБД, ИНСТРУМЕНТЫ',
        'ИНФРАСТРУКТУРА, ТАСК-МЕНЕДЖЕРЫ']
    with pytest.raises(ValueError, match='TECHNOLOGY_GROUP_REQUIRED'):
        prepare_edit(response(before), request(before, 'add', kind='technology', values={'display': 'Go'}))
    with pytest.raises(ValueError, match='TECHNOLOGY_DUPLICATE'):
        prepare_edit(response(before), request(before, 'add', kind='technology', values={'display': 'perl'}, target=groups[0]))
    after, result = applied(before, request(before, 'add', kind='technology', values={'display': 'Go'}, target=groups[0]))
    assert lines(after, 'programming') == ['Python, Perl, Go']
    go = record(after, 'technology', 'Go')
    assert go.job_id is None and go.origin == 'user'
    undone(before, after, result)
    # A one-entry line takes the node's own separator.
    after, _result = applied(before, request(before, 'add', kind='technology', values={'display': 'Redis'}, target=groups[1]))
    assert lines(after, 'data_and_tools') == ['PostgreSQL, Redis']
    plan = editor_plan(before.project)
    assert [value['blockId'] for value in plan['technologyTargets']] == [value.block_id for value in technology_targets(before.project)]


def test_education_and_language_removal_takes_the_item_and_its_title(before):
    education = record(before, 'education')
    after, result = applied(before, request(before, 'remove', record_id=education.id))
    assert 'education' not in views(after) and {'courses', 'languages'} <= views(after)
    undone(before, after, result)
    language = record(before, 'language')
    after, _result = applied(before, request(before, 'remove', record_id=language.id))
    assert 'languages' not in views(after)


def test_actions_without_an_adapter_are_refused_with_a_public_code(before):
    candidate = record(before, 'candidate')
    claim = record(before, 'claim')
    for value in [request(before, 'remove', record_id=candidate.id), request(before, 'remove', record_id=claim.id),
            request(before, 'add', kind='claim', values={'value': 'Other'}),
            request(before, 'edit', record_id=candidate.id, values={'email': 'a@example.org'})]:
        with pytest.raises(ValueError, match='PANEL_ACTION_UNSUPPORTED'):
            prepare_edit(response(before), value)


def test_clearing_the_general_list_keeps_focus_and_each_group_takes_technologies_again(before):
    after, result = applied(before, request(before, 'clear_technologies', kind='technology'))
    # Focus keeps the record only its row shows; the groups go with their lines.
    assert lines(after, 'focus') == ['Python', '3 years']
    assert not {'programming', 'data_and_tools', 'infrastructure'} & views(after)
    assert [(value.block_id, value.label) for value in technology_targets(after.project) if value.job_id is None] == [
        ('view:programming', 'ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ'), ('view:data_and_tools', 'СУБД, ИНСТРУМЕНТЫ'),
        ('view:infrastructure', 'ИНФРАСТРУКТУРА, ТАСК-МЕНЕДЖЕРЫ')]
    undone(before, after, result)
    gone, _result = applied(before, request(before, 'remove', record_id=record(before, 'technology', 'PostgreSQL').id))
    stale = group(gone, 'СУБД, ИНСТРУМЕНТЫ')
    back, back_result = applied(gone, request(gone, 'add', kind='technology', values={'display': 'Redis'}, target=stale,
        identifier='records-restore'))
    # The group returns with its title between its neighbours, as the import orders views, and keeps its target.
    assert lines(back, 'data_and_tools') == ['Redis']
    order = main_views(back)
    assert order.index('programming') < order.index('data_and_tools') < order.index('infrastructure')
    assert group(back, 'СУБД, ИНСТРУМЕНТЫ').block_id == stale.block_id == 'view:data_and_tools'
    more, _result = applied(back, request(back, 'add', kind='technology', values={'display': 'Kafka'},
        target=group(back, 'СУБД, ИНСТРУМЕНТЫ'), identifier='records-more'))
    assert lines(more, 'data_and_tools') == ['Redis, Kafka']
    undone(gone, back, back_result)
    # A placement from before the group came back is refused.
    with pytest.raises(ValueError, match='TECHNOLOGY_LINE_MISSING'):
        prepare_edit(response(back), request(back, 'add', kind='technology', values={'display': 'Kafka'}, target=stale,
            identifier='records-stale'))


def test_a_technology_in_focus_and_in_a_group_is_renamed_and_added_back_on_its_own(before):
    grouped, focus = shown_in(before, 'programming'), shown_in(before, 'focus')
    # The two-column pack's icons can be chosen for a row (D122).
    assert editor_plan(before.project)['focusPanel'] == {'records': [focus], 'icons': True}
    after, _result = applied(before, request(before, 'edit', record_id=grouped, values={'display': 'PYTHON'}))
    assert lines(after, 'programming') == ['PYTHON, Perl'] and lines(after, 'focus') == ['Python', '3 years']
    after, _result = applied(before, request(before, 'edit', record_id=focus, values={'display': 'python'}))
    assert lines(after, 'focus') == ['python', '3 years']
    without, _result = applied(before, request(before, 'remove', record_id=grouped))
    again, _result = applied(without, request(without, 'add', kind='technology', values={'display': 'Python'},
        target=group(without, 'ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ'), identifier='records-again'))
    assert lines(again, 'programming') == ['Perl, Python']


def test_a_group_line_that_also_shows_a_job_technology_stays_the_group_target(before):
    # The import puts a job technology no group admitted into the uncertain group, as assign_skills does.
    docker = record(before, 'technology', 'Docker', job=True)
    changed = before.model_copy(deep=True)
    line = next(block for block in changed.project.document.blocks() if block.type == 'paragraph'
        and block.presentation is not None and block.presentation.view_key == 'data_and_tools')
    sample = next(part for part in line.content if getattr(part, 'field_key', None) == 'display')
    line.content += [literal(', ', sample.presentation), sample.model_copy(update={'record_id': docker.id, 'text': 'Docker',
        'binding_id': 'moved-docker', 'binding_root_id': 'moved-docker', 'occurrence_id': 'moved-docker',
        'cell_id': field_key(docker.id, 'display')})]
    targets = technology_targets(changed.project)
    assert [value.label for value in targets if value.job_id is None] == ['ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ', 'СУБД, ИНСТРУМЕНТЫ',
        'ИНФРАСТРУКТУРА, ТАСК-МЕНЕДЖЕРЫ']
    assert [value.block_id for value in targets if value.job_id == docker.job_id] == [
        value.block_id for value in technology_targets(before.project) if value.job_id == docker.job_id]


def labelled_package():
    """The two-column template with a label line before each job's technologies, as a custom template may declare."""
    config = generic_package().definition.model_dump(mode='json', by_alias=True)
    projects = next(value for value in config['blocks'] if value['id'] == 'projects')
    projects['view']['nodes'][2]['label'] = {'ru': 'Стек:', 'en': 'Stack:'}
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def test_removing_a_labelled_job_line_takes_its_label_and_adding_brings_one_back(tmp_path):
    _fixture, result, before, _originals = asyncio.run(generic_import(tmp_path, 'F10', package=labelled_package()))
    assert result.state == 'published'
    job = next(value for value in before.project.facts.records if value.kind == 'employment'
        and value.employer.raw_text == 'Example Labs')
    assert lines(before, 'projects')[2:4] == ['Стек:', 'Python PostgreSQL Docker']
    cleared, _result = applied(before, request(before, 'clear_technologies', kind='technology', job_id=job.id))
    assert 'Стек:' not in lines(cleared, 'projects')
    section = next(value for value in technology_targets(cleared.project) if value.job_id == job.id)
    added, _result = applied(cleared, request(cleared, 'add', kind='technology', job_id=job.id, values={'display': 'Kafka'},
        target=section, identifier='records-kafka'))
    assert lines(added, 'projects')[2:4] == ['Стек:', 'Kafka'] and lines(added, 'projects').count('Стек:') == 1


def job(workspace, name=None):
    return next(value for value in workspace.project.facts.records if value.kind == 'employment'
        and (name is None or value.employer.raw_text == name))


def period_blocks(workspace, name='Current Systems'):
    section = next(block for block in workspace.project.document.blocks() if block.type == 'section'
        and block.props.record_id == job(workspace, name).id)
    return [block for block in section.children if block.presentation.node_index == 1]


def period_lines(workspace, name='Current Systems'):
    return [''.join(part.text for part in block.content) for block in period_blocks(workspace, name)]


def period_edit(workspace, name='Current Systems', **values):
    target = job(workspace, name)
    return request(workspace, 'edit', record_id=target.id, identifier=f'period-edit-{workspace.project_revision}', values={
        f'period:{target.periods[0].id}:{key}': value for key, value in values.items()})


def test_ending_a_current_job_binds_its_end_in_the_formats_place_and_back(ongoing):
    before = ongoing.model_copy(deep=True)
    assert period_lines(before) == ['2020 – по настоящее время']
    ended, result = applied(before, period_edit(before, present='', end='2024-05'))
    assert period_lines(ended) == ['2020 – 2024']
    period = job(ended, 'Current Systems').periods[0]
    assert period.end.value.month == 5
    assert [span.field_key for span in period_blocks(ended)[0].content if isinstance(span, FieldOccurrence)] == [
        f'period:{period.id}:start', f'period:{period.id}:end']
    assert undone(before, ended, result)
    back, _ = applied(ended, period_edit(ended, present='по настоящее время'))
    assert period_lines(back) == ['2020 – по настоящее время']
    assert job(back, 'Current Systems').periods[0].present.value is True


def test_clearing_the_current_mark_without_an_end_leaves_the_start_alone(ongoing):
    before = ongoing.model_copy(deep=True)
    after, _ = applied(before, period_edit(before, present=''))
    assert period_lines(after) == ['2020']
    filled, _ = applied(after, period_edit(after, end='2021'))
    assert period_lines(filled) == ['2020 – 2021']


def test_a_label_alone_becomes_the_end_and_a_period_without_a_line_gets_one(ongoing):
    before = ongoing.model_copy(deep=True)
    cleared, _ = applied(before, period_edit(before, start=''))
    assert period_lines(cleared) == ['по настоящее время']
    ended, _ = applied(cleared, period_edit(cleared, present='', end='2024'))
    assert period_lines(ended) == ['2024']
    empty, _ = applied(ended, period_edit(ended, end=''))
    assert period_lines(empty) == []
    again, _ = applied(empty, period_edit(empty, present='по настоящее время'))
    assert period_lines(again) == ['по настоящее время']
    section = next(block for block in again.project.document.blocks() if block.type == 'section'
        and block.props.record_id == job(again, 'Current Systems').id)
    assert section.children[1] == period_blocks(again)[0]


def test_an_authored_period_line_stays_and_an_endpoint_it_cannot_show_is_refused(ongoing):
    before = ongoing.model_copy(deep=True)
    period_blocks(before)[0].content[-1].text = 'и работаю сейчас'
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    with pytest.raises(ValueError, match='PANEL_ACTION_UNSUPPORTED'):
        prepare_edit(response(before), period_edit(before, present='', end='2024'))
    after, _ = applied(before, period_edit(before, start='2019'))
    assert period_lines(after) == ['2019 – и работаю сейчас']


def test_an_edited_date_takes_its_siblings_pattern_and_facts_read_the_same(before):
    after, _ = applied(before, period_edit(before, 'Example Labs', start='2020-04'))
    assert period_lines(after, 'Example Labs') == ['04.2020 – 11.2023']
    period = job(after, 'Example Labs').periods[0]
    assert (period.start.raw_text, period.start.value.month) == ('04.2020', 4)
    jobs = editor_plan(after.project)['jobs']
    assert jobs[period_owner(after, 'Example Labs')]['periods'] == ['04.2020 – 11.2023']
    assert jobs[period_owner(after, 'Old Systems')]['periods'] == ['2006 – 2008']


def period_owner(workspace, name):
    return job(workspace, name).id


def test_removing_a_jobs_only_period_takes_its_line(before):
    target = job(before, 'Example Labs')
    command = request(before, 'remove_period', record_id=target.id)
    command.operations[0].command.period_id = target.periods[0].id
    after, result = applied(before, command)
    assert period_lines(after, 'Example Labs') == []
    assert undone(before, after, result)


def test_a_new_current_job_opens_its_view_with_the_formats_dates(before):
    after, result = applied(before, request(before, 'add', kind='employment', values={'employer': 'New Co', 'role': 'Dev',
        'start': '2024-01', 'end': '', 'present': 'по настоящее время'}))
    blocks = after.project.document.regions[2].blocks
    old = {block.id for block in before.project.document.regions[2].blocks}
    at = next(index for index, block in enumerate(blocks) if block.id not in old)
    assert blocks[at - 1].type == 'heading' and blocks[at + 1].presentation.view_key == 'projects'
    assert period_lines(after, 'New Co') == ['01.2024 – по настоящее время']
    assert undone(before, after, result)
    closed, _ = applied(before, request(before, 'add', kind='employment', values={'employer': 'Old Co', 'start': '2010', 'end': ''}))
    assert period_lines(closed, 'Old Co') == ['2010']


def test_a_job_after_its_view_went_brings_the_title_back_where_the_import_puts_it(before):
    region = before.project.document.regions[2]
    gone = {block.id for top in region.blocks if top.presentation.view_key == 'projects' for block in [top, *top.children]}
    region.blocks = [block for block in region.blocks if block.id not in gone]
    for row in before.project.import_coverage:
        row.block_ids = [identifier for identifier in row.block_ids if identifier not in gone]
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    after, _ = applied(before, request(before, 'add', kind='employment', values={'employer': 'New Co'}))
    assert main_views(after).index('projects') == 1 and main_views(after)[2] == 'other_projects'
    assert lines(after, 'projects')[0] == 'New Co'


def test_a_field_with_no_occurrence_joins_the_line_of_its_node(before):
    language = record(before, 'language')
    after, result = applied(before, request(before, 'edit', record_id=language.id, values={'level': 'B2'}))
    assert lines(after, 'languages') == ['English B2']
    assert undone(before, after, result)
    education = record(before, 'education')
    after, _ = applied(before, request(before, 'edit', record_id=education.id, values={'specialty': 'CS', 'completion': '2019'}))
    assert lines(after, 'education') == ['Example Institute', '2019', 'CS']


def test_a_field_before_a_shown_part_goes_first_and_a_new_line_keeps_the_prefix(before):
    target = job(before, 'Example Labs')
    line = next(block for block in before.project.document.blocks() if block.presentation is not None
        and block.presentation.view_key == 'projects' and block.presentation.node_index == 0)
    line.content = [line.content[2]]
    role = next(block for block in before.project.document.blocks() if block.presentation is not None
        and block.presentation.view_key == 'projects' and block.presentation.node_index == 4)
    section = next(block for block in before.project.document.blocks() if block.type == 'section' and line in block.children)
    section.children.remove(role)
    for row in before.project.import_coverage:
        row.block_ids = [identifier for identifier in row.block_ids if identifier != role.id]
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    after, _ = applied(before, request(before, 'edit', record_id=target.id, values={'employer': 'Renamed', 'role': 'lead'}))
    assert lines(after, 'projects')[0] == 'Renamed — Queue Platform'
    assert 'Роль: lead' in lines(after, 'projects')


def test_the_plan_leaves_out_fields_without_a_place_and_periods_a_job_cannot_take(before):
    plan = editor_plan(before.project)
    candidate, old, labs = record(before, 'candidate'), job(before, 'Old Systems'), job(before, 'Example Labs')
    assert plan['unshownFields'] == {candidate.id: ['location'], old.id: ['role']}
    assert plan['jobs'][labs.id]['addPeriod'] is True and 'addPeriod' not in plan['jobs'][old.id]
    command = request(before, 'add_period', record_id=old.id)
    with pytest.raises(ValueError):
        prepare_edit(response(before), command)
    assert prepare_edit(response(before), request(before, 'add_period', record_id=labs.id)).mutation is not None


def test_the_plan_names_the_lines_a_move_stays_in(before):
    lined = editor_plan(before.project)['technologyLines']
    names = {value.id: value.display.raw_text for value in before.project.facts.records if value.kind == 'technology'}
    assert [[names[identifier] for identifier in line] for line in lined] == [['Python', 'PostgreSQL', 'Docker'], ['Python', 'Perl']]


def prose(before, name):
    """A paragraph of its own text around a technology, as a same-project semantic paste leaves it."""
    target = record(before, 'technology', name, job=False)
    block = next(value for value in before.project.document.blocks() if value.presentation is not None
        and value.presentation.view_key == 'summary' and value.type == 'paragraph')
    ref = block.presentation
    block.content = [literal('Ten years of ', ref), FieldOccurrence(type='fact_field', bindingId='prose-fragment',
        bindingRootId='prose', recordId=target.id, fieldKey='display', cellId=field_key(target.id, 'display'),
        occurrenceId='prose', complete=True, presentation=ref, text=name, styles={},
        syncedFactRevision=target.display.revision), literal(' in production at scale.', ref)]
    return WorkspaceV7.model_validate(before.model_dump(by_alias=True)), target


def test_removing_a_technology_named_in_authored_prose_is_refused_and_keeps_the_prose(before):
    before, target = prose(before, 'Perl')
    with pytest.raises(ValueError, match='PANEL_LINE_SHARED'):
        prepare_edit(response(before), request(before, 'remove', record_id=target.id))
    assert lines(before, 'summary') == ['Ten years of Perl in production at scale.']


def compressed(before):
    """Three jobs in the compressed line, as the materializer joins several."""
    middle = job(before, 'Old Systems')
    extra = [middle.model_copy(deep=True), middle.model_copy(deep=True)]
    for value, identifier, name in zip(extra, ('record-old-a', 'record-old-b'), ('Older A', 'Older B')):
        value.id, value.employer.raw_text, value.employer.value = identifier, name, name
        value.periods[0].id = 'period-' + identifier
    before.project.facts.records.extend(extra)
    block = next(value for value in before.project.document.blocks() if value.presentation is not None
        and value.presentation.view_key == 'other_projects' and value.type == 'paragraph')
    span, ref = block.content[0], block.presentation
    def shown(value):
        return span.model_copy(update={'binding_id': 'fragment-' + value.id, 'binding_root_id': 'root-' + value.id,
            'occurrence_id': 'root-' + value.id, 'record_id': value.id, 'cell_id': field_key(value.id, 'employer'),
            'text': value.employer.raw_text}, deep=True)
    block.content = [shown(extra[0]), literal(', ', ref), span, literal(', ', ref), shown(extra[1])]
    return WorkspaceV7.model_validate(before.model_dump(by_alias=True))


def test_removing_a_job_from_a_joined_line_takes_its_separator_and_the_last_takes_the_title(before):
    before = compressed(before)
    after, result = applied(before, request(before, 'remove', record_id=job(before, 'Old Systems').id))
    assert lines(after, 'other_projects') == ['Older A, Older B']
    assert undone(before, after, result)
    after, _ = applied(after, request(after, 'remove', record_id=job(after, 'Older A').id, identifier='remove-a'))
    assert lines(after, 'other_projects') == ['Older B']
    after, _ = applied(after, request(after, 'remove', record_id=job(after, 'Older B').id, identifier='remove-b'))
    assert 'other_projects' not in views(after)


def test_a_computed_focus_line_follows_job_dates_and_technologies(before):
    docker = shown_in(before, 'infrastructure')
    added, _ = applied(before, request(before, 'add_to_focus', record_id=docker))
    assert focus_detail(added, 'Docker') == '4 года'
    moved, result = applied(added, period_edit(added, 'Example Labs', start='2010-03'))
    assert focus_detail(moved, 'Docker') == '14 лет'
    assert undone(added, moved, result)
    # The stated experience of the imported row is no computed line, and the user's own text stays.
    assert focus_detail(moved, 'Python') == '3 years'
    line = next(block for block in added.project.document.blocks() if block.presentation is not None
        and block.presentation.view_key == 'focus' and ''.join(getattr(part, 'text', '') for part in block.content) == '4 года')
    line.content[0].text = 'давно'
    typed = WorkspaceV7.model_validate(added.model_dump(by_alias=True))
    kept, _ = applied(typed, period_edit(typed, 'Example Labs', start='2010-03'))
    assert focus_detail(kept, 'Docker') == 'давно'


def focus_detail(workspace, name):
    rows = {lines_of[0]: lines_of[1:] for lines_of in ([''.join(getattr(part, 'text', '') for part in child.content)
        for child in block.children] for block in workspace.project.document.blocks()
        if block.type == 'section' and block.presentation is not None and block.presentation.view_key == 'focus')}
    return rows[name][0]
