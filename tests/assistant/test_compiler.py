"""Assistant ops become authored operations through the editor's preparation and commit as one undo action."""

import hashlib

import pytest

from packages.resume_core.assistant_compiler import CompileFailure, compile_ops, target_text
from packages.resume_core.models.assistant import ProposeChangesV1
from packages.resume_core.project_journal import snapshot
from packages.resume_core.project_repository import ProjectRepository
from packages.resume_core.rich_fields import inline_groups
from packages.resume_core.rich_mutations import inline_text
from resume_api.projects.service import response_for_workspace
from tests.assistant.fixtures import joined, tabled
from tests.templates.golden.corpus import fixtures

ACTION = 'proposal-under-test'


def stored(root, workspace, sources):
    repository = ProjectRepository(root / 'data')
    repository.create(workspace, blobs=[('sources', key, raw, hashlib.sha256(raw).hexdigest()) for key, raw in sources.items()])
    return repository


def ops(*values):
    return ProposeChangesV1.model_validate({'summary': 'test', 'ops': list(values)}).ops


def commit(repository, project_id, values):
    session = repository.open(project_id)

    def build(committed):
        after, created = compile_ops(committed, values, action_id=ACTION, occupied=session.occupied_ids,
            response_for=response_for_workspace)
        return after, {'created_ids': created}
    return repository.mutate(project_id, base_revision=session.revision, client_mutation_id='apply-' + ACTION,
        request_sha256='0' * 64, action_id=ACTION, kind='edit', build=build)


def text(workspace, block_id, key='content'):
    block = next(value for value in workspace.project.document.blocks() if value.id == block_id)
    return ''.join(inline_text(span) for span in dict(inline_groups(block))[key])


GOLDEN = fixtures()
CASES = {
    'set_block_text': ('scoped', [{'op': 'set_block_text', 'blockId': 'job-label', 'text': 'employer-a, Engineer'}]),
    'replace_text': ('paper', [{'op': 'replace_text', 'blockId': 'block-paper-a', 'find': 'title', 'replace': 'heading'}]),
    'insert_blocks': ('paper', [{'op': 'insert_blocks', 'afterBlockId': 'block-paper-a',
        'blocks': [{'kind': 'heading', 'level': 2, 'text': 'Projects'}, {'kind': 'bullet', 'text': 'Queue'}]}]),
    'delete_blocks': ('paper', [{'op': 'delete_blocks', 'blockIds': ['block-paper-b']}]),
    'move_block': ('paper', [{'op': 'move_block', 'blockId': 'block-paper-b', 'parentId': 'main'}]),
    'format_block': ('anchored', [{'op': 'format_block', 'blockId': 'block-paper-a', 'kind': 'heading', 'level': 2,
        'alignment': 'center'}]),
    'update_fact_builtin': ('scoped', [{'op': 'update_fact', 'recordId': 'employer-a', 'field': 'employer',
        'value': 'Northwind'}]),
    'update_fact_extension': ('paper', [{'op': 'update_fact', 'recordId': 'paper-a', 'field': 'title', 'value': 'Retitled'}]),
    'delete_fact_builtin': ('scoped', [{'op': 'delete_fact', 'recordId': 'employer-b'}]),
    'delete_fact_claim': ('scoped', [{'op': 'delete_fact', 'recordId': 'claim'}]),
    'delete_fact_extension': ('related', [{'op': 'delete_fact', 'recordId': 'paper-a'}]),
    'several_ops': ('paper', [{'op': 'replace_text', 'blockId': 'block-paper-a', 'find': 'Shared', 'replace': 'Common'},
        {'op': 'format_block', 'blockId': 'block-paper-b', 'alignment': 'right'}]),
}


