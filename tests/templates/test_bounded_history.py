"""Actual writer history keeps large unchanged evidence out of retained inverses."""

import pytest

from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.rich_document import SourceWitness
from packages.resume_core.models.template_document import PresentedText
from packages.resume_core.models.template_mutations import AuthoredBlockHistoryDelta
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.models.template_writer import WriterMutationV2
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.template_block_patches import block_hash, restore_payload
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_local_history import changes, restore
from packages.resume_core.template_preparation import prepare_text_edit
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_template_local_history import history_request
from tests.templates.test_template_preparation import command, response
from tests.templates.test_template_writers import TemplateWriterFixture
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


def prepared_save(fixture, *, text='!', start=2, end=2, identifier='large-edit', token=1, action='large-action'):
    before = fixture.current()
    request = command(before, start=start, end=end, text=text, target={'kind': 'literal'} if start == end else None)
    request.client_mutation_id = identifier
    request.capture.action_id = action
    request.capture.session_id = fixture.proof.session_id
    request.capture.action_token = token
    prepared = prepare_text_edit(response(before), request)
    mutation = prepared.mutation
    cursor = fixture.jobs.load(fixture.project).writer.acknowledged_cursor + 1
    return WriterMutationV2(**fixture.advance_request(cursor, [{'cursor': cursor, 'mutation': mutation}]).model_dump(by_alias=True),
        mutation=mutation)


def test_real_large_save_coalesced_undo_redo_and_net_empty_use_bounded_history(tmp_path):
    before, sources = large_workspace()
    fixture = TemplateWriterFixture(tmp_path, before, sources)
    first = fixture.writers.save(fixture.project, prepared_save(fixture), originals=fixture.originals)
    second = fixture.writers.save(fixture.project, prepared_save(fixture, text='?', start=3, end=3,
        identifier='large-edit-two', token=2), originals=fixture.originals)
    opening = fixture.writers.local_history.openings[fixture.project]
    assert len(opening.actions) == 1 and second.local_history_ack.generation > first.local_history_ack.generation
    retained = next(value for value in opening.actions[0].delta.values() if isinstance(value, AuthoredBlockHistoryDelta))
    assert len(canonical(retained)) < 1500 and 'large-witness' not in canonical(retained).decode()
    undo_request = history_request(fixture, second.local_history_ack)
    mutation = fixture.writers.local_history.derive(opening, fixture.current(), undo_request)
    assert len(canonical(mutation)) < 2500 and mutation.steps[0].kind == 'restore_authored_block_patch'
    undone = fixture.writers.local_history_command(fixture.project, undo_request, originals=fixture.originals)
    assert block_hash(undone.workspace.project.document.regions[2].blocks[0]) == block_hash(before.project.document.regions[2].blocks[0])
    redone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, undone.local_history_ack, 'redo', 'large-redo'), originals=fixture.originals)
    assert ''.join(span.text for span in redone.workspace.project.document.regions[2].blocks[0].content) == 'Hi!?'
    assert redone.workspace.project.document.regions[2].blocks[0].provenance == before.project.document.regions[2].blocks[0].provenance
    # A separate typing group can return exactly to its starting payload.
    fixture.writers.save(fixture.project, prepared_save(fixture, text='x', start=4, end=4,
        identifier='net-empty-first', token=1, action='empty-action'), originals=fixture.originals)
    empty = fixture.writers.save(fixture.project, prepared_save(fixture, text='', start=4, end=5,
        identifier='net-empty-last', token=2, action='empty-action'), originals=fixture.originals)
    assert empty.local_history_ack is None
    assert len(fixture.writers.local_history.openings[fixture.project].actions) == 1
    assert LIMITS.inverse_bytes == 512 * 1024


def test_hash_guards_include_provenance_and_all_payload_values_and_reject_identity_paths():
    before, _ = large_workspace()
    after = before.model_copy(deep=True)
    block = after.project.document.regions[2].blocks[0]; block.content[0].text += '!'
    delta = changes(before, after)
    entry = delta[('block', block.id)]
    assert isinstance(entry, AuthoredBlockHistoryDelta) and len(canonical(entry)) < 1500
    assert block_hash(restore(after, delta).project.document.regions[2].blocks[0]) == block_hash(before.project.document.regions[2].blocks[0])
    block.provenance[0].evidence[0].text += 'changed'
    with pytest.raises(ValueError, match='preimage'):
        restore(after, delta)
    original = before.project.document.regions[2].blocks[0]
    for key in ['id', 'revision', 'children', 'placement']:
        with pytest.raises(ValueError):
            restore_payload(original, block_hash(original), block_hash(original),
                [{'kind': 'set', 'pointer': '/' + key, 'valueWire': 'null'}])


def test_retained_fragment_ids_restore_only_under_exact_history_and_still_reject_collisions():
    from tests.templates.test_template_preparation import proof
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


