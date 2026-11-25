"""Job order and date warnings in Facts (D182): rows in page order, a new job by date, a card's move by one place, the
sort newest first, and the warnings «Стоит не по дате» and «Пересекается с …». All data is synthetic."""

import asyncio

import pytest

from packages.resume_core.editing.mutations import apply_rich_mutation
from packages.resume_core.editing.template_inverse import inverse_template_mutation, semantic
from packages.resume_core.editing.template_panel_jobs import (check_dates, job_lists, job_order, job_warnings,
                                                              periods_overlap)
from packages.resume_core.editing.template_panel_records import panel_plan
from packages.resume_core.editing.template_preparation import prepare_edit
from packages.resume_core.fields import set_text
from packages.resume_core.hashing import canonical
from packages.resume_core.importing.template_builtin_admission import unknown
from packages.resume_core.models.panel_request import RichPanelRequest
from packages.resume_core.models.rich_facts import EmploymentRecord, WorkingPeriod
from tests.templates.generic_fixtures import generic_import
from tests.templates.test_panel_creation import request
from tests.templates.test_panel_preparation import prepared, restore
from tests.templates.test_template_preparation import response
from tests.templates.test_transactions import authorization


def period(start='', end='', present=False, identifier='p'):
    value = WorkingPeriod(id=identifier, revision=1, start=unknown(), end=unknown(),
        present={**unknown(), 'value': False, 'status': 'known'}, evidence=[])
    job = EmploymentRecord(id='job', kind='employment', revision=1, origin='user', evidence=[], employer=unknown(),
        role=unknown(), periods=[value])
    for key, text in (('start', start), ('end', end), ('present', 'по настоящее время' if present else '')):
        set_text(job, f'period:{identifier}:{key}', text)
    return job.periods[0]


OVERLAPS = [
    (('01.2020', '05.2022'), ('05.2022', '03.2024'), False),
    (('01.2020', '06.2022'), ('05.2022', '03.2024'), True),
    (('2019', '2021'), ('2021', '2023'), False),
    (('2019', '2022'), ('2021', '2023'), True),
    (('2019', '2021'), ('06.2021', '2023'), False),
    (('03.2022', '', True), ('01.2023', '06.2023'), True),
    # Containment, a day precision against a month, and periods far apart.
    (('2015', '2024'), ('03.2018', '04.2019'), True),
    (('15.03.2021', '20.05.2022'), ('05.2022', '2023'), False),
    (('15.03.2021', '20.06.2022'), ('05.2022', '2023'), True),
    (('2001', '2003'), ('2010', '2012'), False),
    # Two current periods overlap; one that ends before the other starts does not.
    (('2018', '', True), ('2021', '', True), True),
    (('2015', '2017'), ('2018', '', True), False),
    # No start, no end and not current, text that is not a date, an end before the start: no warning.
    (('', '2021'), ('2019', '2023'), False),
    (('2019', ''), ('2020', '2021'), False),
    (('весна 2020', '2022'), ('2021', '2023'), False),
    (('2019', 'потом'), ('2020', '2021'), False),
    (('2023', '2019'), ('2020', '2021'), False),
    # Two one-unit periods of the same unit only touch.
    (('2020', '2020'), ('2020', '2020'), False),
]


@pytest.mark.parametrize(('first', 'second', 'expected'), OVERLAPS)
def test_two_periods_overlap_only_past_their_shared_boundary_unit(first, second, expected):
    one, two = period(*first, identifier='a'), period(*second, identifier='b')
    assert periods_overlap(one, two) is expected
    assert periods_overlap(two, one) is expected


@pytest.fixture(scope='module')
def two_column(tmp_path_factory):
    return asyncio.run(generic_import(tmp_path_factory.mktemp('job-order'), 'F10'))[2]


def employer(project, record_id):
    return next(record.employer.raw_text for record in project.facts.records if record.id == record_id)


def cards(workspace):
    """The employer names of the detailed list's cards, in page order."""
    project = workspace.project
    return [employer(project, block.props.record_id) for _parent, items in job_lists(project) for block in items]


def add(before, name, identifier, **dates):
    result = prepared(before, request(before, values={'employer': name, 'role': 'Dev', **dates}, identifier=identifier))
    return result.preview.workspace


def panel(before, operation, record_id=None, values=None, identifier='job-move'):
    return request(before, operation=operation, kind='employment', record_id=record_id, values=values, identifier=identifier)


def job_id(workspace, name):
    return next(record.id for record in workspace.project.facts.records if record.kind == 'employment'
        and record.employer.raw_text == name)


