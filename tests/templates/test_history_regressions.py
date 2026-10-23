"""Cell and subject history preserve identity and order across nested Undo."""

from tests.templates.test_relation_transactions import related_workspace
from tests.templates.storage_fixtures import workspace
from tests.templates.test_transactions import authorization, extension_step, request
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_facts import ambiguous_edit
from packages.resume_core.template_authoring import duplicate_entity
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive


def undo(before, after, action, name):
    inverse = inverse_template_mutation(before, after, origin_action_id=action,
        mutation_id=name, session_id='session', action_token=2)
    return apply_rich_mutation(after, inverse, history_authorization=authorization(after, inverse))[0]


def test_multiple_subject_delete_undo_restores_original_order():
    before, _ = related_workspace()
    steps = [{'kind': 'remove_record', 'recordId': record.id, 'beforeRevision': record.revision}
        for record in before.project.facts.records if record.kind == 'employment']
    steps += [{'kind': 'remove_block', 'blockId': block.id, 'beforeRevision': block.revision}
        for block in before.project.document.regions[2].blocks]
    deleted, _ = apply_rich_mutation(before, request(before, steps, 'delete-both'))
    restored = undo(before, deleted, 'delete-both', 'undo-delete-both')
    assert [r.id for r in restored.project.facts.records] == [r.id for r in before.project.facts.records]


def test_undo_new_cell_after_undoing_later_shared_scope():
    before, sources = workspace()
    supplied = before.project.facts.extensions[0].cells.pop(1)
    added_record = before.project.facts.extensions[0].model_copy(deep=True)
    supplied.raw_input, supplied.typed_value = 'Human journal', None
    supplied.state, supplied.origin, supplied.user_corrected = 'human_raw', 'human', True
    supplied.evidence = []
    added_record.cells.append(supplied)
    added, _ = apply_rich_mutation(before, request(before, [extension_step(before, added_record)], 'add-cell'))
    scoped_facts = ambiguous_edit(added.project.facts, ['a-title', 'a-journal'],
        'Shared manual text', 'shared-edit', ['block-paper-a'], scope_id='shared-scope')
    edited, _ = apply_rich_mutation(added, request(added, [
        extension_step(added, scoped_facts.extensions[0]),
        {'kind': 'put_manual_scope', 'scope': scoped_facts.manual_scopes[0].model_dump(by_alias=True)}], 'shared-edit'))
    restored_add = undo(added, edited, 'shared-edit', 'undo-shared-edit')
    inverse = inverse_template_mutation(before, restored_add, origin_action_id='add-cell',
        mutation_id='undo-add-cell', session_id='session', action_token=3)
    restored, _ = apply_rich_mutation(restored_add, inverse, history_authorization=authorization(restored_add, inverse))
    assert [c.id for c in restored.project.facts.extensions[0].cells] == [c.id for c in before.project.facts.extensions[0].cells]
    assert restored.project.facts.extensions[0].retired_cell_ids == {'journal': 'a-journal'}
    transferred, _, _, _ = open_rich_archive(export_rich_archive(restored, sources, {}, {}), 'history-copy')
    assert transferred.project.facts == restored.project.facts
    copied, _ = duplicate_entity(restored.project.facts, 'paper-a', 'copy-after-undo')
    assert not copied.retired_cell_ids
    assert not {cell.id for cell in copied.cells} & {'a-journal', 'a-title'}
    redone_add = undo(restored_add, restored, 'undo-add-cell', 'redo-add-cell')
    assert not redone_add.project.facts.extensions[0].retired_cell_ids
    assert [c.id for c in redone_add.project.facts.extensions[0].cells] == [c.id for c in added.project.facts.extensions[0].cells]
    redone_edit = undo(edited, redone_add, 'undo-shared-edit', 'redo-shared-edit')
    for cell in redone_edit.project.facts.extensions[0].cells:
        if cell.id in {'a-title', 'a-journal'}:
            assert (cell.manual_scope_id, cell.typed_value) == ('shared-scope', None)
    assert redone_edit.project.facts.manual_scopes[-1].raw_input == 'Shared manual text'
