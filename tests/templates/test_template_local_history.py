"""Real writer Undo/Redo needs retained authority and one durable issue transaction."""

import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.models.template_writer import WriterLocalHistoryCommandV2, WriterMutationV2
from packages.resume_core.rich_dependencies import placements
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.templates.compiler import canonical
from tests.templates.test_materialize import text
from tests.templates.test_template_writers import TemplateWriterFixture


def history_request(fixture, ack, direction='undo', identifier='local-undo'):
    state = fixture.jobs.load(fixture.project)
    return WriterLocalHistoryCommandV2(**fixture.advance_request(state.writer.acknowledged_cursor).model_dump(by_alias=True),
        originActionId=ack.action_id, actionGeneration=ack.generation, direction=direction, clientMutationId=identifier)


def edit_again(fixture, *, identifier='next-save', action='next-action', value='Second exact correction', token=1, block_id=None):
    from tests.templates.test_transactions import request
    current = fixture.current()
    block = next(block for block in current.project.document.blocks() if block.id == block_id) if block_id else next(
        block for block in current.project.document.blocks() if 'Exact human correction' in ''.join(part.text for part in block.content))
    command = request(current, [{'kind': 'replace_inline_range', 'blockId': block.id, 'beforeRevision': block.revision,
        'cellId': None, 'field': 'content', 'start': 0, 'end': len(''.join(part.text for part in block.content).encode('utf-16-le')) // 2,
        'content': [{'type': 'text', 'text': value, 'styles': {}}]}], identifier)
    command.action_id, command.capture.action_id = action, action
    command.capture.session_id, command.capture.action_token = fixture.proof.session_id, token
    cursor = fixture.jobs.load(fixture.project).writer.acknowledged_cursor + 1
    return WriterMutationV2(**fixture.advance_request(cursor, [{'cursor': cursor, 'mutation': command}]).model_dump(by_alias=True),
        mutation=command)


def put_block_again(fixture, block, *, action, identifier, token):
    from tests.templates.test_transactions import request
    current = fixture.current()
    actual = next(value for value in current.project.document.blocks() if value.id == block.id)
    parent, previous, _owner = placements(current.project.document)[block.id]
    mutation = request(current, [{'kind': 'put_block', 'parentId': parent, 'afterId': previous,
        'beforeRevision': actual.revision, 'block': block.model_dump(by_alias=True), 'keepChildren': True}], identifier)
    mutation.action_id = mutation.capture.action_id = action
    mutation.capture.session_id, mutation.capture.action_token = fixture.proof.session_id, token
    cursor = fixture.jobs.load(fixture.project).writer.acknowledged_cursor + 1
    return WriterMutationV2(**fixture.advance_request(cursor, [{'cursor': cursor, 'mutation': mutation}]).model_dump(by_alias=True), mutation=mutation)


def test_real_issue_undo_redo_and_exact_duplicate_retire_only_the_original_target(tmp_path, monkeypatch):
    fixture = TemplateWriterFixture(tmp_path)
    before = fixture.current()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('local history must not run template checks')
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload', forbidden)
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    assert saved.local_history_ack.generation == 1
    command = history_request(fixture, saved.local_history_ack)
    undone = fixture.writers.local_history_command(fixture.project, command, originals=fixture.originals)
    assert [issue.state for issue in undone.workspace.project.import_issues] == ['active', 'active']
    assert 'Exact human correction' not in text(undone.workspace.project.document)
    assert undone.workspace.document_revision > saved.workspace.document_revision
    assert undone.local_history_ack.generation == 2
    again = fixture.writers.local_history_command(fixture.project, command, originals=fixture.originals)
    assert again.replayed and again.workspace == undone.workspace and again.mutation_wire == undone.mutation_wire
    with pytest.raises(BackgroundFailure, match='JOB_IDEMPOTENCY_CONFLICT'):
        fixture.writers.local_history_command(fixture.project, command.model_copy(update={'direction': 'redo'}), originals=fixture.originals)
    redo = history_request(fixture, undone.local_history_ack, 'redo', 'local-redo')
    redone = fixture.writers.local_history_command(fixture.project, redo, originals=fixture.originals)
    assert [issue.state for issue in redone.workspace.project.import_issues] == ['retired', 'active']
    assert 'Exact human correction' in text(redone.workspace.project.document)
    assert redone.workspace.project.facts == before.project.facts
    assert redone.workspace.project.current_history() == before.project.current_history()
    assert redone.workspace.sync_records == before.sync_records
    assert not fixture.jobs.load(fixture.project).history_commands and not fixture.jobs.load(fixture.project).inverses


