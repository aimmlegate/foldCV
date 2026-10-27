"""Ownership and cascaded deletion use the same document/history transaction."""

from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.models.template_facts import Observation
from packages.resume_core.archive_zip import write_zip
from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_authoring import move_occurrence_steps
from packages.resume_core.models.template_document import TemplateSectionBlock
from packages.resume_core.templates.compiler import canonical, compile_bytes, sha256
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.storage_fixtures import workspace
from tests.templates.test_relations import facts
from tests.templates.test_transactions import authorization, issue, request

import pytest

from packages.resume_core.rich_mutations import RichMutationFailure


def related_workspace():
    value, originals = workspace()
    config = value.project.template_package.definition.model_dump(by_alias=True)
    config['fact_types'][0]['relations'] = [{'kind': kind, 'target_types': ['employers']}
        for kind in ['owned_by', 'extension_of', 'related_to']]
    for identifier, kind in [('employers', 'employment'), ('claims', 'claim')]:
        config['fact_types'].append({'id': identifier, 'schema_version': '1', 'builtin_kind': kind,
            'schema': {'type': 'object', 'properties': {}, 'additionalProperties': False, 'required': []},
            'relations': [{'kind': relation, 'target_types': ['employers']}
                for relation in ['owned_by', 'related_to']] if kind == 'claim' else []})
    value.project.template_package = compile_bytes(canonical(config), BUNDLED_TEMPLATE.parent, original_format='json')
    value.project.facts = facts()
    value.project.facts.observations = [Observation(id='original-owner', itemHandle='handle-a', fieldKey='title',
        rawInput='Retained original owner', typedValue=None, evidence=value.project.facts.extensions[0].cells[0].evidence,
        ownerRelations=[value.project.facts.relations[0]], proposalHash=sha256(b'original'),
        admission='uncertain', receiptIds=[])]
    for block in value.project.document.regions[2].blocks:
        block.presentation.package_hash = value.project.template_package.package_hash
        for inline in block.content:
            inline.presentation.package_hash = value.project.template_package.package_hash
    return WorkspaceV7.model_validate(value.model_dump(by_alias=True)), originals


