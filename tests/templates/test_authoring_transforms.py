"""Independent identity and style expectations for generic authoring commands."""

import pytest

from packages.resume_core.models.template_document import FieldOccurrence, PresentedText
from packages.resume_core.rich_fields import occurrences
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.template_authoring import (copy_blocks, copy_fragment, duplicate_entity,
    inserted_paragraph, merge_blocks, split_block)
from packages.resume_core.template_facts import ambiguous_edit
from tests.templates.storage_fixtures import workspace
from tests.templates.test_transactions import request


def test_split_and_remerge_keep_one_cell_and_occurrence_with_distinct_fragments():
    original, _ = workspace()
    block = original.project.document.regions[2].blocks[0]
    left, right = split_block(block, 7)
    assert left.content[0].text == 'Shared '
    assert right.content[0].text == 'title'
    assert left.content[0].binding_id != right.content[0].binding_id
    assert left.content[0].occurrence_id == right.content[0].occurrence_id == 'occurrence-paper-a'
    assert left.content[0].cell_id == right.content[0].cell_id == 'a-title'
    assert right.presentation == left.presentation == block.presentation
    merged = merge_blocks(left, right)
    original.project.document.regions[2].blocks[0] = merged
    group = occurrences(original.project.document)[('paper-a', 'title', 'occurrence-paper-a')]
    assert group.text == 'Shared title'
    assert len(group.spans) == 2


def test_complete_and_partial_copies_have_different_binding_authority():
    original, _ = workspace()
    block = original.project.document.regions[2].blocks[0]
    block.content[0].text = 'Backend Engineer'
    block.content[0].styles.bold = True
    complete = copy_blocks(original.project, [block])[0]
    partial = copy_fragment(original.project, block, 8, 16)
    assert isinstance(complete.content[0], FieldOccurrence)
    assert complete.content[0].cell_id == 'a-title'
    assert complete.content[0].occurrence_id != block.content[0].occurrence_id
    assert complete.id != block.id
    assert isinstance(partial.content[0], PresentedText)
    assert partial.content[0].text == 'Engineer' and partial.content[0].styles.bold
    assert partial.content[0].citations == original.project.facts.extensions[0].cells[0].evidence
    assert partial.presentation == block.presentation
    original.project.document.regions[2].blocks += [complete, partial]
    groups = [g for g in occurrences(original.project.document).values() if g.record_id == 'paper-a']
    assert len(groups) == 2 and [g.text for g in groups] == ['Backend Engineer', 'Backend Engineer']
    assert original.project.facts.extensions[0].cells[0].raw_input == 'Shared title'


def test_copy_only_half_of_an_occurrence_split_across_paragraphs_is_literal():
    original, _ = workspace()
    left, right = split_block(original.project.document.regions[2].blocks[0], 7)
    original.project.document.regions[2].blocks = [left, right]
    partial = copy_blocks(original.project, [right])[0]
    assert isinstance(partial.content[0], PresentedText)
    whole = copy_blocks(original.project, [left, right])
    assert whole[0].content[0].occurrence_id == whole[1].content[0].occurrence_id
    assert whole[0].content[0].occurrence_id != left.content[0].occurrence_id


def test_distinct_field_merge_keeps_cells_and_inline_style_of_trailing_paragraph():
    original, _ = workspace()
    first, second = original.project.document.regions[2].blocks
    second.presentation.overrides.size = 17
    second.props.text_color = '#334455'
    second.props.background_color = '#eeeeee'
    second.content[0].presentation = None
    second.content[0].styles.italic = True
    merged = merge_blocks(first, second)
    assert merged.presentation == first.presentation
    assert [p.cell_id for p in merged.content] == ['a-title', 'b-title']
    assert [p.occurrence_id for p in merged.content] == ['occurrence-paper-a', 'occurrence-paper-b']
    assert merged.content[1].presentation.overrides.size == 17
    assert merged.content[1].styles.italic
    assert merged.content[1].styles.text_color == '#334455'
    assert merged.content[1].styles.background_color == '#eeeeee'
    new = inserted_paragraph(second, 'Human paragraph')
    assert new.presentation.overrides.size == 17
    assert new.id not in {first.id, second.id} and new.content[0].text == 'Human paragraph'


def test_explicit_entity_copy_allocates_new_ids_and_retains_copy_lineage():
    original, _ = workspace()
    record, scopes = duplicate_entity(original.project.facts, 'paper-a', 'copy-entity')
    assert not scopes and record.copy_of_record_id == 'paper-a'
    assert record.id != 'paper-a' and record.item_handle != 'handle-a'
    assert {cell.id for cell in record.cells}.isdisjoint({cell.id for cell in original.project.facts.extensions[0].cells})
    changed, _ = apply_rich_mutation(original, request(original,
        [{'kind': 'put_extension', 'beforeRevision': None, 'record': record.model_dump(by_alias=True)}], 'copy-entity'))
    assert len(changed.project.facts.extensions) == 3
    assert changed.project.facts.extensions[-1].cells[0].typed_value == 'Shared title'
    assert changed.project.facts.extensions[-1].cells[0].origin == 'human'
    assert changed.project.facts.extensions[0] == original.project.facts.extensions[0]


def test_copy_of_pending_manual_entity_keeps_exact_raw_scope_with_new_cell_ids():
    original, _ = workspace()
    original.project.facts = ambiguous_edit(original.project.facts, ['a-title', 'a-journal'],
        'Exact unresolved human input', 'ambiguous', ['block-paper-a'])
    record, scopes = duplicate_entity(original.project.facts, 'paper-a', 'copy-pending')
    assert len(scopes) == 1 and scopes[0].raw_input == 'Exact unresolved human input'
    assert set(scopes[0].cell_ids) == {record.cells[0].id, record.cells[1].id}
    assert scopes[0].id != original.project.facts.manual_scopes[0].id
    steps = [{'kind': 'put_manual_scope', 'scope': scopes[0].model_dump(by_alias=True)},
        {'kind': 'put_extension', 'beforeRevision': None, 'record': record.model_dump(by_alias=True)}]
    copied, _ = apply_rich_mutation(original, request(original, steps, 'copy-pending'))
    assert copied.project.facts.extensions[-1].cells[0].state == 'pending_manual'
    assert copied.project.facts.extensions[-1].cells[0].typed_value is None


def test_portable_state_cannot_forge_cyclic_entity_copy_lineage():
    original, _ = workspace()
    original.project.facts.extensions[0].copy_of_record_id = 'paper-b'
    original.project.facts.extensions[1].copy_of_record_id = 'paper-a'
    with pytest.raises(ValueError, match='cyclic entity copy lineage'):
        type(original).model_validate(original.model_dump(by_alias=True))
