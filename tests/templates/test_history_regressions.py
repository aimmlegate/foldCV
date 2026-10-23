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


def test_two_edits_of_one_field_undo_and_redo_in_order_through_the_writer(tmp_path):
    # Undo advances the field's synced fact revision; the earlier edit's history guard must not read it as a change.
    from packages.resume_core.models.template_writer import WriterPrepareEditV2
    from tests.templates.test_compact_save import compact_command
    from tests.templates.test_template_local_history import history_request
    from tests.templates.test_template_preparation import command
    from tests.templates.test_template_writers import TemplateWriterFixture
    before, sources = workspace()
    fixture = TemplateWriterFixture(tmp_path, before, sources)
    def save(start, end, text, identifier, cursor):
        value = command(fixture.current(), start=start, end=end, text=text)
        value.client_mutation_id = value.capture.action_id = identifier
        value.capture.session_id = fixture.proof.session_id
        prepared = fixture.writers.prepare_edit_delta(fixture.project, WriterPrepareEditV2(schemaVersion=2, proof=fixture.proof,
            preparation=value))
        return fixture.writers.save(fixture.project, compact_command(fixture, prepared, cursor), originals=fixture.originals)
    def shown():
        return ''.join(part.text for part in fixture.current().project.document.regions[2].blocks[0].content)
    first = save(0, 6, 'One', 'first', 1)
    second = save(0, 3, 'Two', 'second', 2)
    assert shown() == 'Two title'
    for ack, identifier, expected in [(second.local_history_ack, 'undo-second', 'One title'),
            (first.local_history_ack, 'undo-first', 'Shared title')]:
        undone = fixture.writers.local_history_command(fixture.project, history_request(fixture, ack, identifier=identifier),
            originals=fixture.originals)
        assert shown() == expected
    fixture.writers.local_history_command(fixture.project, history_request(fixture, undone.local_history_ack, 'redo', 'redo-first'),
        originals=fixture.originals)
    assert shown() == 'One title'
    title = next(cell for record in fixture.current().project.facts.extensions if record.id == 'paper-a'
        for cell in record.cells if cell.field_key == 'title')
    assert title.raw_input == 'One title'
    assert all(part.synced_fact_revision == title.revision for part in fixture.current().project.document.regions[2].blocks[0].content)