@pytest.fixture(scope='module')
def three(two_column):
    """Example Labs (03.2020 – 11.2023) and two new jobs in the detailed list; Old Systems stays in the compact list."""
    workspace = add(two_column, 'Early Corp', 'add-early', start='2010', end='2012')
    return add(workspace, 'Middle Inc', 'add-middle', start='2015', end='2017')


def test_a_new_job_goes_to_its_place_by_date_also_in_the_middle(three):
    assert cards(three) == ['Example Labs', 'Middle Inc', 'Early Corp']


def test_a_new_job_goes_before_the_first_older_card_of_a_list_out_of_order(three):
    moved = move(three, 'Early Corp', 'up', 'move-1')
    moved = move(moved, 'Early Corp', 'up', 'move-2')
    assert cards(moved) == ['Early Corp', 'Example Labs', 'Middle Inc']
    current = add(moved, 'Newer Ltd', 'add-newer', start='2018', end='2019')
    assert cards(current) == ['Newer Ltd', 'Early Corp', 'Example Labs', 'Middle Inc']


def test_a_current_job_from_the_add_form_is_the_newest(three):
    current = add(three, 'Now Co', 'add-now', start='2012', present='по настоящее время')
    record = next(record for record in current.project.facts.records if record.id == job_id(current, 'Now Co'))
    assert record.periods[0].present.value is True
    assert cards(current)[0] == 'Now Co'


def test_a_job_without_a_date_goes_last(three):
    assert cards(add(three, 'Undated', 'add-undated'))[-1] == 'Undated'


def move(before, name, direction, identifier):
    result = prepared(before, panel(before, 'move_job', job_id(before, name), {'direction': direction}, identifier))
    assert result.mutation is not None
    assert {step.kind for step in result.mutation.steps} == {'move_block'}
    restore(before, result)
    return result.preview.workspace


def test_facts_rows_follow_the_page_and_a_job_off_the_page_comes_last(three):
    project = three.project
    order = [employer(project, identifier) for identifier in job_order(project)]
    # The compact list stands below the detailed one on the page.
    assert order == ['Example Labs', 'Middle Inc', 'Early Corp', 'Old Systems']
    moved = move(three, 'Early Corp', 'up', 'move-row')
    assert [employer(moved.project, value) for value in panel_plan(moved.project)['jobOrder']][:3] == \
        ['Example Labs', 'Early Corp', 'Middle Inc']
    off = three.model_copy(deep=True)
    for region in off.project.document.regions:
        region.blocks = [block for block in region.blocks if getattr(block.props, 'record_id', None) != job_id(three, 'Example Labs')]
    assert [employer(off.project, value) for value in job_order(off.project)][-1] == 'Example Labs'
    assert 'move' not in panel_plan(off.project)['jobs'][job_id(three, 'Example Labs')]


def test_the_plan_offers_only_the_moves_a_card_has(three):
    jobs = panel_plan(three.project)['jobs']
    assert jobs[job_id(three, 'Example Labs')]['move'] == {'up': False, 'down': True}
    assert jobs[job_id(three, 'Middle Inc')]['move'] == {'up': True, 'down': True}
    assert jobs[job_id(three, 'Early Corp')]['move'] == {'up': True, 'down': False}
    # A job in the compact list has no card to move.
    assert 'move' not in jobs[job_id(three, 'Old Systems')]


@pytest.mark.parametrize(('name', 'direction'), [('Example Labs', 'up'), ('Early Corp', 'down'), ('Old Systems', 'up')])
def test_a_move_the_plan_does_not_offer_is_refused_and_changes_nothing(three, name, direction):
    raw = canonical(three)
    with pytest.raises(ValueError, match='PANEL_ACTION_UNSUPPORTED'):
        prepare_edit(response(three), panel(three, 'move_job', job_id(three, name), {'direction': direction}))
    assert canonical(three) == raw


@pytest.mark.parametrize('values', [{}, {'direction': 'left'}, {'direction': 'up', 'extra': 'x'}])
def test_a_move_needs_one_known_direction(three, values):
    with pytest.raises(ValueError):
        RichPanelRequest.model_validate(panel(three, 'move_job', job_id(three, 'Middle Inc'), values).operations[0].command
            .model_dump(by_alias=True))


