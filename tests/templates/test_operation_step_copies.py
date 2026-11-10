"""Import steps share what they do not change with their input and never change the input itself (S8 speed)."""

import pytest

from packages.resume_core.storage import RepositoryFailure
from packages.resume_core.importing.template_import import (CleanupProof, admit_operation, cancel_operation,
                                                            dispatch_attempt, observe_time, reconcile_cleanup,
                                                            record_return, reserve_attempt, resume_operation)
from packages.resume_core.hashing import digest
from resume_api.importer.template_pipeline import operation_in
from resume_api.importer.template_sidecar import OperationSidecar
from tests.templates.entry_fixtures import entries_package, entries_script, lines_source, ref_of
from tests.templates.evidence_references import model_targets
from tests.templates.pipeline_fixtures import NOW, cleaned, model, owner, ready_operation, resume_command, usage
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_template_pipeline import failing_review

LATER = '2026-10-21T00:00:05+00:00'


def frozen(operation):
    return operation.model_dump_json(by_alias=True)


def test_each_attempt_step_returns_a_separate_operation_and_leaves_its_input_unchanged():
    operation = ready_operation()
    task = operation.tasks[0].id
    steps = []
    before = frozen(operation)
    reserved, attempt = reserve_attempt(operation, task, 'initial', digest('request'), model(), owner(1), NOW)
    steps.append((operation, before, reserved))
    before = frozen(reserved)
    dispatched = dispatch_attempt(reserved, attempt, NOW)
    steps.append((reserved, before, dispatched))
    before = frozen(dispatched)
    returned = record_return(dispatched, attempt, '{"payload": {}}', 'completed', usage(), cleaned(), returned_at=LATER)
    steps.append((dispatched, before, returned))
    before = frozen(returned)
    proof = CleanupProof(attempt, digest(returned.attempts[0].owner), digest('proof'), 'controlled-terminal')
    reconciled = reconcile_cleanup(returned, proof, LATER)
    steps.append((returned, before, reconciled))
    for given, unchanged, result in steps:
        assert frozen(given) == unchanged
        # The result shares no attempt, task or list with its input.
        assert all(new is not old for new in result.attempts for old in given.attempts)
        assert all(new is not old for new in result.tasks for old in given.tasks)
        assert result.attempts is not given.attempts and result.cleanup_records is not given.cleanup_records
    assert [value.state for value in reconciled.attempts] == ['returned'] and reconciled.cleanup_records


def test_observing_time_copies_only_the_fields_it_changes_and_resume_keeps_its_input():
    operation = ready_operation()
    before = frozen(operation)
    observed = observe_time(operation, LATER)
    assert observed.last_observed_at == LATER and operation.last_observed_at != LATER and frozen(operation) == before
    cancelled = cancel_operation(operation)
    before = frozen(cancelled)
    command = resume_command(cancelled)
    resumed = resume_operation(cancelled, command, LATER)
    assert frozen(cancelled) == before and resumed.authorizations[-1].id == command.authorization_id
    assert [task.state for task in cancelled.tasks] != [task.state for task in resumed.tasks] or cancelled.state != resumed.state


def step_kinds(prior, updated):
    """What one pipeline step did, read from what it added to the operation and how its attempts moved."""
    def added(name):
        known = {value.id for value in getattr(prior, name)}
        return [value for value in getattr(updated, name) if value.id not in known]
    states = {value.id: value.state for value in prior.attempts}
    kinds = {'reserve' for _value in added('attempts')} | {'review reserve' for _value in added('review_inputs')}
    kinds |= {'dispatch' if value.state == 'dispatch_started' else 'return' for value in updated.attempts
        if states.get(value.id) in {'reserved', 'dispatch_started'} and value.state != states[value.id]}
    kinds |= {'input' for _value in added('task_inputs')} | {'parse' for _value in added('proposals')}
    kinds |= {'accept' for _value in added('receipts')}
    kinds |= {'entries from the ' + value.entry.origin if value.entry else 'outline review' for value in added('tasks')}
    parents = {value.parent_task_id for value in updated.tasks}
    kinds |= {'close' if value.task_id in parents else 'fallback' if value.disposition == 'source_fallback' else 'finish'
        for value in added('task_results')}
    return kinds