def test_extension_owned_move_and_builtin_claim_move_are_one_reversible_action():
    before, _ = related_workspace()
    award = before.project.facts.relations[0].model_copy(deep=True)
    award.target_id = 'employer-b'
    claim = {'id': 'claim-owner', 'kind': 'owned_by', 'subjectId': 'claim', 'targetId': 'employer-b',
        'revision': 1, 'active': True}
    changed, _ = apply_rich_mutation(before, request(before, [
        {'kind': 'put_relation', 'beforeRevision': award.revision, 'relation': award.model_dump(by_alias=True)},
        {'kind': 'put_relation', 'beforeRevision': None, 'relation': claim}], 'move-owned'))
    assert changed.project.facts.extensions[0].relations[0].target_id == 'employer-b'
    assert changed.project.facts.extensions[1].relations[0].target_id == 'employer-a'
    assert next(r for r in changed.project.facts.records if r.id == 'claim').job_id == 'employer-b'
    assert changed.project.facts.observations[0].owner_relations[0].target_id == 'employer-a'
    inverse = inverse_template_mutation(before, changed, origin_action_id='move-owned',
        mutation_id='undo-move', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(changed, inverse, history_authorization=authorization(changed, inverse))
    assert restored.project.facts.extensions[0].relations[0].target_id == 'employer-a'
    assert next(r for r in restored.project.facts.records if r.id == 'claim').job_id == 'employer-a'
    assert restored.project.facts.observations == before.project.facts.observations


def test_owner_delete_undo_redo_and_portable_keep_exact_record_and_relation_ids():
    before, sources = related_workspace()
    steps = [{'kind': 'remove_record', 'recordId': 'employer-a', 'beforeRevision': 1}]
    steps += [{'kind': 'remove_block', 'blockId': block.id, 'beforeRevision': block.revision}
        for block in before.project.document.regions[2].blocks]
    deleted, _ = apply_rich_mutation(before, request(before, steps, 'delete-owner'))
    assert {t.record_id for t in deleted.project.facts.tombstones} == {'employer-a', 'claim', 'paper-a', 'paper-b'}
    assert [r.id for r in deleted.project.facts.extensions if r.active] == ['reference']
    inverse = inverse_template_mutation(before, deleted, origin_action_id='delete-owner',
        mutation_id='undo-delete', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(deleted, inverse, history_authorization=authorization(deleted, inverse))
    assert [r.id for r in restored.project.facts.extensions] == ['paper-a', 'paper-b', 'reference']
    assert [b.id for b in restored.project.document.regions[2].blocks] == ['block-paper-a', 'block-paper-b']
    assert {r.id for r in restored.project.facts.records} == {'employer-a', 'employer-b', 'claim'}
    assert all(r.active for r in restored.project.facts.relations)
    redo = inverse_template_mutation(deleted, restored, origin_action_id='delete-owner',
        mutation_id='redo-delete', session_id='session', action_token=3, kind='redo')
    again, _ = apply_rich_mutation(restored, redo, history_authorization=authorization(restored, redo))
    assert {t.record_id for t in again.project.facts.tombstones} == {'employer-a', 'claim', 'paper-a', 'paper-b'}
    transferred, retained, _, _ = open_archive_v7(write_zip(archive_payload_v7(again, sources, {})), 'delete-copy')
    assert transferred.project.facts == again.project.facts and retained == sources
    assert transferred.project.document == again.project.document


def test_deleting_only_an_occurrence_keeps_facts_and_relationships_exact():
    before, _ = related_workspace()
    changed, _ = apply_rich_mutation(before, request(before, [{'kind': 'remove_block',
        'blockId': 'block-paper-a', 'beforeRevision': 1}], 'delete-occurrence'))
    assert changed.project.facts == before.project.facts
    assert [b.id for b in changed.project.document.regions[2].blocks] == ['block-paper-b']


def owner_sections(value):
    first, second = value.project.document.regions[2].blocks
    value.project.document.regions[2].blocks = [TemplateSectionBlock(type='section', id='owner-a', revision=1,
        props={'recordId': 'employer-a'}, content=[], children=[first, second], provenance=[], presentation=first.presentation),
        TemplateSectionBlock(type='section', id='owner-b', revision=1, props={'recordId': 'employer-b'},
            content=[], children=[], provenance=[], presentation=second.presentation)]
    return WorkspaceV7.model_validate(value.model_dump(by_alias=True))


def test_manual_occurrence_move_changes_document_and_owned_fact_in_one_history_action():
    value, _ = related_workspace()
    before = owner_sections(value)
    steps, conflicts = move_occurrence_steps(before, 'block-paper-a', 'owner-b')
    assert not conflicts and [step['kind'] for step in steps] == ['move_block', 'put_relation']
    changed, _ = apply_rich_mutation(before, request(before, steps, 'visual-move'))
    assert changed.project.document.regions[2].blocks[1].children[0].id == 'block-paper-a'
    assert changed.project.facts.extensions[0].relations[0].target_id == 'employer-b'
    assert changed.project.facts.observations == before.project.facts.observations
    inverse = inverse_template_mutation(before, changed, origin_action_id='visual-move',
        mutation_id='undo-visual', session_id='session', action_token=2)
    undone, _ = apply_rich_mutation(changed, inverse, history_authorization=authorization(changed, inverse))
    assert [child.id for child in undone.project.document.regions[2].blocks[0].children] == ['block-paper-a', 'block-paper-b']
    assert undone.project.facts.extensions[0].relations[0].target_id == 'employer-a'


def test_extension_subject_and_complete_owner_moves_keep_their_relationships():
    value, _ = related_workspace()
    before = owner_sections(value)
    for block, destination in [('block-paper-b', 'owner-b'), ('owner-a', 'owner-b'), ('block-paper-a', 'main')]:
        steps, _ = move_occurrence_steps(before, block, destination)
        assert [step['kind'] for step in steps] == ['move_block']
        changed, _ = apply_rich_mutation(before, request(before, steps, 'preserved-' + block))
        assert changed.project.facts == before.project.facts


@pytest.mark.parametrize('action', ['move', 'remove'])
def test_relation_scoped_issue_retires_with_its_relation_and_undo_restores_both(action):
    before, _ = related_workspace()
    relation = before.project.facts.relations[0].model_copy(deep=True)
    warning = issue('owner-warning', relation.id)
    before.project.import_issues = [warning]
    retire = {'kind': 'set_issue_state', 'issueId': warning.id, 'beforeLifecycleId': warning.lifecycle_id,
        'beforeState': 'active', 'afterLifecycleId': 'retired', 'afterState': 'retired',
        'actionId': 'relation-edit', 'importedFingerprint': warning.imported_fingerprint}
    unchanged = {'kind': 'put_relation', 'beforeRevision': relation.revision, 'relation': relation.model_dump(by_alias=True)}
    with pytest.raises(RichMutationFailure):
        apply_rich_mutation(before, request(before, [unchanged, retire], 'relation-edit'))
    if action == 'move':
        relation.target_id = 'employer-b'
        change = {**unchanged, 'relation': relation.model_dump(by_alias=True)}
    else:
        change = {'kind': 'remove_relation', 'beforeRevision': relation.revision, 'relationId': relation.id}
    changed, _ = apply_rich_mutation(before, request(before, [change, retire], 'relation-edit'))
    assert changed.project.import_issues[0].state == 'retired'
    inverse = inverse_template_mutation(before, changed, origin_action_id='relation-edit',
        mutation_id='undo-relation', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(changed, inverse, history_authorization=authorization(changed, inverse))
    assert restored.project.import_issues[0].state == 'active'
    assert restored.project.facts.relations[0].target_id == 'employer-a'
    assert restored.project.facts.relations[0].active
    assert restored.project.facts.observations == before.project.facts.observations


def test_builtin_owner_change_requires_a_matching_effective_relation():
    before, _ = related_workspace()
    relation = {'id': 'claim-owner', 'kind': 'owned_by', 'subjectId': 'claim', 'targetId': 'employer-a',
        'revision': 1, 'active': True}
    before, _ = apply_rich_mutation(before, request(before, [
        {'kind': 'put_relation', 'beforeRevision': None, 'relation': relation}], 'capture-owner'))
    claim = next(record for record in before.project.facts.records if record.id == 'claim').model_copy(deep=True)
    claim.job_id = 'employer-b'
    put = {'kind': 'put_record', 'beforeRevision': claim.revision, 'record': claim.model_dump(by_alias=True)}
    original = before.model_dump_json(by_alias=True)
    with pytest.raises(RichMutationFailure):
        apply_rich_mutation(before, request(before, [put], 'divergent-owner'))
    assert before.model_dump_json(by_alias=True) == original
    bad = before.model_dump(by_alias=True)
    next(record for record in bad['project']['facts']['records'] if record['id'] == 'claim')['jobId'] = 'employer-b'
    with pytest.raises(ValueError, match='ownership disagree'):
        WorkspaceV7.model_validate(bad)
    current = next(value for value in before.project.facts.relations if value.id == 'claim-owner')
    matching = {**relation, 'targetId': 'employer-b'}
    changed, _ = apply_rich_mutation(before, request(before, [put,
        {'kind': 'put_relation', 'beforeRevision': current.revision, 'relation': matching}], 'coherent-owner'))
    assert next(record for record in changed.project.facts.records if record.id == 'claim').job_id == 'employer-b'
    assert next(value for value in changed.project.facts.relations if value.id == 'claim-owner').target_id == 'employer-b'


def test_related_to_builtin_target_never_reassigns_its_owner():
    before, _ = related_workspace()
    relation = {'id': 'claim-reference', 'kind': 'related_to', 'subjectId': 'claim', 'targetId': 'employer-b',
        'revision': 1, 'active': True}
    changed, _ = apply_rich_mutation(before, request(before, [
        {'kind': 'put_relation', 'beforeRevision': None, 'relation': relation}], 'add-reference'))
    claim = next(record for record in changed.project.facts.records if record.id == 'claim')
    assert claim == next(record for record in before.project.facts.records if record.id == 'claim')
    assert claim.job_id == 'employer-a'
    assert changed.project.facts.relations[-1].target_id == 'employer-b'
