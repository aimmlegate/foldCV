"""Application admission decisions preserve handles, siblings and failed parents."""

import pytest

from packages.resume_core.models.template_facts import HandleAllocation, Lineage
from packages.resume_core.template_replacements import apply_accepted_records
from packages.resume_core.templates.compiler import sha256
from tests.templates.storage_fixtures import papers
from tests.templates.human_authority_fixtures import human_papers


def allocation(record):
    return HandleAllocation(operationId='operation', taskId='paper-task', discoveryAttemptId='discovery',
        key=record.item_handle, semanticType=record.semantic_type, discoveryHash=sha256(b'synthetic-discovery'),
        itemHandle=record.item_handle, recordId=record.id, cellIds={cell.field_key: cell.id for cell in record.cells})


def child(parent, name):
    result = parent.model_copy(deep=True)
    result.id, result.item_handle = name, 'handle-' + name
    for cell in result.cells:
        cell.id = name + '-' + cell.field_key
    return result


def test_reordered_accepted_repair_updates_only_second_publication_once():
    before = papers()
    first, second = [record.model_copy(deep=True) for record in before.extensions]
    second.cells[1].raw_input = second.cells[1].typed_value = 'Corrected journal'
    second.cells[1].origin = 'model'
    second.cells[1].admission_receipt_ids = ['retained-review-receipt']
    options = {'accepted_handles': ['handle-a', 'handle-b'], 'expected_revisions': {'handle-a': 1, 'handle-b': 1},
        'action_id': 'accepted-repair'}
    changed = apply_accepted_records(before, [second, first], [allocation(second), allocation(first)], [], **options)
    assert changed.extensions[0] == before.extensions[0]
    assert changed.extensions[1].cells[1].raw_input == 'Corrected journal'
    assert changed.extensions[1].cells[1].revision > before.extensions[1].cells[1].revision
    assert changed.extensions[1].cells[0] == before.extensions[1].cells[0]
    repeated = apply_accepted_records(changed, [second, first], [allocation(second), allocation(first)], [], **options)
    assert repeated == changed
    omitted = apply_accepted_records(before, [second], [allocation(second)], [], **options)
    assert omitted.extensions[0] == before.extensions[0] and len(omitted.extensions) == 2
    selected_field = second.model_copy(deep=True)
    selected_field.cells = [selected_field.cells[1]]
    partial = apply_accepted_records(before, [selected_field], [allocation(second)], [], **options)
    assert partial.extensions[1].cells[0] == before.extensions[1].cells[0]
    assert len(partial.extensions[1].cells) == 5
    assert partial.extensions[1].cells[1].raw_input == 'Corrected journal'
    assert apply_accepted_records(partial, [selected_field], [allocation(second)], [], **options) == partial
    changed_again = selected_field.model_copy(deep=True)
    changed_again.cells[0].raw_input = changed_again.cells[0].typed_value = 'Another journal'
    with pytest.raises(ValueError, match='stale replacement capture'):
        apply_accepted_records(partial, [changed_again], [allocation(second)], [], **options)


def test_split_and_merge_retire_parents_only_after_all_children_are_admitted():
    before = papers()
    one, two = child(before.extensions[0], 'split-one'), child(before.extensions[0], 'split-two')
    split = Lineage(kind='split', parents=['handle-a'], children=[one.item_handle, two.item_handle], attemptId='repair')
    options = {'expected_revisions': {'handle-a': 1}, 'action_id': 'accepted-split'}
    failed = apply_accepted_records(before, [one, two], [allocation(one), allocation(two)], [split],
        accepted_handles=[one.item_handle], **options)
    assert failed == before
    changed = apply_accepted_records(before, [two, one], [allocation(one), allocation(two)], [split],
        accepted_handles=[one.item_handle, two.item_handle], **options)
    assert not changed.extensions[0].active and changed.extensions[1] == before.extensions[1]
    assert {r.item_handle for r in changed.extensions if r.active} == {'handle-b', one.item_handle, two.item_handle}
    combined = child(one, 'merged')
    merge = Lineage(kind='merge', parents=[one.item_handle, two.item_handle], children=[combined.item_handle], attemptId='repair-two')
    merged = apply_accepted_records(changed, [combined], [allocation(combined)], [merge],
        accepted_handles=[combined.item_handle], expected_revisions={one.item_handle: 1, two.item_handle: 1}, action_id='accepted-merge')
    assert {r.item_handle for r in merged.extensions if r.active} == {'handle-b', combined.item_handle}
    assert {t.record_id for t in merged.tombstones} == {'paper-a', one.id, two.id}
    assert merged.extensions[1] == before.extensions[1]
    assert apply_accepted_records(merged, [combined], [allocation(combined)], [merge],
        accepted_handles=[combined.item_handle], expected_revisions={one.item_handle: 1, two.item_handle: 1}, action_id='accepted-merge') == merged


@pytest.mark.parametrize('failure', ['stale_parent', 'recycled_parent', 'duplicate_child', 'wrong_cell_id'])
def test_invalid_or_stale_replacement_keeps_original_exact(failure):
    before = papers()
    one, two = child(before.extensions[0], 'one'), child(before.extensions[0], 'two')
    split = Lineage(kind='split', parents=['handle-a'], children=[one.item_handle, two.item_handle], attemptId='repair')
    revision = 1
    allocations = [allocation(one), allocation(two)]
    if failure == 'stale_parent':
        revision = 2
    elif failure == 'recycled_parent':
        split.children[0] = 'handle-a'
    elif failure == 'duplicate_child':
        split.children[1] = one.item_handle
    else:
        one.cells[0].id = 'worker-selected-id'
    original = before.model_dump_json(by_alias=True)
    with pytest.raises(ValueError):
        apply_accepted_records(before, [one, two], allocations, [split], accepted_handles=[one.item_handle, two.item_handle],
            expected_revisions={'handle-a': revision}, action_id='invalid')
    assert before.model_dump_json(by_alias=True) == original


@pytest.mark.parametrize('kind', ['split', 'merge'])
@pytest.mark.parametrize('state', ['human_raw', 'pending_manual'])
def test_model_lineage_preserves_human_parent_and_independent_sibling(kind, state):
    before = human_papers(state)
    model_source = papers().extensions[0]
    one, two = child(model_source, 'one'), child(model_source, 'two')
    sibling = child(model_source, 'sibling')
    before.extensions.append(sibling)
    changed_sibling = sibling.model_copy(deep=True)
    changed_sibling.cells[0].raw_input = changed_sibling.cells[0].typed_value = 'Accepted sibling correction'
    changed_sibling.cells[0].origin = 'model'
    changed_sibling.cells[0].admission_receipt_ids = ['retained-review-receipt']
    incoming = [one, two] if kind == 'split' else [one]
    parents = ['handle-a'] if kind == 'split' else ['handle-a', 'handle-b']
    link = Lineage(kind=kind, parents=parents, children=[record.item_handle for record in incoming], attemptId='repair')
    incoming.append(changed_sibling)
    after = apply_accepted_records(before, incoming, [allocation(record) for record in incoming], [link],
        accepted_handles=[record.item_handle for record in incoming],
        expected_revisions={record.item_handle: record.revision for record in before.extensions}, action_id='reviewed-lineage')
    assert after.extensions[:2] == before.extensions[:2] and not after.tombstones
    assert len(after.extensions) == 3 and after.manual_scopes == before.manual_scopes
    assert after.extensions[2].cells[0].raw_input == 'Accepted sibling correction'
