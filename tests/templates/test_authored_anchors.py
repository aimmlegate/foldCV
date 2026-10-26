"""Structural edits retain exact import ledger anchors and scoped history."""

from copy import deepcopy

import pytest

from packages.resume_core.models.template_workspace import SpanCoverage
from packages.resume_core.rich_dependencies import dependency
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.template_anchors import anchor_steps, coverage_address, coverage_target, issue_target
from packages.resume_core.template_authoring import copy_blocks, merge_blocks, split_block
from packages.resume_core.template_dependencies import selector
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_local_history import changes, restore, values
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_transactions import authorization, issue, request


def anchored():
    before, originals = workspace()
    project = before.project
    block = project.document.regions[2].blocks[0]
    span = project.facts.extensions[0].cells[0].evidence[0]
    row = SpanCoverage(span=span, itemHandle='handle-a', blockIds=[block.id], disposition='accepted', reason=None)
    project.import_coverage = [row, row.model_copy(deep=True)]
    project.import_issues = [issue('issue-a', 'paper-a')]
    return type(before).model_validate(before.model_dump(by_alias=True)), originals


def put(block, before, *, previous=None, new=False):
    return {'kind': 'put_block', 'parentId': 'main', 'afterId': previous,
        'beforeRevision': None if new else next(value.revision for value in before.project.document.blocks() if value.id == block.id),
        'block': block.model_dump(by_alias=True)}


def split_request(before, identifier='split'):
    block = before.project.document.regions[2].blocks[0]
    left, right = split_block(block, 7)
    steps = [put(left, before), put(right, before, previous=left.id, new=True)]
    steps += [step.model_dump(by_alias=True) for step in anchor_steps(before.project, {block.id: [left.id, right.id]})]
    return request(before, steps, identifier), right.id


def test_duplicate_coverage_rows_select_exact_index_and_share_sequence_guard():
    before, _ = anchored()
    first, second = coverage_target(before.project, 0), coverage_target(before.project, 1)
    assert first.coverage_identity_hash == second.coverage_identity_hash
    assert first.coverage_sequence_hash == second.coverage_sequence_hash
    changed, _ = apply_rich_mutation(before, request(before, [{'kind': 'set_authored_anchors',
        'target': second.model_dump(by_alias=True), 'beforeBlockIds': ['block-paper-a'], 'afterBlockIds': []}]))
    assert changed.project.import_coverage[0] == before.project.import_coverage[0]
    assert changed.project.import_coverage[1].block_ids == []
    assert changed.project.import_coverage[1].disposition == 'accepted'
    assert changed.project.import_issues == before.project.import_issues


