"""Controlled stalled writes prove fencing, not native filesystem deadlines."""

import asyncio
import threading

import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from tests.templates.test_template_publication import TemplatePublicationFixture
from resume_api.importer.template_persistence import PersistenceWindow, TemplatePersistence


@pytest.mark.asyncio
async def test_saved_outcome_retains_the_content_hash_after_metadata_checkpoint(tmp_path):
    fixture = TemplatePublicationFixture(tmp_path)
    persistence = TemplatePersistence(fixture.publisher, wall=lambda: fixture.now)
    outcome = await persistence.publish(fixture.before, fixture.after, fixture.before.pre_draft.template_operations[0],
        originals=fixture.originals)
    current = fixture.current()
    assert outcome.state == 'saved' and outcome.workspace_hash == digest_bytes(fixture.after)
    assert digest_bytes(current) != outcome.workspace_hash
    retained = current.project.template_operations[0]
    assert retained.state == 'published' and retained.publication == outcome
    fixture.now = '2026-10-21T01:00:00+00:00'
    assert await persistence.publish(fixture.before, fixture.after, fixture.before.pre_draft.template_operations[0],
        originals=fixture.originals) == outcome
    assert len(fixture.jobs.load(fixture.project).manual_intents) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('phase,saved', [('intent_stored', False), ('commit_claimed', True),
    ('workspace_replaced', True)])
async def test_timeout_keeps_write_owned_and_new_work_fenced_until_reconciled(tmp_path, monkeypatch, phase, saved):
    fixture = TemplatePublicationFixture(tmp_path)
    reached, release = threading.Event(), threading.Event()
    def pause(name, _project):
        if name == phase:
            reached.set()
            assert release.wait(5)
    fixture.publisher.observer = pause
    persistence = TemplatePersistence(fixture.publisher, wall=lambda: fixture.now)
    wait = asyncio.wait
    async def expire_at_cutpoint(tasks, *, timeout):
        assert 0 < timeout <= 30
        assert await asyncio.to_thread(reached.wait, 5)
        return await wait(tasks, timeout=0.01)
    monkeypatch.setattr(asyncio, 'wait', expire_at_cutpoint)
    try:
        outcome = await persistence.publish(fixture.before, fixture.after, fixture.before.pre_draft.template_operations[0],
            originals=fixture.originals)
        assert reached.is_set() and outcome.state == 'outcome_unknown'
        assert fixture.project in persistence.pending and fixture.jobs.fences[fixture.project] == 'OUTCOME_UNKNOWN'
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            await persistence.reconcile(fixture.project)
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            await persistence.bounded(fixture.project, lambda: None,
                PersistenceWindow.capture('2026-10-21T00:05:31+00:00', fixture.now, persistence.elapsed()))
    finally:
        release.set()
        if fixture.project in persistence.pending:
            await asyncio.gather(persistence.wait_pending(fixture.project), return_exceptions=True)
    await persistence.reconcile(fixture.project)
    actual = persistence.outcome(fixture.project, fixture.binding)
    assert actual.state == ('saved' if saved else 'failed_before_replacement')
    assert fixture.current() == (fixture.after if saved else fixture.before)
    assert len(fixture.jobs.load(fixture.project).manual_intents) == 1


@pytest.mark.asyncio
async def test_metadata_failure_does_not_downgrade_a_proven_saved_import(tmp_path):
    fixture = TemplatePublicationFixture(tmp_path)
    calls = []
    def fail(name, _project):
        if name == 'before_snapshot_prepared':
            calls.append(name)
            if len(calls) == 2:
                raise OSError('controlled outcome checkpoint failure')
    fixture.publisher.observer = fail
    persistence = TemplatePersistence(fixture.publisher, wall=lambda: fixture.now)
    outcome = await persistence.publish(fixture.before, fixture.after, fixture.before.pre_draft.template_operations[0],
        originals=fixture.originals)
    assert outcome.state == 'saved' and outcome.workspace_hash == digest_bytes(fixture.after)
    assert fixture.current().project is not None
    assert fixture.current().project.template_operations[0].publication.state == 'pending'
    assert persistence.outcome(fixture.project, fixture.binding).state == 'saved'


def test_persistence_window_does_not_extend_on_wall_rollback():
    window = PersistenceWindow.capture('2026-10-21T00:00:30+00:00', '2026-10-21T00:00:00+00:00', 100)
    assert window.remaining('2026-10-20T23:59:00+00:00', 130) == 0
    restarted = PersistenceWindow.capture('2026-10-21T00:00:30+00:00', '2026-10-20T23:59:00+00:00', 100,
        started_at='2026-10-21T00:00:00+00:00')
    assert restarted.remaining('2026-10-20T23:59:00+00:00', 100) == 0