@pytest.mark.parametrize('phase', ['before_workspace_replaced', 'before_local_history_receipt'])
def test_large_publication_interruption_recovers_without_inventing_history(tmp_path, phase):
    before, sources = large_workspace()
    fixture = TemplateWriterFixture(tmp_path, before, sources)
    target = fixture.publisher if phase == 'before_workspace_replaced' else fixture.writers
    def interrupt(name, _project):
        if name == phase:
            raise SystemExit('synthetic publication interruption')
    target.observer = interrupt
    request = prepared_save(fixture)
    with pytest.raises(SystemExit, match='synthetic publication'):
        fixture.writers.save(fixture.project, request, originals=fixture.originals)
    target.observer = lambda *_args: None
    if phase == 'before_workspace_replaced':
        fixture.publisher.recover(fixture.project)
        assert block_hash(fixture.current().project.document.regions[2].blocks[0]) == block_hash(before.project.document.regions[2].blocks[0])
        fixture.writers.reconcile(fixture.project, fixture.advance_request(1))
        assert not fixture.writers.local_history.openings
    else:
        saved = fixture.writers.save(fixture.project, request, originals=fixture.originals)
        assert saved.replayed and saved.local_history_ack.generation == 1
        undone = fixture.writers.local_history_command(fixture.project,
            history_request(fixture, saved.local_history_ack), originals=fixture.originals)
        assert block_hash(undone.workspace.project.document.regions[2].blocks[0]) == block_hash(before.project.document.regions[2].blocks[0])


@pytest.mark.parametrize('direction', ['insert', 'delete'])
def test_true_large_changed_payload_exceeds_existing_inverse_budget_before_commit(tmp_path, direction):
    before, sources = workspace()
    block = before.project.document.regions[2].blocks[0]
    block.content = [PresentedText(type='text', text='X' * (600 * 1024) if direction == 'delete' else 'Hi', styles={})]
    fixture = TemplateWriterFixture(tmp_path, before, sources)
    raw = canonical(fixture.current())
    request = prepared_save(fixture, text='' if direction == 'delete' else 'X' * (600 * 1024),
        start=0 if direction == 'delete' else 2, end=600 * 1024 if direction == 'delete' else 2)
    with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
        fixture.writers.save(fixture.project, request, originals=fixture.originals)
    assert canonical(fixture.current()) == raw
    assert not fixture.writers.local_history.openings