def test_split_merge_and_undo_redo_restore_anchor_lists_without_retiring_issue():
    before, _ = anchored()
    mutation, right_id = split_request(before)
    split, _ = apply_rich_mutation(before, mutation)
    expected = ['block-paper-a', right_id]
    assert [row.block_ids for row in split.project.import_coverage] == [expected, expected]
    assert split.project.import_issues[0].block_ids == expected
    assert split.project.import_issues[0].lifecycle_id == before.project.import_issues[0].lifecycle_id
    assert split.project.import_issues[0].state == 'active'
    leading, trailing = split.project.document.regions[2].blocks[:2]
    merged = merge_blocks(leading, trailing)
    steps = [put(merged, split), {'kind': 'remove_block', 'blockId': trailing.id, 'beforeRevision': trailing.revision}]
    steps += [step.model_dump(by_alias=True) for step in anchor_steps(split.project, {trailing.id: [leading.id]})]
    joined, _ = apply_rich_mutation(split, request(split, steps, 'merge'))
    assert [row.block_ids for row in joined.project.import_coverage] == [['block-paper-a']] * 2
    undo = inverse_template_mutation(split, joined, origin_action_id='merge', mutation_id='undo', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(joined, undo, history_authorization=authorization(joined, undo))
    assert [row.block_ids for row in restored.project.import_coverage] == [expected, expected]
    assert restored.project.import_issues == split.project.import_issues
    redo = inverse_template_mutation(joined, restored, origin_action_id='merge', mutation_id='redo', session_id='session', action_token=3, kind='redo')
    replayed, _ = apply_rich_mutation(restored, redo, history_authorization=authorization(restored, redo))
    assert replayed.project.import_coverage == joined.project.import_coverage
    assert replayed.project.import_issues == joined.project.import_issues
    assert before.project.document.regions[2].blocks[0].content[0].text == 'Shared title'


def test_copy_preserves_source_anchors_and_removing_one_occurrence_keeps_cell_issue():
    before, _ = anchored()
    block = before.project.document.regions[2].blocks[0]
    copied = copy_blocks(before.project, [block])[0]
    duplicated, _ = apply_rich_mutation(before, request(before, [put(copied, before, previous=block.id, new=True)], 'copy'))
    assert duplicated.project.import_coverage == before.project.import_coverage
    assert duplicated.project.import_issues == before.project.import_issues
    steps = [{'kind': 'remove_block', 'blockId': block.id, 'beforeRevision': block.revision}]
    steps += [step.model_dump(by_alias=True) for step in anchor_steps(duplicated.project, {block.id: []})]
    removed, _ = apply_rich_mutation(duplicated, request(duplicated, steps, 'remove'))
    assert all(row.block_ids == [] and row.disposition == 'accepted' for row in removed.project.import_coverage)
    assert removed.project.import_issues[0].block_ids == []
    assert removed.project.import_issues[0].state == 'active'
    assert removed.project.facts == before.project.facts
    assert copied.id in {value.id for value in removed.project.document.blocks()}


@pytest.mark.parametrize('change', ['sequence', 'identity', 'before', 'after', 'duplicate', 'lifecycle', 'state', 'fingerprint'])
def test_stale_or_invalid_anchor_rejects_whole_transaction(change):
    before, _ = anchored()
    target = coverage_target(before.project, 0).model_dump(by_alias=True)
    if change in {'lifecycle', 'state', 'fingerprint'}:
        target = issue_target(before.project.import_issues[0]).model_dump(by_alias=True)
        key = {'lifecycle': 'beforeLifecycleId', 'state': 'beforeState', 'fingerprint': 'importedFingerprint'}[change]
        target[key] = 'retired' if change == 'state' else '0' * 64
    elif change in {'sequence', 'identity'}:
        target['coverageSequenceHash' if change == 'sequence' else 'coverageIdentityHash'] = '0' * 64
    step = {'kind': 'set_authored_anchors', 'target': target,
        'beforeBlockIds': [] if change == 'before' else ['block-paper-a'],
        'afterBlockIds': ['missing'] if change == 'after' else []}
    steps = [step, deepcopy(step)] if change == 'duplicate' else [step]
    old = canonical(before)
    with pytest.raises(RichMutationFailure, match='STALE_MUTATION'):
        apply_rich_mutation(before, request(before, steps))
    assert canonical(before) == old


def test_issue_anchor_and_retirement_guards_use_original_lifecycle_in_either_step_order():
    before, _ = anchored()
    imported = before.project.import_issues[0]
    anchor = {'kind': 'set_authored_anchors', 'target': issue_target(imported).model_dump(by_alias=True),
        'beforeBlockIds': imported.block_ids, 'afterBlockIds': []}
    retirement = {'kind': 'set_issue_state', 'issueId': imported.id, 'beforeLifecycleId': imported.lifecycle_id,
        'beforeState': 'active', 'afterLifecycleId': 'retired-life', 'afterState': 'retired',
        'actionId': 'human-edit', 'importedFingerprint': imported.imported_fingerprint}
    block = before.project.document.regions[2].blocks[0].model_copy(deep=True)
    block.content[0].text = 'Exact edit'
    first, _ = apply_rich_mutation(before, request(before, [put(block, before), anchor, retirement]))
    second, _ = apply_rich_mutation(before, request(before, [put(block, before), retirement, anchor]))
    assert first.project == second.project
    assert first.project_revision == second.project_revision
    inverse = inverse_template_mutation(before, first, origin_action_id='human-edit', mutation_id='undo', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(first, inverse, history_authorization=authorization(first, inverse))
    assert restored.project.import_issues == before.project.import_issues


def test_coverage_dependency_and_local_restore_guard_exact_anchor_and_sequence():
    before, _ = anchored()
    mutation, _ = split_request(before)
    after, _ = apply_rich_mutation(before, mutation)
    address = coverage_address(before.project, 0)
    target = selector('coverage_anchor', address)
    old = dependency(before, 'field', target)
    assert dependency(after, 'field', target).fingerprint != old.fingerprint
    delta = changes(before, after)
    assert any(kind == 'coverage_anchor' for kind, _ in delta)
    restored = restore(after, delta)
    assert restored.project.import_coverage == before.project.import_coverage
    assert restored.project.import_issues == before.project.import_issues
    stale = after.model_copy(deep=True)
    stale.project.import_coverage[0].block_ids = []
    from packages.resume_core.background_store import BackgroundFailure
    with pytest.raises(BackgroundFailure, match='DEPENDENCY_CHANGED'):
        restore(stale, delta)
    stale.project.import_coverage.reverse()
    stale.project.import_coverage[0].reason = 'changed-sequence'
    with pytest.raises(ValueError, match='DEPENDENCY_MISSING'):
        dependency(stale, 'field', target)


def writer_split(fixture):
    from packages.resume_core.models.template_writer import WriterMutationV2
    command, _ = split_request(fixture.current())
    command.capture.session_id = fixture.proof.session_id
    return WriterMutationV2(**fixture.advance_request(1, [{'cursor': 1, 'mutation': command}]).model_dump(by_alias=True),
        mutation=command)


def test_existing_writer_undo_redo_retains_coverage_and_issue_anchors(tmp_path):
    from tests.templates.test_template_local_history import history_request
    from tests.templates.test_template_writers import TemplateWriterFixture
    before, originals = anchored()
    fixture = TemplateWriterFixture(tmp_path, before, originals)
    saved = fixture.writers.save(fixture.project, writer_split(fixture), originals=fixture.originals)
    assert saved.local_history_ack is not None
    assert len(saved.workspace.project.import_coverage[0].block_ids) == 2
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, saved.local_history_ack), originals=fixture.originals)
    assert undone.workspace.project.import_coverage == before.project.import_coverage
    assert undone.workspace.project.import_issues == before.project.import_issues
    redone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, undone.local_history_ack, 'redo', 'redo'), originals=fixture.originals)
    assert redone.workspace.project.import_coverage == saved.workspace.project.import_coverage
    assert redone.workspace.project.import_issues == saved.workspace.project.import_issues