def test_a_move_never_crosses_the_title_or_enters_the_compact_list(three):
    lists = job_lists(three.project)
    assert len(lists) == 1
    views = {block.presentation.view_key for block in lists[0][1]}
    assert views == {'projects'}
    moved = move(three, 'Early Corp', 'up', 'move-a')
    region = next(region for region in moved.project.document.regions if any(block.id == lists[0][1][0].id for block in region.blocks))
    keys = [block.presentation.view_key if block.presentation else None for block in region.blocks]
    # The view title still stands right before the first card.
    assert keys[keys.index('projects')] == 'projects' and region.blocks[keys.index('projects')].type == 'heading'


def test_a_move_is_never_refused_because_of_dates_and_flags_follow(three):
    moved = move(three, 'Early Corp', 'up', 'move-flag')
    plan = panel_plan(moved.project)
    # Early Corp (2012) now stands above Middle Inc (2017): Middle Inc is the card out of order.
    assert plan['sortJobs'] is True
    assert plan['jobs'][job_id(moved, 'Middle Inc')].get('outOfOrder') is True
    assert not plan['jobs'][job_id(moved, 'Early Corp')].get('outOfOrder')
    assert not panel_plan(three.project).get('sortJobs')


def test_flags_skip_an_undated_card_and_equal_dates_give_none(three):
    workspace = add(three, 'Undated', 'add-flag-undated')
    workspace = move(workspace, 'Undated', 'up', 'undated-up-1')
    workspace = move(workspace, 'Undated', 'up', 'undated-up-2')
    assert cards(workspace) == ['Example Labs', 'Undated', 'Middle Inc', 'Early Corp']
    assert not panel_plan(workspace.project).get('sortJobs')
    same = add(workspace, 'Same Year', 'add-same', start='2016', end='2017')
    assert not panel_plan(same.project).get('sortJobs')


def test_sort_puts_each_list_newest_first_undated_last_and_undoes_in_one_step(three):
    workspace = add(three, 'Undated', 'add-sort-undated')
    workspace = move(workspace, 'Undated', 'up', 'sort-up-1')
    workspace = move(workspace, 'Undated', 'up', 'sort-up-2')
    workspace = move(workspace, 'Undated', 'up', 'sort-up-3')
    workspace = move(workspace, 'Early Corp', 'up', 'sort-up-4')
    assert cards(workspace) == ['Undated', 'Example Labs', 'Early Corp', 'Middle Inc']
    assert panel_plan(workspace.project)['sortJobs'] is True
    result = prepared(workspace, panel(workspace, 'sort_jobs', identifier='sort'))
    assert {step.kind for step in result.mutation.steps} == {'move_block'}
    sorted_workspace = result.preview.workspace
    assert cards(sorted_workspace) == ['Example Labs', 'Middle Inc', 'Early Corp', 'Undated']
    plan = panel_plan(sorted_workspace.project)
    assert 'sortJobs' not in plan and not any(job.get('outOfOrder') for job in plan['jobs'].values())
    restored = restore(workspace, result)
    assert cards(restored) == cards(workspace)
    redo = inverse_template_mutation(sorted_workspace, restored, origin_action_id=result.mutation.action_id,
        mutation_id='redo-sort', session_id='session', action_token=3, kind='redo')
    replayed, _ = apply_rich_mutation(restored, redo, history_authorization=authorization(restored, redo))
    assert cards(replayed) == cards(sorted_workspace)
    assert semantic(replayed.project.document) == semantic(sorted_workspace.project.document)


def test_a_sort_with_nothing_to_do_changes_nothing(three):
    assert prepare_edit(response(three), panel(three, 'sort_jobs', identifier='sort-none')).mutation is None


def test_a_move_redoes_after_its_undo(three):
    before = three
    result = prepared(before, panel(before, 'move_job', job_id(before, 'Middle Inc'), {'direction': 'down'}, 'move-redo'))
    after = result.preview.workspace
    assert cards(after) == ['Example Labs', 'Early Corp', 'Middle Inc']
    restored = restore(before, result)
    redo = inverse_template_mutation(after, restored, origin_action_id=result.mutation.action_id,
        mutation_id='redo-move', session_id='session', action_token=3, kind='redo')
    replayed, _ = apply_rich_mutation(restored, redo, history_authorization=authorization(restored, redo))
    assert cards(replayed) == cards(after)


def test_a_date_change_leaves_the_card_in_place_and_only_changes_the_flags(three):
    record = next(value for value in three.project.facts.records if value.id == job_id(three, 'Early Corp'))
    key = f'period:{record.periods[0].id}:end'
    result = prepared(three, request(three, operation='edit', kind=None, record_id=record.id,
        values={key: '2030'}, identifier='edit-date'))
    current = result.preview.workspace
    assert cards(current) == cards(three)
    plan = panel_plan(current.project)
    assert plan['sortJobs'] is True and plan['jobs'][record.id]['outOfOrder'] is True