@pytest.mark.parametrize('name', sorted(CASES))
def test_every_op_kind_commits_as_one_undo_action_and_undo_restores_it(tmp_path, name):
    fixture, values = CASES[name]
    workspace, sources = GOLDEN[fixture]
    repository = stored(tmp_path, workspace, sources)
    before = snapshot(repository.read(workspace.project_id))
    commit(repository, workspace.project_id, ops(*values))
    session = repository.open(workspace.project_id)
    assert session.journal.state()['undo']['actionId'] == ACTION
    assert snapshot(repository.read(workspace.project_id)) != before
    repository.history(workspace.project_id, direction='undo', base_revision=session.revision, client_mutation_id='undo-1',
        request_sha256='1' * 64, expected_action_id=ACTION)
    assert snapshot(repository.read(workspace.project_id)) == before
    assert session.journal.state()['undo'] is None


@pytest.mark.parametrize('op', [{'op': 'create_fact', 'kind': 'employment', 'values': {'employer': 'Northwind', 'role': 'Lead'}},
    {'op': 'create_fact', 'kind': 'period', 'jobId': '{job}'}])
def test_employment_and_period_creation_use_the_template_view_and_undo_as_one_action(tmp_path, op):
    from tests.templates.test_panel_creation import employment_workspace, owner
    workspace, sources = employment_workspace()
    job = owner(workspace).props.record_id
    repository = stored(tmp_path, workspace, sources)
    before = snapshot(repository.read(workspace.project_id))
    commit(repository, workspace.project_id, ops({**op, **({'jobId': job} if 'jobId' in op else {})}))
    after = repository.read(workspace.project_id)
    jobs = [record for record in after.project.facts.records if record.kind == 'employment']
    if op['kind'] == 'employment':
        assert any(record.employer.raw_text == 'Northwind' for record in jobs)
    else:
        assert len(next(record for record in jobs if record.id == job).periods) == 2
    session = repository.open(workspace.project_id)
    repository.history(workspace.project_id, direction='undo', base_revision=session.revision, client_mutation_id='undo-1',
        request_sha256='1' * 64, expected_action_id=ACTION)
    assert snapshot(repository.read(workspace.project_id)) == before


def test_a_period_takes_its_dates_and_refuses_an_unknown_value(tmp_path):
    from tests.templates.test_panel_creation import employment_workspace, owner
    workspace, sources = employment_workspace()
    job = owner(workspace).props.record_id
    repository = stored(tmp_path, workspace, sources)
    commit(repository, workspace.project_id, ops({'op': 'create_fact', 'kind': 'period', 'jobId': job,
        'values': {'start': '2020', 'end': '2021'}}))
    record = next(value for value in repository.read(workspace.project_id).project.facts.records if value.id == job)
    assert (record.periods[-1].start.raw_text, record.periods[-1].end.raw_text) == ('2020', '2021')
    with pytest.raises(CompileFailure) as refused:
        compile_ops(workspace, ops({'op': 'create_fact', 'kind': 'period', 'jobId': job, 'values': {'title': 'x'}}),
            action_id=ACTION, occupied=set(), response_for=response_for_workspace)
    assert refused.value.code == 'ASSISTANT_OP_REFUSED'


def test_target_id_is_for_a_technology():
    workspace, _sources = GOLDEN['scoped']
    with pytest.raises(CompileFailure) as refused:
        compile_ops(workspace, ops({'op': 'create_fact', 'kind': 'employment', 'targetId': 'line', 'values': {'employer': 'A'}}),
            action_id=ACTION, occupied=set(), response_for=response_for_workspace)
    assert refused.value.code == 'ASSISTANT_OP_INVALID'


def test_the_preview_of_a_record_shows_its_text_not_a_null_or_a_date_object():
    workspace, _sources = GOLDEN['scoped']
    record = next(value for value in workspace.project.facts.records if value.kind == 'employment')
    assert target_text(workspace, record.id).startswith(f'employer: {record.employer.raw_text}')
    assert 'None' not in target_text(workspace, record.id)


def test_other_fact_kinds_have_no_creation_path_on_v7():
    workspace, _sources = GOLDEN['scoped']
    with pytest.raises(CompileFailure) as refused:
        compile_ops(workspace, ops({'op': 'create_fact', 'kind': 'language', 'values': {'language': 'English'}}),
            action_id=ACTION, occupied=set(), response_for=response_for_workspace)
    assert refused.value.code == 'ASSISTANT_OP_REFUSED'


