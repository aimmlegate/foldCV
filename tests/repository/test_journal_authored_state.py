"""Journal undo and redo of authored state the edit path changes together: import issues, a later unrelated action,
shared manual scopes, ownership moves and cascaded deletion; metadata outside the stack stays (G3)."""

import pytest

from packages.resume_core.models.projects import RenameRequestV1
from packages.resume_core.project_repository import RepositoryFailure
from packages.resume_core.template_inverse import semantic
from tests.templates.editor_fixtures import TemplateEditor
from tests.templates.test_materialize import fallback_edit, text
from tests.templates.test_transactions import request


def retype(current, block, value, *, identifier, action):
    length = len(''.join(part.text for part in block.content).encode('utf-16-le')) // 2
    mutation = request(current, [{'kind': 'replace_inline_range', 'blockId': block.id, 'beforeRevision': block.revision,
        'cellId': None, 'field': 'content', 'start': 0, 'end': length,
        'content': [{'type': 'text', 'text': value, 'styles': {}}]}], identifier)
    mutation.action_id = mutation.capture.action_id = action
    return mutation


def test_an_issue_retired_by_an_edit_is_restored_by_undo_and_retired_again_by_redo(tmp_path, monkeypatch):
    editor = TemplateEditor(tmp_path)
    before = editor.current()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('undo must not run template checks')
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload', forbidden)
    mutation = fallback_edit(before)
    editor.commit(mutation)
    edited = editor.current()
    assert [issue.state for issue in edited.project.import_issues] == ['retired', 'active']
    base = edited.project_revision
    undone = editor.undo('local-undo', expected=mutation.action_id)
    assert not undone.replayed
    restored = editor.current()
    assert [issue.state for issue in restored.project.import_issues] == ['active', 'active']
    assert 'Exact human correction' not in text(restored.project.document)
    assert restored.document_revision > edited.document_revision
    again = editor.undo('local-undo', expected=mutation.action_id, base=base)
    assert again.replayed and editor.current() == restored
    with pytest.raises(RepositoryFailure) as reused:
        editor.redo('local-undo', base=base)
    assert reused.value.code == 'MUTATION_ID_REUSED'
    editor.redo('local-redo', expected=mutation.action_id)
    redone = editor.current()
    assert [issue.state for issue in redone.project.import_issues] == ['retired', 'active']
    assert 'Exact human correction' in text(redone.project.document)
    assert redone.project.facts == before.project.facts
    assert redone.project.current_history() == before.project.current_history()
    assert redone.sync_records == before.sync_records


def test_undoing_a_later_unrelated_action_keeps_the_earlier_one_which_then_undoes(tmp_path):
    editor = TemplateEditor(tmp_path)
    first = fallback_edit(editor.current())
    editor.commit(first)
    current = editor.current()
    heading = next(block for block in current.project.document.blocks() if block.type == 'heading')
    original = ''.join(part.text for part in heading.content)
    editor.commit(retype(current, heading, 'Human heading', identifier='heading-edit', action='heading-action'))
    editor.undo('undo-heading', expected='heading-action')
    kept = editor.current()
    assert 'Exact human correction' in text(kept.project.document) and 'Human heading' not in text(kept.project.document)
    assert ''.join(part.text for part in next(block for block in kept.project.document.blocks() if block.id == heading.id).content) == original
    editor.undo('undo-first', expected=first.action_id)
    restored = editor.current()
    assert 'Exact human correction' not in text(restored.project.document)
    assert [issue.state for issue in restored.project.import_issues] == ['active', 'active']


def test_a_rename_between_an_edit_and_its_undo_keeps_the_new_title(tmp_path):
    editor = TemplateEditor(tmp_path)
    mutation = fallback_edit(editor.current())
    editor.commit(mutation)
    editor.service.rename(editor.project, RenameRequestV1(editorToken=editor.token,
        baseRevision=editor.current().project_revision, title='Independent metadata'))
    assert editor.history_state()['undo']['actionId'] == mutation.action_id
    editor.undo('undo-after-rename', expected=mutation.action_id)
    undone = editor.current()
    assert undone.title == 'Independent metadata' and undone.project.import_issues[0].state == 'active'


@pytest.mark.parametrize('case', ['joined_scope', 'owner_move', 'owner_delete'])
def test_shared_scopes_ownership_moves_and_cascaded_deletion_undo_and_redo_exactly(case, tmp_path):
    from packages.resume_core.template_authoring import move_occurrence_steps
    from tests.templates.test_builtin_scopes import joined_edit, scoped_workspace
    from tests.templates.test_relation_transactions import owner_sections, related_workspace
    before, sources = scoped_workspace() if case == 'joined_scope' else related_workspace()
    if case == 'owner_move':
        before = owner_sections(before)
    if case == 'joined_scope':
        mutation, _scope = joined_edit(before)
    elif case == 'owner_move':
        steps, conflicts = move_occurrence_steps(before, 'block-paper-a', 'owner-b')
        assert not conflicts
        mutation = request(before, steps, 'move-owned')
    else:
        steps = [{'kind': 'remove_record', 'recordId': 'employer-a', 'beforeRevision': 1}]
        steps.extend({'kind': 'remove_block', 'blockId': block.id, 'beforeRevision': block.revision}
            for block in before.project.document.regions[2].blocks)
        mutation = request(before, steps, 'delete-owned')
    editor = TemplateEditor(tmp_path, before, sources)
    editor.commit(mutation)
    saved = editor.current()
    editor.undo('undo-owned', expected=mutation.action_id)
    undone = editor.current()
    assert semantic(undone.project.document) == semantic(before.project.document)
    assert semantic(undone.project.facts.records) == semantic(before.project.facts.records)
    assert semantic(undone.project.facts.extensions) == semantic(before.project.facts.extensions)
    assert undone.project.facts.relations == before.project.facts.relations
    assert undone.project.facts.builtin_manual_scopes == before.project.facts.builtin_manual_scopes
    assert undone.project.facts.observations == before.project.facts.observations
    editor.redo('redo-owned', expected=mutation.action_id)
    redone = editor.current()
    assert semantic(redone.project.document) == semantic(saved.project.document)
    assert semantic(redone.project.facts.records) == semantic(saved.project.facts.records)
    assert semantic(redone.project.facts.extensions) == semantic(saved.project.facts.extensions)
    assert redone.project.facts.builtin_manual_scopes == saved.project.facts.builtin_manual_scopes