def test_shared_usage_counts_pending_reservation_commands_and_guards_and_detach_releases(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    registry = fixture.writers.local_history
    assert registry.usage() == {}
    def interrupt(name, _project):
        if name == 'before_local_history_receipt':
            raise SystemExit('retain pending receipt')
    fixture.writers.observer = interrupt
    request = fixture.save_request()
    with pytest.raises(SystemExit, match='retain pending'):
        fixture.writers.save(fixture.project, request, originals=fixture.originals)
    opening = registry.openings[fixture.project]
    pending_usage = registry.usage()[fixture.project]
    assert pending_usage.draft_bytes == 0 and pending_usage.owned_bytes > 0 and pending_usage.records > 2
    pending = opening.pending[request.mutation.client_mutation_id]
    assert pending['reserved_bytes'] >= 0 and pending['reserved_records'] >= 0
    fixture.writers.observer = lambda *_args: None
    saved = fixture.writers.save(fixture.project, request, originals=fixture.originals)
    final_usage = registry.usage()[fixture.project]
    assert pending_usage.owned_bytes >= final_usage.owned_bytes and pending_usage.records >= final_usage.records
    assert not opening.pending and opening.known_ids and opening.generations
    undone = fixture.writers.local_history_command(fixture.project,
        history_request(fixture, saved.local_history_ack), originals=fixture.originals)
    command_usage = registry.usage()[fixture.project]
    assert opening.commands and command_usage.owned_bytes > final_usage.owned_bytes
    # An expired lease retains its nonportable history until explicit closure.
    state = fixture.jobs.load(fixture.project)
    state.writer.lease_expires_at = '2000-01-01T00:00:00Z'
    assert registry.usage(states={fixture.project: state})[fixture.project] == command_usage
    fixture.writers.detach(fixture.project, fixture.advance_request(fixture.jobs.load(fixture.project).writer.acknowledged_cursor))
    assert registry.usage() == {} and undone.local_history_ack is not None


def test_preparation_admission_and_normal_writes_share_existing_history_usage(tmp_path, monkeypatch):
    from dataclasses import replace
    from packages.resume_core import background_store
    from packages.resume_core.background_store import RetainedUsage
    from packages.resume_core.models.template_writer import WriterPrepareEditV2
    fixture = TemplateWriterFixture(tmp_path)
    fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    registry = fixture.writers.local_history
    old_usage = registry.usage()[fixture.project]
    state = fixture.jobs.load(fixture.project)
    bound = background_store.records(state) + sum(
        provider(states={fixture.project: state}).get(fixture.project, RetainedUsage()).records
        for provider in fixture.jobs.usage_providers.values())
    preparation = command(fixture.current(), start=0, end=1)
    preparation.capture.session_id = fixture.proof.session_id
    request = WriterPrepareEditV2(schemaVersion=2, proof=fixture.proof, preparation=preparation)
    with monkeypatch.context() as limited:
        limited.setattr(background_store, 'LIMITS', replace(LIMITS, metadata_global_records=bound))
        with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
            fixture.writers.prepare_edit(fixture.project, request)
    assert registry.usage()[fixture.project] == old_usage
    assert fixture.writers.preparations.usage() == {}
    fixture.jobs.usage_providers['other-owner'] = lambda **_kwargs: {'other-project': RetainedUsage(0, 100, 1)}
    with monkeypatch.context() as limited:
        limited.setattr(background_store, 'LIMITS', replace(LIMITS, metadata_global_records=bound))
        with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
            fixture.writers.heartbeat(fixture.project, fixture.proof)
    assert registry.usage()[fixture.project] == old_usage


def test_failed_first_admission_does_not_install_an_empty_unbudgeted_opening(tmp_path, monkeypatch):
    from dataclasses import replace
    from packages.resume_core import background_store
    fixture = TemplateWriterFixture(tmp_path)
    state = fixture.jobs.load(fixture.project)
    before = canonical(fixture.current())
    registry = fixture.writers.local_history
    assert not registry.openings and not registry.usage()
    with monkeypatch.context() as limited:
        limited.setattr(background_store, 'LIMITS', replace(LIMITS,
            metadata_global_records=background_store.records(state)))
        with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
            fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    assert not registry.openings and not registry.usage()
    assert canonical(fixture.current()) == before
    fixture.writers.heartbeat(fixture.project, fixture.proof)


def test_real_candidate_capacity_rejection_releases_the_unpublished_pending_reservation(tmp_path, monkeypatch):
    from dataclasses import replace
    from packages.resume_core import background_store
    fixture = TemplateWriterFixture(tmp_path)
    registry = fixture.writers.local_history
    before = canonical(fixture.current())
    reached = []
    original = fixture.publisher._store_intent
    def store(*args):
        reached.append(True)
        assert registry.openings[fixture.project].pending
        return original(*args)
    monkeypatch.setattr(fixture.publisher, '_store_intent', store)
    with monkeypatch.context() as limited:
        limited.setattr(background_store, 'LIMITS', replace(LIMITS, metadata_global_records=21))
        with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
            fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    assert reached and not registry.openings and not registry.usage()
    assert canonical(fixture.current()) == before and not fixture.jobs.load(fixture.project).manual_intents
    fixture.writers.heartbeat(fixture.project, fixture.proof)


def test_unknown_durable_intent_reply_keeps_reservation_until_reconciliation(tmp_path, monkeypatch):
    fixture = TemplateWriterFixture(tmp_path)
    registry = fixture.writers.local_history
    original = fixture.publisher._store_intent
    def store(*args):
        original(*args)
        raise BackgroundFailure('OUTCOME_UNKNOWN')
    with monkeypatch.context() as interrupted:
        interrupted.setattr(fixture.publisher, '_store_intent', store)
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    assert registry.openings[fixture.project].pending and registry.usage()[fixture.project].owned_bytes > 0
    assert fixture.jobs.load(fixture.project).manual_intents
    fixture.publisher.recover(fixture.project)
    fixture.writers.reconcile(fixture.project, fixture.advance_request(1))
    assert not registry.openings and not registry.usage()


def test_exact_shared_byte_bound_allows_explicit_detach_but_failed_write_keeps_history(tmp_path, monkeypatch):
    from dataclasses import replace
    from packages.resume_core import background_store
    from packages.resume_core.project_store import encoded
    fixture = TemplateWriterFixture(tmp_path)
    fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    registry = fixture.writers.local_history
    old = registry.usage()[fixture.project]
    state = fixture.jobs.load(fixture.project)
    total = (len(encoded(state.model_dump(mode='json', by_alias=True))) + fixture.jobs._reserved_bytes(state)
        + fixture.jobs._extra_bytes(fixture.project) + fixture.jobs._fixed_bytes(state)
        + sum(provider(states={fixture.project: state}).get(fixture.project, background_store.RetainedUsage()).owned_bytes
            for provider in fixture.jobs.usage_providers.values()))
    request = fixture.advance_request(state.writer.acknowledged_cursor)
    with monkeypatch.context() as failed:
        def fail(*_args, **_kwargs):
            raise BackgroundFailure('JOB_STORAGE_FULL')
        failed.setattr(fixture.jobs, '_write', fail)
        with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
            fixture.writers.detach(fixture.project, request)
    assert registry.usage()[fixture.project] == old
    assert fixture.jobs.load(fixture.project).writer.status == 'attached'
    # A durable clean transition may prospectively free its nonportable data.
    with monkeypatch.context() as limited:
        limited.setattr(background_store, 'LIMITS', replace(LIMITS, sidecar_global_bytes=total))
        fixture.writers.detach(fixture.project, request)
    assert not registry.openings and not registry.usage()