def test_client_supplied_inverse_never_establishes_writer_history_authority(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    before = fixture.current()
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    inverse = inverse_template_mutation(before, saved.workspace, origin_action_id='human-edit',
        mutation_id='forged-local-undo', session_id=fixture.proof.session_id, action_token=2)
    value = WriterMutationV2(**fixture.advance_request(1).model_dump(by_alias=True), mutation=inverse)
    with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
        fixture.writers.save(fixture.project, value, originals=fixture.originals)
    assert fixture.current() == saved.workspace


def test_contiguous_typing_coalesces_earliest_before_latest_after_and_retyping_is_new(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    before = fixture.current()
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    changed = fixture.writers.save(fixture.project, edit_again(fixture, action='human-edit', token=2), originals=fixture.originals)
    assert changed.local_history_ack.action_id == saved.local_history_ack.action_id
    assert changed.local_history_ack.generation == 2
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, changed.local_history_ack), originals=fixture.originals)
    assert text(undone.workspace.project.document) == text(before.project.document)
    assert [issue.state for issue in undone.workspace.project.import_issues] == ['active', 'active']
    redone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, undone.local_history_ack, 'redo', 'local-redo'), originals=fixture.originals)
    assert 'Second exact correction' in text(redone.workspace.project.document)
    first = TemplateMutationV1.model_validate_json(redone.mutation_wire)
    block_id = next(step.block_id for step in first.steps if step.kind == 'restore_authored_block_patch')
    original = next(block for block in before.project.document.blocks() if block.id == block_id)
    retyped = fixture.writers.save(fixture.project, edit_again(fixture, value=''.join(part.text for part in original.content),
        identifier='retyped-save', action='new-human-action', block_id=block_id), originals=fixture.originals)
    assert retyped.workspace.project.import_issues[0].state == 'retired'


def test_unrelated_later_action_undo_preserves_prior_action_then_its_undo_works(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    block = next(block for block in fixture.current().project.document.blocks() if block.type == 'heading')
    changed = fixture.writers.save(fixture.project, edit_again(fixture, block_id=block.id, value='Human heading'), originals=fixture.originals)
    restored_heading = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, changed.local_history_ack), originals=fixture.originals)
    assert 'Exact human correction' in text(restored_heading.workspace.project.document)
    restored = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, saved.local_history_ack, identifier='earlier-undo'), originals=fixture.originals)
    assert 'Exact human correction' not in text(restored.workspace.project.document)
    assert [issue.state for issue in restored.workspace.project.import_issues] == ['active', 'active']


@pytest.mark.parametrize('phase', ['before_workspace_replaced', 'before_local_history_receipt'])
def test_failed_or_interrupted_replay_uses_commit_proof_before_advancing_session_cursor(tmp_path, phase):
    fixture = TemplateWriterFixture(tmp_path)
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    command = history_request(fixture, saved.local_history_ack)
    before = canonical(fixture.current())
    def interrupt(name, _project):
        if name == phase:
            raise SystemExit('synthetic cut')
    target = fixture.publisher if phase == 'before_workspace_replaced' else fixture.writers
    target.observer = interrupt
    with pytest.raises(SystemExit, match='synthetic cut'):
        fixture.writers.local_history_command(fixture.project, command, originals=fixture.originals)
    target.observer = lambda *_args: None
    if phase == 'before_workspace_replaced':
        fixture.publisher.recover(fixture.project)
        assert canonical(fixture.current()) == before
        assert fixture.writers.local_history.openings[fixture.project].cursor == 1
    else:
        replayed = fixture.writers.local_history_command(fixture.project, command, originals=fixture.originals)
        assert replayed.replayed and replayed.local_history_ack.generation == 2
        assert [issue.state for issue in replayed.workspace.project.import_issues] == ['active', 'active']
        assert fixture.writers.local_history.openings[fixture.project].cursor == 0


