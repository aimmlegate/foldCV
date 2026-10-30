"""Facts panel edits outside employment on the Generic F10 import (D113): record fields, technologies in their lines,
education and language removal; Undo restores each, and an action without an adapter is refused with a public code."""

import asyncio
import json

import pytest

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
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
    """The technology record of the first name span in a view; Generic's Focus and group views keep records of their own."""
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
            request(before, 'add', kind='education', values={'institution': 'Other'}),
            request(before, 'add', kind='language', values={'language': 'French'}),
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
    # The Generic pack's icons can be chosen for a row (D122).
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
    """The Generic template with a label line before each job's technologies, as a custom template may declare."""
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