@pytest.mark.asyncio
async def test_no_step_of_an_import_changes_a_view_and_the_read_cache_keeps_what_the_disk_holds(tmp_path, monkeypatch):
    # D154: a step reads the shared cached view without copying it, and the next read keeps what the step wrote.
    # Without FOLDCV_VERIFY a cached read parses no sidecar, so a step that reads its sidecar back shows.
    monkeypatch.delenv('FOLDCV_VERIFY', raising=False)
    src, raw = lines_source(3)
    fixture = RuntimeFixture(tmp_path, captured=entries_package(), src=src, original_bytes=raw, concurrency=2, cap=30,
        fallback=False)
    def outline_review(value):
        return {'missing': [{'title': 'Stream Letters', 'first': ref_of(value, 'paper-c'), 'last': ref_of(value, 'paper-c')}],
            'remarks': []}
    def reviews(value):
        lines = value['semanticContext']['taskInput']['entry']['lines']
        second = any(option['ref'] in lines and option['text'].endswith('paper-b\n') for option in value['evidence'])
        return failing_review(value, model_targets(value)) if second else {'results': []}
    fixture.transport.scripted = entries_script(review=outline_review, reviews=reviews)
    pipeline, step, parsed, views, kinds = fixture.pipeline, fixture.pipeline.update_operation, [], [], set()
    read = OperationSidecar.read
    monkeypatch.setattr(OperationSidecar, 'read', lambda self, *args: parsed.append(args) or read(self, *args))

    def checked_step(project, operation_id, transition):
        # The project lock holds the other steps off while this one is checked.
        with fixture.repository.open(project).lock:
            before = pipeline.read(project)
            views.append((before, before.model_dump_json(by_alias=True)))
            parsed.clear()
            result = step(project, operation_id, transition)
            assert not parsed and before.model_dump_json(by_alias=True) == views[-1][1]
            assert pipeline.read_cache[project][2] is result and result == fixture.fresh_pipeline().read(project)
            kinds.update(step_kinds(operation_in(before, operation_id), operation_in(result, operation_id)))
            return result
    monkeypatch.setattr(pipeline, 'update_operation', checked_step)
    result = await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published'
    assert kinds == {'input', 'reserve', 'review reserve', 'dispatch', 'return', 'parse', 'accept', 'finish', 'fallback',
        'close', 'outline review', 'entries from the outline', 'entries from the review'}
    # The views a task held across its awaits are unchanged too.
    assert all(view.model_dump_json(by_alias=True) == frozen for view, frozen in views)


@pytest.mark.asyncio
async def test_a_step_beside_another_live_import_sidecar_still_ends_unknown(tmp_path, monkeypatch):
    # The read cache keeps a step's result only while no other import has a sidecar file: two live sidecars fence.
    monkeypatch.delenv('FOLDCV_VERIFY', raising=False)
    fixture = RuntimeFixture(tmp_path)
    first = await fixture.pipeline.start(fixture.project, fixture.command)
    await fixture.pipeline.cancel(fixture.project, first.id)
    command = fixture.command.model_copy(update={'client_request_id': 'second-request'})
    second = await fixture.pipeline.start(fixture.project, command)
    saved = fixture.saved()
    fixture.sidecar.write(fixture.project, saved.project_revision, operation_in(saved, first.id), saved.pre_draft.facts)
    with pytest.raises(RepositoryFailure, match='OUTCOME_UNKNOWN'):
        fixture.pipeline.update_operation(fixture.project, second.id, lambda value, _data, _workspace: admit_operation(value, NOW))
