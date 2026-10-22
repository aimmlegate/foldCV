"""Retry and traversal changes cannot change authored output identity."""

import pytest

from packages.resume_core.models.background import WriterProofV1
from packages.resume_core.models.template_document import BoundLink, FieldRef, PresentedText
from packages.resume_core.rich_mutations import cut_inline
from packages.resume_core.template_authoring import copy_blocks, copy_fragment, copy_inline, inserted_paragraph, split_block
from packages.resume_core.template_preparation_ids import EditIdAllocator, existing_ids
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace


def allocator(original, *, op='operation', mutation='mutation', changes=None, occupied=None):
    proof = WriterProofV1(schemaVersion=1, lineage='lineage', epoch=1, incarnation='incarnation',
        sessionId='session', credential='c' * 32)
    if changes:
        proof = proof.model_copy(update=changes)
    return EditIdAllocator(proof, mutation, op, existing_ids(original) if occupied is None else occupied)


def test_named_slots_are_order_independent_and_report_every_result():
    original, _ = workspace()
    first, second = allocator(original), allocator(original)
    a, b = ['copy-block', 'first'], ['copy-block', 'second']
    a1, b1 = first.allocate('block', a), first.allocate('block', b)
    b2, a2 = second.allocate('block', b), second.allocate('block', a)
    assert (a1, b1) == (a2, b2) and a1 != b1
    assert first.created_ids == second.created_ids
    assert first.created_ids == {'operation': {'["copy-block","first"]': a1, '["copy-block","second"]': b1}}
    assert first.allocate('block', a) == a1
    with pytest.raises(ValueError, match='changes purpose'):
        first.allocate('citation', a)


@pytest.mark.parametrize('changes', [{'lineage': 'next'}, {'epoch': 2}, {'incarnation': 'next'}, {'session_id': 'next'}])
def test_every_opening_component_separates_identity(changes):
    original, _ = workspace()
    assert allocator(original).allocate('block', ['insert']) != allocator(original, changes=changes).allocate('block', ['insert'])


def test_operation_and_request_ids_separate_identity_but_credentials_do_not():
    original, _ = workspace()
    value = allocator(original).allocate('block', ['insert'])
    assert value != allocator(original, op='next').allocate('block', ['insert'])
    assert value != allocator(original, mutation='next').allocate('block', ['insert'])
    assert value == allocator(original, changes={'credential': 'z' * 32}).allocate('block', ['insert'])


def test_collisions_fail_without_partial_allocation_or_silent_suffix():
    original, _ = workspace()
    value = allocator(original).allocate('block', ['insert'])
    blocked = allocator(original, occupied={value})
    with pytest.raises(ValueError, match='collides'):
        blocked.allocate('block', ['insert'])
    assert blocked.created_ids == {'operation': {}}


def test_derived_outputs_preserve_exact_selectors_and_cannot_change_identity_or_become_free_ids():
    original,_=workspace();value=allocator(original)
    selector='["fact","new-record","role"]';slot=['builtin-cell','new-record','role']
    assert value.derived('builtin-cell',slot,selector)==selector
    assert value.derived('builtin-cell',slot,selector)==selector
    assert selector in value.created_ids['operation'].values()
    with pytest.raises(ValueError,match='changes purpose or value'):
        value.derived('builtin-cell',slot,'different')
    with pytest.raises(ValueError,match='changes purpose'):
        value.allocate('cell',slot)
    with pytest.raises(ValueError,match='changes purpose'):
        value.allocate('derived:builtin-cell',slot)
    with pytest.raises(ValueError,match='collides'):
        allocator(original,occupied={selector}).derived('builtin-cell',slot,selector)


def test_existing_identifiers_include_nested_mapping_values_and_roots():
    original, _ = workspace()
    identifiers = existing_ids(original)
    for block in original.project.document.blocks():
        assert block.id in identifiers
    assert {'a-title', 'paper-a', 'handle-a', 'occurrence-paper-a'} <= identifiers
    assert 'Shared title' not in identifiers


def test_split_nested_fragments_and_citations_are_exact_on_retry(monkeypatch):
    original, _ = workspace()
    block = original.project.document.regions[2].blocks[0]
    span = block.content[0]
    reference = FieldRef(recordId=span.record_id, fieldKey=span.field_key, cellId=span.cell_id,
        occurrenceId=span.occurrence_id)
    block.content = [BoundLink(type='bound_link', href='https://example.test', content=[span],
        labelBinding=reference, urlBinding=None, presentation=span.presentation)]
    def forbidden():
        pytest.fail('deterministic transforms must not allocate random nested IDs')
    monkeypatch.setattr('uuid.uuid4', forbidden)
    first, retry = allocator(original), allocator(original)
    left, right = split_block(block, 7, id_factory=first)
    repeated = split_block(block, 7, id_factory=retry)
    assert canonical([value.model_dump(by_alias=True) for value in (left, right)]) == canonical([
        value.model_dump(by_alias=True) for value in repeated])
    assert left.content[0].content[0].text == 'Shared '
    assert right.content[0].content[0].text == 'title'
    assert left.content[0].content[0].binding_id != right.content[0].content[0].binding_id
    allocated = set(first.slots.values())
    assert {right.id, left.content[0].content[0].binding_id, right.content[0].content[0].binding_id} <= allocated
    assert first.created_ids == retry.created_ids