def test_interrupted_writer_commit_keeps_prior_document_coverage_and_issue_transaction(tmp_path):
    from tests.templates.test_template_writers import TemplateWriterFixture
    before, originals = anchored()
    fixture = TemplateWriterFixture(tmp_path, before, originals)
    command = writer_split(fixture)
    def interrupt(phase, _project):
        if phase == 'before_workspace_replaced':
            raise SystemExit('synthetic cut')
    fixture.publisher.observer = interrupt
    with pytest.raises(SystemExit, match='synthetic cut'):
        fixture.writers.save(fixture.project, command, originals=fixture.originals)
    fixture.publisher.observer = lambda *_args: None
    fixture.publisher.recover(fixture.project)
    assert canonical(fixture.current()) == canonical(before)
    assert fixture.writers.local_history.openings[fixture.project].cursor == 0


@pytest.mark.parametrize('coherent', [False, True])
def test_private_draft_recovery_requires_anchors_with_document_and_issue_state(tmp_path, coherent):
    from packages.resume_core.background_store import BackgroundFailure
    from packages.resume_core.models.template_writer import WriterCheckpointV2, WriterDraftResolveV2
    from tests.templates.test_template_writers import TemplateWriterFixture
    before, originals = anchored()
    fixture = TemplateWriterFixture(tmp_path, before, originals)
    mutation = writer_split(fixture).mutation
    pending, _ = apply_rich_mutation(before, mutation)
    coverage = pending.project.import_coverage if coherent else before.project.import_coverage
    record = fixture.writers.checkpoint(fixture.project, WriterCheckpointV2(schemaVersion=2, proof=fixture.proof,
        id='anchor-checkpoint', sequence=1, actionCursor=1, baseRevision=before.project_revision,
        baseSha256=fixture.view.workspace_sha256, payload={'schemaVersion': 2,
            'document': pending.project.document.model_dump(by_alias=True), 'facts': pending.project.facts.model_dump(by_alias=True),
            'importIssues': [value.model_dump(by_alias=True) for value in pending.project.import_issues],
            'importCoverage': [value.model_dump(by_alias=True) for value in coverage],
            'outbox': [mutation.model_dump(by_alias=True)], 'assetPins': [],
            'touches': [{'cursor': 1, 'mutation': mutation.model_dump(by_alias=True)}]}))
    command = WriterDraftResolveV2(schemaVersion=2, proof=fixture.proof, id=record.id, sequence=record.sequence,
        payloadSha256=record.payload_sha256, canonicalRevision=before.project_revision,
        canonicalSha256=fixture.view.workspace_sha256, mutation=mutation)
    if not coherent:
        with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
            fixture.writers.use_draft(fixture.project, command, originals=fixture.originals)
        assert fixture.current() == before
    else:
        restored = fixture.writers.use_draft(fixture.project, command, originals=fixture.originals)
        assert restored.workspace.project.import_coverage == pending.project.import_coverage
        assert restored.workspace.project.import_issues == pending.project.import_issues