def test_overlaps_name_the_other_jobs_in_row_order_and_skip_the_job_itself(three):
    workspace = add(three, 'Parallel', 'add-parallel', start='2016', end='2021')
    jobs = panel_plan(workspace.project)['jobs']
    parallel = job_id(workspace, 'Parallel')
    assert [employer(workspace.project, value) for value in jobs[parallel]['overlaps']] == ['Example Labs', 'Middle Inc']
    assert jobs[job_id(workspace, 'Example Labs')]['overlaps'] == [parallel]
    assert 'overlaps' not in jobs[job_id(workspace, 'Early Corp')]
    # Two periods of one job that overlap each other give no warning.
    record = next(value for value in workspace.project.facts.records if value.id == job_id(workspace, 'Early Corp'))
    copy = workspace.model_copy(deep=True)
    own = next(value for value in copy.project.facts.records if value.id == record.id)
    own.periods.append(period('2011', '2013', identifier='second'))
    assert 'overlaps' not in job_warnings(copy.project)[0][record.id]


def test_the_date_check_gives_the_form_warnings_and_writes_nothing(three):
    raw = canonical(three)
    middle = next(value for value in three.project.facts.records if value.id == job_id(three, 'Middle Inc'))
    key = f'period:{middle.periods[0].id}:'
    found = check_dates(three.project, middle.id, {key + 'start': '2019', key + 'end': '2021', key + 'present': ''})
    assert found == {'schemaVersion': 1, 'warnings': [
        {'kind': 'overlap', 'recordId': job_id(three, 'Example Labs'), 'period': '03.2020 – 11.2023'}]}
    reversed_dates = check_dates(three.project, middle.id, {key + 'start': '2017', key + 'end': '2015'})
    assert reversed_dates['warnings'] == [{'kind': 'reversed', 'periodId': middle.periods[0].id}]
    # A current period has no end to compare; its open end overlaps the jobs after its start.
    current = check_dates(three.project, None, {'start': '2011', 'end': '2005', 'present': 'по настоящее время'})
    assert [item['kind'] for item in current['warnings']] == ['overlap', 'overlap', 'overlap']
    assert check_dates(three.project, None, {'start': 'весна', 'end': ''})['warnings'] == []
    assert canonical(three) == raw
    with pytest.raises(ValueError, match='DATE_CHECK_INVALID'):
        check_dates(three.project, None, {'employer': 'x'})
    with pytest.raises(ValueError, match='DATE_CHECK_INVALID'):
        check_dates(three.project, middle.id, {'period:other:start': '2020'})
    with pytest.raises(ValueError, match='DATE_CHECK_INVALID'):
        check_dates(three.project, 'missing', {})


@pytest.mark.parametrize('dates', [{'start': '2025', 'end': '2019'}, {'start': '2099', 'end': ''}, {'start': 'когда-то', 'end': 'потом'},
    {'start': '', 'end': '2020'}, {'start': '13.2020', 'end': '0000'}])
def test_a_period_date_is_saved_as_the_user_gave_it(two_column, dates):
    current = add(two_column, 'As Given', 'add-as-given', **dates)
    record = next(value for value in current.project.facts.records if value.id == job_id(current, 'As Given'))
    assert (record.periods[0].start.raw_text, record.periods[0].end.raw_text) == (dates['start'], dates['end'])


def test_a_docx_of_a_resume_with_warnings_has_no_warning_text(three, tmp_path):
    from packages.resume_core.models.template_render import TemplateRenderRequestV1, snapshot_identity
    from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
    from packages.resume_core.responses.template_export import capture_export
    from tests.templates.test_captured_docx import emitted, xml
    workspace = add(move(three, 'Early Corp', 'up', 'docx-move'), 'Parallel', 'docx-parallel', start='2016', end='2021')
    plan = panel_plan(workspace.project)
    assert plan['sortJobs'] and any(job.get('overlaps') for job in plan['jobs'].values())
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    request_value = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=workspace.project.template_package)
    text = emitted(xml(render_captured_docx(request_value, tmp_path)))
    assert 'Early Corp' in text and 'Parallel' in text
    assert not any(word in text for word in ('Стоит не по дате', 'Пересекается', 'Расставить', 'Окончание раньше'))