def test_restart_or_detach_never_rebuilds_local_authority_from_saved_mutations(tmp_path):
    from packages.resume_core.background_writers import WriterSessions
    fixture = TemplateWriterFixture(tmp_path)
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    request = history_request(fixture, saved.local_history_ack)
    fresh = WriterSessions(fixture.publisher)
    fresh.live = dict(fixture.writers.live)
    with pytest.raises(BackgroundFailure, match='REQUEST_EXPIRED'):
        fresh.local_history_command(fixture.project, request, originals=fixture.originals)
    assert not fresh.local_history.openings
    fixture.writers.detach(fixture.project, fixture.advance_request(1))
    assert fixture.project not in fixture.writers.local_history.openings


def test_stale_snapshot_and_equal_text_intervening_write_cannot_restore_authority(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    command = history_request(fixture, saved.local_history_ack)
    def rename(workspace):
        workspace.title = 'Independent metadata'
        workspace.project_revision += 1
        workspace.project.revision = workspace.project_revision
    current = fixture.current()
    after = current.model_copy(deep=True)
    rename(after)
    fixture.publisher.snapshot(fixture.project, digest_bytes(current), after, 'independent-title', originals=fixture.originals)
    with pytest.raises(BackgroundFailure, match='DEPENDENCY_CHANGED'):
        fixture.writers.local_history_command(fixture.project, command, originals=fixture.originals)
    current = fixture.current()
    block = next(block for block in current.project.document.blocks() if 'Exact human correction' in ''.join(part.text for part in block.content))
    from tests.templates.test_transactions import request
    parent, previous, _owner = placements(current.project.document)[block.id]
    equal = request(current, [{'kind': 'put_block', 'parentId': parent,
        'afterId': previous, 'beforeRevision': block.revision, 'block': block.model_dump(by_alias=True), 'keepChildren': True}], 'equal-external')
    fixture.publisher.manual(fixture.project, equal, originals=fixture.originals)
    with pytest.raises(BackgroundFailure, match='DEPENDENCY_CHANGED'):
        fixture.writers.local_history_command(fixture.project,
            history_request(fixture, saved.local_history_ack), originals=fixture.originals)


def test_validated_own_touch_watermark_preserves_contiguous_action_authority(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    first = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    later = edit_again(fixture, action='human-edit', token=2)
    from packages.resume_core.models.template_writer import WriterAdvanceV2
    touch = WriterAdvanceV2.model_validate(later.model_dump(by_alias=True, exclude={'mutation'}))
    fixture.writers.flush(fixture.project, touch)
    saved = fixture.writers.save(fixture.project, later, originals=fixture.originals)
    assert saved.local_history_ack.generation == first.local_history_ack.generation + 1
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, saved.local_history_ack), originals=fixture.originals)
    assert 'Second exact correction' not in text(undone.workspace.project.document)
    assert undone.workspace.project.import_issues[0].state == 'active'


def test_fresh_metadata_snapshot_preserves_unrelated_title_during_local_undo(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    before = fixture.current()
    after = before.model_copy(deep=True)
    after.title = 'Independent metadata'
    after.project_revision += 1
    after.project.revision = after.project_revision
    fixture.publisher.snapshot(fixture.project, digest_bytes(before), after, 'metadata-save', originals=fixture.originals)
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, saved.local_history_ack), originals=fixture.originals)
    assert undone.workspace.title == after.title and undone.workspace.project.import_issues[0].state == 'active'