def test_block_target_retirement_uses_original_anchors_when_the_content_is_removed():
    before, _ = anchored()
    imported = before.project.import_issues[0]
    imported.target_ids = []
    block = before.project.document.regions[2].blocks[0]
    steps = [{'kind': 'remove_block', 'blockId': block.id, 'beforeRevision': block.revision}]
    steps += [step.model_dump(by_alias=True) for step in anchor_steps(before.project, {block.id: []})]
    steps += [{'kind': 'set_issue_state', 'issueId': imported.id, 'beforeLifecycleId': imported.lifecycle_id,
        'beforeState': 'active', 'afterLifecycleId': 'retired-life', 'afterState': 'retired',
        'actionId': 'human-edit', 'importedFingerprint': imported.imported_fingerprint}]
    after, _ = apply_rich_mutation(before, request(before, steps))
    assert after.project.import_issues[0].block_ids == []
    assert after.project.import_issues[0].state == 'retired'


@pytest.mark.parametrize('operation', ['split', 'merge', 'copy', 'alignment', 'marks', 'move', 'fragment_id', 'occurrence_id', 'literal'])
@pytest.mark.parametrize('scope', ['cell', 'block'])
def test_explicit_mutation_cannot_retire_issue_for_content_preserving_authoring(operation, scope):
    before, _ = anchored()
    imported = before.project.import_issues[0]
    imported.target_ids = ['a-title'] if scope == 'cell' else []
    block = before.project.document.regions[2].blocks[0]
    if operation == 'split':
        command, _ = split_request(before)
        steps = [step.model_dump(by_alias=True) for step in command.steps]
    elif operation == 'merge':
        trailing = before.project.document.regions[2].blocks[1]
        merged = merge_blocks(block, trailing)
        steps = [put(merged, before), {'kind': 'remove_block', 'blockId': trailing.id, 'beforeRevision': trailing.revision}]
        steps += [step.model_dump(by_alias=True) for step in anchor_steps(before.project, {trailing.id: [block.id]})]
    elif operation == 'copy':
        copied = copy_blocks(before.project, [block])[0]
        steps = [put(copied, before, previous=block.id, new=True)]
    elif operation == 'move':
        steps = [{'kind': 'move_block', 'blockId': block.id, 'beforeRevision': block.revision,
            'parentId': 'main', 'afterId': 'block-paper-b'}]
    else:
        changed = block.model_copy(deep=True)
        if operation == 'alignment':
            changed.props.alignment = 'right'
        elif operation == 'marks':
            changed.content[0].styles.bold = True
        elif operation == 'fragment_id':
            changed.content[0].binding_id = 'new-fragment-id'
        elif operation == 'occurrence_id':
            changed.content[0].occurrence_id = changed.content[0].binding_root_id = 'new-occurrence'
        else:
            from packages.resume_core.models.template_document import PresentedText
            changed.content = [PresentedText(type='text', text=block.content[0].text, styles={})]
        steps = [put(changed, before)]
    steps += [{'kind': 'set_issue_state', 'issueId': imported.id, 'beforeLifecycleId': imported.lifecycle_id,
        'beforeState': 'active', 'afterLifecycleId': 'retired-life', 'afterState': 'retired',
        'actionId': 'human-edit', 'importedFingerprint': imported.imported_fingerprint}]
    old = canonical(before)
    with pytest.raises(RichMutationFailure, match='STALE_MUTATION'):
        apply_rich_mutation(before, request(before, steps))
    assert canonical(before) == old


