"""Authored block history deltas keep large unchanged evidence in hash guards, and retained fragment ids restore only
under exact history authorization."""

import pytest

from packages.resume_core.models.rich_document import SourceWitness
from packages.resume_core.models.template_document import PresentedText
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.template_block_patches import block_delta, block_hash, restore_payload
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_preparation import prepare_text_edit
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_template_preparation import command, response
from tests.templates.test_transactions import authorization


def large_workspace():
    value, sources = workspace()
    block = value.project.document.regions[2].blocks[0]
    block.content = [PresentedText(type='text', text='Hi', styles={}, presentation=block.presentation)]
    block.provenance = [SourceWitness(kind='source', id='large-witness', evidence=[{'sourceId': 'source-papers',
        'sourceRevision': 1, 'unitId': 'unit-papers', 'unitRevision': 1, 'text': 'x' * (1024 * 1024)}])]
    for index in range(120):
        copy = block.model_copy(deep=True); copy.id = 'unrelated-' + str(index); copy.provenance = []
        copy.content = [PresentedText(type='text', text='Unrelated text ' + 'z' * 10000, styles={})]
        value.project.document.regions[2].blocks.append(copy)
    value = WorkspaceV7.model_validate(value.model_dump(by_alias=True))
    assert len(canonical(value.project.document)) > 2 * 1024 * 1024
    return value, sources


def test_hash_guards_include_provenance_and_all_payload_values_and_reject_identity_paths():
    before, _ = large_workspace()
    after = before.model_copy(deep=True)
    original = before.project.document.regions[2].blocks[0]
    block = after.project.document.regions[2].blocks[0]; block.content[0].text += '!'
    delta = block_delta(original, block)
    assert len(canonical(delta)) < 1500 and 'large-witness' not in canonical(delta).decode()
    restored = restore_payload(block, delta.after_semantic_hash, delta.before_semantic_hash, delta.inverse_patch)
    assert block_hash(restored) == block_hash(original)
    block.provenance[0].evidence[0].text += 'changed'
    with pytest.raises(ValueError, match='preimage'):
        restore_payload(block, delta.after_semantic_hash, delta.before_semantic_hash, delta.inverse_patch)
    for key in ['id', 'revision', 'children', 'placement']:
        with pytest.raises(ValueError):
            restore_payload(original, block_hash(original), block_hash(original),
                [{'kind': 'set', 'pointer': '/' + key, 'valueWire': 'null'}])


def test_retained_fragment_ids_restore_only_under_exact_history_and_still_reject_collisions():
    before, _ = workspace()
    prepared = prepare_text_edit(response(before), command(before, start=1, end=3, text='X'))
    after = prepared.preview.workspace
    inverse = inverse_template_mutation(before, after, origin_action_id=prepared.mutation.action_id,
        mutation_id='restore-fragments', session_id='session', action_token=2)
    assert any(step.kind == 'restore_authored_block_patch' for step in inverse.steps)
    with pytest.raises(RichMutationFailure, match='STALE_MUTATION'):
        apply_rich_mutation(after, inverse)
    restored, _ = apply_rich_mutation(after, inverse, history_authorization=authorization(after, inverse))
    old_span = before.project.document.regions[2].blocks[0].content[0]
    restored_span = restored.project.document.regions[2].blocks[0].content[0]
    assert restored_span.model_dump(exclude={'synced_fact_revision'}) == old_span.model_dump(exclude={'synced_fact_revision'})
    forged = inverse.model_copy(deep=True); forged.kind = 'typing'; forged.history.kind = 'edit'; forged.history.origin_action_id = None
    with pytest.raises(RichMutationFailure, match='STALE_MUTATION'):
        apply_rich_mutation(after, forged)
    original = before.project.document.regions[2].blocks[0].content[0]
    other = after.project.document.regions[2].blocks[1]
    other.content = [original.model_copy(deep=True)]
    with pytest.raises(RichMutationFailure, match='RICH_PATCH_INVALID'):
        apply_rich_mutation(after, inverse, history_authorization=authorization(after, inverse))