def test_delayed_reconciliation_cannot_attach_after_undo_redo_even_with_refreshed_revision_guards(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, saved.local_history_ack), originals=fixture.originals)
    redone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, undone.local_history_ack, 'redo', 'redo-action'), originals=fixture.originals)
    delayed = edit_again(fixture, identifier='delayed-reconciliation', action='human-edit', token=1)
    delayed.mutation.kind = 'reconciliation'
    before = canonical(fixture.current())
    with pytest.raises(BackgroundFailure, match='DEPENDENCY_CHANGED'):
        fixture.writers.save(fixture.project, delayed, originals=fixture.originals)
    assert canonical(fixture.current()) == before
    assert redone.workspace.project.import_issues[0].state == 'retired'


@pytest.mark.parametrize('case', ['equal_write', 'coalesced_to_original'])
def test_no_effect_own_write_grants_no_inverse_and_never_blocks_the_prior_action(tmp_path, case):
    from tests.templates.test_transactions import request
    fixture = TemplateWriterFixture(tmp_path)
    first = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    block = next(block for block in fixture.current().project.document.blocks() if block.type == 'heading')
    if case == 'equal_write':
        parent, previous, _owner = placements(fixture.current().project.document)[block.id]
        mutation = request(fixture.current(), [{'kind': 'put_block', 'parentId': parent, 'afterId': previous,
            'beforeRevision': block.revision, 'block': block.model_dump(by_alias=True), 'keepChildren': True}], 'equal-own')
        mutation.capture.session_id = fixture.proof.session_id
        command = WriterMutationV2(**fixture.advance_request(2, [{'cursor': 2, 'mutation': mutation}]).model_dump(by_alias=True), mutation=mutation)
        skipped = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    else:
        original = block.model_copy(deep=True)
        fixture.writers.save(fixture.project, edit_again(fixture, block_id=block.id, value='Temporary heading',
            action='heading-action', identifier='heading-first'), originals=fixture.originals)
        current = next(value for value in fixture.current().project.document.blocks() if value.id == block.id)
        parent, previous, _owner = placements(fixture.current().project.document)[block.id]
        mutation = request(fixture.current(), [{'kind': 'put_block', 'parentId': parent, 'afterId': previous,
            'beforeRevision': current.revision, 'block': original.model_dump(by_alias=True), 'keepChildren': True}], 'heading-restored')
        mutation.action_id = mutation.capture.action_id = 'heading-action'
        mutation.capture.session_id, mutation.capture.action_token = fixture.proof.session_id, 2
        command = WriterMutationV2(**fixture.advance_request(3, [{'cursor': 3, 'mutation': mutation}]).model_dump(by_alias=True), mutation=mutation)
        skipped = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert skipped.local_history_ack is None
    assert fixture.writers.local_history.openings[fixture.project].cursor == 1
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, first.local_history_ack), originals=fixture.originals)
    assert undone.workspace.project.import_issues[0].state == 'active'
    assert 'Exact human correction' not in text(undone.workspace.project.document)


@pytest.mark.parametrize('changed', [False, True])
def test_edit_cannot_reuse_an_undone_action_or_corrupt_its_redo_cursor(tmp_path, changed):
    from tests.templates.test_transactions import request
    fixture = TemplateWriterFixture(tmp_path)
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, saved.local_history_ack), originals=fixture.originals)
    block = next(block for block in fixture.current().project.document.blocks() if block.type == 'heading')
    if changed:
        command = edit_again(fixture, block_id=block.id, value='Changed heading', action=saved.local_history_ack.action_id, token=3)
    else:
        parent, previous, _owner = placements(fixture.current().project.document)[block.id]
        mutation = request(fixture.current(), [{'kind': 'put_block', 'parentId': parent, 'afterId': previous,
            'beforeRevision': block.revision, 'block': block.model_dump(by_alias=True), 'keepChildren': True}], 'reuse-undone')
        mutation.action_id = mutation.capture.action_id = saved.local_history_ack.action_id
        mutation.capture.session_id, mutation.capture.action_token = fixture.proof.session_id, 3
        command = WriterMutationV2(**fixture.advance_request(2, [{'cursor': 2, 'mutation': mutation}]).model_dump(by_alias=True), mutation=mutation)
    before = canonical(fixture.current())
    with pytest.raises(BackgroundFailure, match='DEPENDENCY_CHANGED'):
        fixture.writers.save(fixture.project, command, originals=fixture.originals)
    assert canonical(fixture.current()) == before
    opening = fixture.writers.local_history.openings[fixture.project]
    assert opening.cursor == 0 and len(opening.actions) == 1
    redone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, undone.local_history_ack, 'redo', 'redo-after-rejected-reuse'), originals=fixture.originals)
    assert redone.workspace.project.import_issues[0].state == 'retired'