def test_real_text_change_can_retire_its_cell_issue_and_preserves_sibling_issue():
    before, _ = anchored()
    before.project.import_issues[0].target_ids = ['a-title']
    sibling = issue('issue-b', 'b-title'); sibling.block_ids = ['block-paper-b']
    before.project.import_issues.append(sibling)
    block = before.project.document.regions[2].blocks[0].model_copy(deep=True)
    block.content[0].text += ' exact human addition'
    imported = before.project.import_issues[0]
    steps = [put(block, before), {'kind': 'set_issue_state', 'issueId': imported.id,
        'beforeLifecycleId': imported.lifecycle_id, 'beforeState': 'active', 'afterLifecycleId': 'retired-life',
        'afterState': 'retired', 'actionId': 'human-edit', 'importedFingerprint': imported.imported_fingerprint}]
    changed, _ = apply_rich_mutation(before, request(before, steps))
    assert changed.project.import_issues[0].state == 'retired'
    assert changed.project.import_issues[1] == sibling


@pytest.mark.parametrize('operation', ['split', 'merge', 'copy', 'alignment'])
def test_unrelated_real_edit_cannot_authorize_retirement_of_preserved_block_scope(operation):
    from packages.resume_core.models.template_document import PresentedText, TemplateParagraphBlock
    before, _ = anchored()
    block = before.project.document.regions[2].blocks[0]
    other = TemplateParagraphBlock(type='paragraph', id='unrelated', revision=1, props={}, children=[],
        content=[PresentedText(type='text', text='Unrelated original text', styles={})], provenance=[],
        presentation=block.presentation)
    before.project.document.regions[2].blocks.append(other)
    imported = before.project.import_issues[0]; imported.target_ids = []
    if operation == 'split':
        command, _ = split_request(before)
        steps = [step.model_dump(by_alias=True) for step in command.steps]
    elif operation == 'merge':
        trailing = before.project.document.regions[2].blocks[1]
        merged = merge_blocks(block, trailing)
        steps = [put(merged, before), {'kind': 'remove_block', 'blockId': trailing.id, 'beforeRevision': trailing.revision}]
        steps += [step.model_dump(by_alias=True) for step in anchor_steps(before.project, {trailing.id: [block.id]})]
    elif operation == 'copy':
        copied = copy_blocks(before.project, [block])[0]
        steps = [put(copied, before, previous=block.id, new=True)]
    else:
        changed = block.model_copy(deep=True); changed.props.alignment = 'right'
        steps = [put(changed, before)]
    changed = other.model_copy(deep=True); changed.content[0].text = 'Actual separate edit'
    steps += [put(changed, before, previous=block.id if operation == 'merge' else 'block-paper-b'),
        {'kind': 'set_issue_state', 'issueId': imported.id,
        'beforeLifecycleId': imported.lifecycle_id, 'beforeState': 'active', 'afterLifecycleId': 'retired-life',
        'afterState': 'retired', 'actionId': 'human-edit', 'importedFingerprint': imported.imported_fingerprint}]
    with pytest.raises(RichMutationFailure, match='STALE_MUTATION'):
        apply_rich_mutation(before, request(before, steps))


def test_history_values_hash_the_coverage_ledger_once(monkeypatch):
    import packages.resume_core.template_anchors as anchors
    before, _originals = anchored()
    row = before.project.import_coverage[0]
    before.project.import_coverage = [row.model_copy(deep=True) for _index in range(300)]
    expected = [coverage_address(before.project, index) for index in range(300)]
    calls, original = [], anchors.coverage_sequence
    monkeypatch.setattr(anchors, 'coverage_sequence', lambda project: calls.append(1) or original(project))
    # Hashing the whole ledger per row made every save quadratic in import coverage size.
    keys = [key for kind, key in values(before) if kind == 'coverage_anchor']
    assert keys == expected and len(calls) == 1
    calls.clear()
    assert restore(before, {}) is not None and len(calls) == 2
    calls.clear()
    steps = anchor_steps(before.project, {row.block_ids[0]: ['block-new']})
    assert sum(step.target.kind == 'coverage' for step in steps) == 300 and len(calls) == 1