def test_set_block_text_keeps_field_occurrences_and_replaces_only_the_literal_gaps(tmp_path):
    workspace, sources = joined()
    repository = stored(tmp_path, workspace, sources)
    commit(repository, workspace.project_id, ops({'op': 'set_block_text', 'blockId': 'block-paper-a',
        'text': 'Author of Shared title in Journal North!'}))
    after = repository.read(workspace.project_id)
    block = after.project.document.regions[2].blocks[0]
    assert text(after, 'block-paper-a') == 'Author of Shared title in Journal North!'
    fields = [span for span in block.content if getattr(span, 'field_key', None)]
    assert [(span.field_key, span.text) for span in fields] == [('title', 'Shared title'), ('journal', 'Journal North')]
    assert {span.occurrence_id for span in fields} == {'occurrence-paper-a', 'occurrence-journal'}


def test_set_block_text_refuses_text_that_drops_a_field_and_names_it():
    workspace, _sources = joined()
    with pytest.raises(CompileFailure) as refused:
        compile_ops(workspace, ops({'op': 'set_block_text', 'blockId': 'block-paper-a', 'text': 'By Shared title only'}),
            action_id=ACTION, occupied=set(), response_for=response_for_workspace)
    assert refused.value.code == 'ASSISTANT_FIELDS_LOST' and refused.value.detail == ['journal']


@pytest.mark.parametrize('find, code', [('e', 'ASSISTANT_MATCH_NOT_UNIQUE'), ('absent', 'ASSISTANT_MATCH_NOT_UNIQUE'),
    ('title / Journal', 'ASSISTANT_MATCH_CROSSES_SPAN')])
def test_replace_text_needs_one_match_inside_one_span(find, code):
    workspace, _sources = joined()
    with pytest.raises(CompileFailure) as refused:
        compile_ops(workspace, ops({'op': 'replace_text', 'blockId': 'block-paper-a', 'find': find, 'replace': 'x'}),
            action_id=ACTION, occupied=set(), response_for=response_for_workspace)
    assert refused.value.code == code


def test_table_cells_and_image_captions_are_addressed_by_cell_and_field(tmp_path):
    workspace, sources = tabled()
    repository = stored(tmp_path, workspace, sources)
    commit(repository, workspace.project_id, ops(
        {'op': 'set_block_text', 'blockId': 'block-paper-a', 'cellId': 'cell-a', 'text': 'New cell text'},
        {'op': 'replace_text', 'blockId': 'image-block', 'field': 'caption', 'find': 'Old', 'replace': 'New'}))
    after = repository.read(workspace.project_id)
    assert text(after, 'block-paper-a', 'cell-a') == 'New cell text'
    assert text(after, 'image-block', 'caption') == 'New caption'


def test_an_extension_field_is_edited_through_its_first_occurrence_and_refused_without_one():
    workspace, _sources = joined()
    after, _created = compile_ops(workspace, ops({'op': 'update_fact', 'recordId': 'paper-a', 'field': 'journal',
        'value': 'Journal South'}), action_id=ACTION, occupied=set(), response_for=response_for_workspace)
    assert text(after, 'block-paper-a') == 'By Shared title / Journal South.'
    cell = next(cell for cell in next(value for value in after.project.facts.extensions if value.id == 'paper-a').cells
        if cell.field_key == 'journal')
    assert cell.raw_input == 'Journal South'
    with pytest.raises(CompileFailure) as refused:
        compile_ops(workspace, ops({'op': 'update_fact', 'recordId': 'paper-a', 'field': 'year', 'value': '2025'}),
            action_id=ACTION, occupied=set(), response_for=response_for_workspace)
    assert refused.value.code == 'ASSISTANT_FIELD_WITHOUT_OCCURRENCE'


def test_compiling_never_changes_the_committed_workspace():
    workspace, _sources = joined()
    raw = workspace.model_dump_json(by_alias=True)
    compile_ops(workspace, ops({'op': 'set_block_text', 'blockId': 'block-paper-a', 'text': 'Shared title / Journal North'}),
        action_id=ACTION, occupied=set(), response_for=response_for_workspace)
    assert workspace.model_dump_json(by_alias=True) == raw