def test_same_typing_group_continues_after_net_empty_without_reusing_old_ack_generation(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    block = next(block for block in fixture.current().project.document.blocks() if block.type == 'heading')
    first = fixture.writers.save(fixture.project, edit_again(fixture, block_id=block.id, value='Temporary heading',
        action='heading-group', identifier='heading-group-first'), originals=fixture.originals)
    empty = fixture.writers.save(fixture.project, put_block_again(fixture, block, action='heading-group',
        identifier='heading-group-empty', token=2), originals=fixture.originals)
    assert empty.local_history_ack is None
    continued = fixture.writers.save(fixture.project, edit_again(fixture, block_id=block.id, value='Continued heading',
        action='heading-group', identifier='heading-group-continued', token=3), originals=fixture.originals)
    assert continued.local_history_ack.generation > first.local_history_ack.generation
    with pytest.raises(BackgroundFailure, match='DEPENDENCY_CHANGED'):
        fixture.writers.local_history_command(fixture.project,
            history_request(fixture, first.local_history_ack, identifier='old-generation'), originals=fixture.originals)
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, continued.local_history_ack, identifier='current-generation'), originals=fixture.originals)
    assert 'Continued heading' not in text(undone.workspace.project.document)
    assert all(issue.state == 'active' for issue in undone.workspace.project.import_issues)


@pytest.mark.parametrize('branch', ['undone', 'net_empty'])
def test_later_edit_retires_removed_action_id_without_resetting_its_authority(tmp_path, branch):
    fixture = TemplateWriterFixture(tmp_path)
    block = next(block for block in fixture.current().project.document.blocks() if block.type == 'heading')
    first = fixture.writers.save(fixture.project, edit_again(fixture, block_id=block.id, value='Temporary heading',
        action='old-group', identifier='old-group-first'), originals=fixture.originals)
    if branch == 'undone':
        fixture.writers.local_history_command(fixture.project,
            history_request(fixture, first.local_history_ack), originals=fixture.originals)
    else:
        fixture.writers.save(fixture.project, put_block_again(fixture, block, action='old-group',
            identifier='old-group-empty', token=2), originals=fixture.originals)
    current = fixture.writers.save(fixture.project, edit_again(fixture, block_id=block.id, value='New action',
        action='fresh-group', identifier='fresh-group-save'), originals=fixture.originals)
    assert current.local_history_ack.generation > first.local_history_ack.generation
    before = canonical(fixture.current())
    with pytest.raises(BackgroundFailure, match='DEPENDENCY_CHANGED'):
        fixture.writers.save(fixture.project, edit_again(fixture, block_id=block.id, value='Reused ID',
            action='old-group', identifier='old-group-reused', token=5), originals=fixture.originals)
    assert canonical(fixture.current()) == before