def test_copy_reorder_keeps_named_blocks_occurrences_and_fragments_stable(monkeypatch):
    original, _ = workspace()
    blocks = original.project.document.regions[2].blocks
    monkeypatch.setattr('uuid.uuid4', lambda: pytest.fail('random nested copy ID'))
    forward, reverse = allocator(original), allocator(original)
    copied = copy_blocks(original.project, blocks, id_factory=forward)
    reordered = copy_blocks(original.project, list(reversed(blocks)), id_factory=reverse)
    assert canonical([block.model_dump(by_alias=True) for block in copied]) == canonical([
        block.model_dump(by_alias=True) for block in reversed(reordered)])
    assert forward.created_ids == reverse.created_ids
    for old, new in zip(blocks, copied, strict=True):
        assert new.id != old.id
        assert new.content[0].cell_id == old.content[0].cell_id
        assert new.content[0].occurrence_id != old.content[0].occurrence_id


def test_inline_copy_allocates_no_throwaway_block_and_partial_copy_is_literal(monkeypatch):
    original, _ = workspace()
    block = original.project.document.regions[2].blocks[0]
    monkeypatch.setattr('uuid.uuid4', lambda: pytest.fail('random inline copy ID'))
    complete_ids, partial_ids = allocator(original), allocator(original)
    complete = copy_inline(original.project, block.content, id_factory=complete_ids)
    selected = cut_inline(block.content, 7, 12, id_factory=partial_ids, allocation_path=('clipboard', block.id))
    partial = copy_inline(original.project, selected, id_factory=partial_ids)
    assert complete[0].cell_id == 'a-title' and complete[0].occurrence_id != 'occurrence-paper-a'
    assert isinstance(partial[0], PresentedText) and partial[0].text == 'title'
    assert partial[0].citations == original.project.facts.extensions[0].cells[0].evidence
    assert all(not identifier.startswith('block-') for identifier in [*complete_ids.slots.values(), *partial_ids.slots.values()])


def test_fragment_and_insert_retry_preserve_source_presentation(monkeypatch):
    original, _ = workspace()
    block = original.project.document.regions[2].blocks[0]
    monkeypatch.setattr('uuid.uuid4', lambda: pytest.fail('random fragment/insert ID'))
    first, retry = allocator(original), allocator(original)
    copied = copy_fragment(original.project, block, 7, 12, id_factory=first)
    repeated = copy_fragment(original.project, block, 7, 12, id_factory=retry)
    assert canonical(copied) == canonical(repeated)
    assert copied.presentation == block.presentation
    assert inserted_paragraph(block, 'Human', id_factory=first) == inserted_paragraph(block, 'Human', id_factory=retry)


@pytest.mark.parametrize('offset', [0, 2, 4])
@pytest.mark.parametrize('position', [0, 1])
@pytest.mark.parametrize('nested', [False, True])
def test_split_retains_empty_semantic_anchor_once_with_right_boundary_ownership(offset, position, nested):
    original, _ = workspace()
    block = original.project.document.regions[2].blocks[0]
    span = block.content[0]; span.text = ''
    anchor = span
    if nested:
        anchor = BoundLink(type='bound_link', href='https://example.test', content=[span],
            labelBinding=FieldRef(recordId=span.record_id, fieldKey=span.field_key, cellId=span.cell_id,
                occurrenceId=span.occurrence_id), urlBinding=None, presentation=span.presentation)
    tail = PresentedText(type='text', text='Tail', styles={})
    block.content = [anchor, tail] if position == 0 else [tail, anchor]
    type(original).model_validate(original.model_dump(by_alias=True))
    left, right = split_block(block, offset, id_factory=allocator(original))
    def fields(content):
        return [child for part in content for child in (part.content if isinstance(part, BoundLink) else [part])
            if getattr(child, 'cell_id', None) == 'a-title']
    anchors = fields(left.content) + fields(right.content)
    assert len(anchors) == 1 and anchors[0].text == ''
    assert anchors[0].binding_id == span.binding_id
    expected_right = position == 1 or offset == 0
    assert bool(fields(right.content)) == expected_right


def test_split_recovers_empty_nested_field_at_end_of_nonempty_link():
    original, _ = workspace()
    block = original.project.document.regions[2].blocks[0]
    span = block.content[0]; span.text = ''
    block.content = [BoundLink(type='bound_link', href='https://example.test',
        content=[PresentedText(type='text', text='AB', styles={}), span],
        labelBinding=FieldRef(recordId=span.record_id, fieldKey=span.field_key, cellId=span.cell_id,
            occurrenceId=span.occurrence_id), urlBinding=None, presentation=span.presentation),
        PresentedText(type='text', text='CD', styles={})]
    left, right = split_block(block, 2, id_factory=allocator(original))
    assert left.content[0].content[0].text == 'AB' and len(left.content[0].content) == 1
    assert right.content[0].content[0].binding_id == span.binding_id
    assert right.content[1].text == 'CD'