def test_pruned_interrupted_receipt_drops_inverses_without_resetting_same_opening_guards(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    first = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    block_id = next(block.id for block in fixture.current().project.document.blocks()
        if 'Exact human correction' in ''.join(part.text for part in block.content))
    def interrupt(name, _project):
        if name == 'before_local_history_receipt':
            raise SystemExit('synthetic cut')
    fixture.writers.observer = interrupt
    with pytest.raises(SystemExit, match='synthetic cut'):
        fixture.writers.save(fixture.project, edit_again(fixture, action='human-edit', token=2, block_id=block_id), originals=fixture.originals)
    fixture.writers.observer = lambda *_args: None
    current = fixture.current()
    after = current.model_copy(deep=True)
    after.title = 'Unrelated metadata after interrupted receipt'
    after.project_revision += 1
    after.project.revision = after.project_revision
    fixture.publisher.snapshot(fixture.project, digest_bytes(current), after, 'metadata-prune', originals=fixture.originals)
    assert not any(value.client_mutation_id == 'next-save' for value in fixture.jobs.load(fixture.project).manual_intents)
    fixture.writers.flush(fixture.project, fixture.advance_request(fixture.jobs.load(fixture.project).writer.acknowledged_cursor))
    before = canonical(fixture.current())
    with pytest.raises(BackgroundFailure, match='DEPENDENCY_CHANGED'):
        fixture.writers.save(fixture.project, edit_again(fixture, action='human-edit', token=3,
            identifier='lost-group-reuse', block_id=block_id), originals=fixture.originals)
    assert canonical(fixture.current()) == before
    with pytest.raises(BackgroundFailure, match='REQUEST_EXPIRED'):
        fixture.writers.local_history_command(fixture.project,
            history_request(fixture, first.local_history_ack, identifier='old-pruned-ack'), originals=fixture.originals)
    fresh = fixture.writers.save(fixture.project, edit_again(fixture, action='fresh-action',
        identifier='fresh-after-prune', block_id=block_id, value='Fresh post-prune correction'), originals=fixture.originals)
    assert fresh.local_history_ack.generation > first.local_history_ack.generation + 1
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, fresh.local_history_ack, identifier='fresh-after-prune-undo'), originals=fixture.originals)
    assert 'Second exact correction' in text(undone.workspace.project.document)
    assert undone.workspace.title == after.title


@pytest.mark.parametrize('case', ['joined_scope', 'owner_move', 'owner_delete'])
def test_actual_writer_replays_shared_scopes_ownership_and_cascaded_deletion(case, tmp_path):
    from packages.resume_core.agent_edits import semantic
    from packages.resume_core.template_authoring import move_occurrence_steps
    from tests.templates.test_builtin_scopes import scoped_workspace, joined_edit
    from tests.templates.test_relation_transactions import related_workspace, owner_sections
    from tests.templates.test_transactions import request
    before, sources = scoped_workspace() if case == 'joined_scope' else related_workspace()
    if case == 'owner_move':
        before = owner_sections(before)
    fixture = TemplateWriterFixture(tmp_path, before, sources)
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
    mutation.capture.session_id = fixture.proof.session_id
    command = WriterMutationV2(**fixture.advance_request(1, [{'cursor': 1, 'mutation': mutation}]).model_dump(by_alias=True), mutation=mutation)
    saved = fixture.writers.save(fixture.project, command, originals=fixture.originals)
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, saved.local_history_ack), originals=fixture.originals)
    assert semantic(undone.workspace.project.document) == semantic(before.project.document)
    assert semantic(undone.workspace.project.facts.records) == semantic(before.project.facts.records)
    assert semantic(undone.workspace.project.facts.extensions) == semantic(before.project.facts.extensions)
    assert not undone.workspace.project.facts.builtin_manual_scopes
    assert undone.workspace.project.facts.observations == before.project.facts.observations
    redone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, undone.local_history_ack, 'redo', 'redo-owned'), originals=fixture.originals)
    assert semantic(redone.workspace.project.document) == semantic(saved.workspace.project.document)
    assert semantic(redone.workspace.project.facts.records) == semantic(saved.workspace.project.facts.records)
    assert semantic(redone.workspace.project.facts.extensions) == semantic(saved.workspace.project.facts.extensions)
    assert redone.workspace.project.facts.builtin_manual_scopes == saved.workspace.project.facts.builtin_manual_scopes
