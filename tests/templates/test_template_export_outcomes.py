"""Controlled exporters prove identity/outcomes, not DOCX or Word rendering."""

import asyncio
import threading

import pytest

from packages.resume_core.models.template_render import TemplateRendererIdentity
from packages.resume_core.template_export import snapshot_identity
from packages.resume_core.template_import import TemplateImportFailure, digest
from packages.resume_core.background_store import BackgroundFailure
from tests.templates.test_template_checkpoints import authored_owner
from tests.templates.template_runtime_fixtures import RuntimeFixture
from resume_api.importer.template_export import TemplateExporter
from tests.templates.test_template_finalization_flow import queued
from tests.templates.test_template_job_routing import service_for


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
async def test_export_failure_is_durable_and_retry_has_no_inference(tmp_path, entry):
    fixture = RuntimeFixture(tmp_path)
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.pipeline
    try:
        if service:
            await queued(service, fixture, fixture.command)
            operation = fixture.current().project.template_operations[0]
        else:
            operation = await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
        inference = len(fixture.transport.calls)
        calls = []
        def render(request):
            calls.append(request)
            if len(calls) == 1:
                raise RuntimeError('controlled export failure')
            return b'controlled artifact; not a DOCX acceptance claim'
        renderer = TemplateRendererIdentity(id='controlled-renderer', version='1', sha256=digest('controlled-renderer-code'))
        exporter = TemplateExporter(pipeline, renderer, render)
        snapshot = snapshot_identity(fixture.current())
        first = await exporter.export(fixture.project, snapshot, publication_intent_id=operation.publication.intent_id)
        assert first.attempt.state == 'failed' and first.attempt.error_code == 'RENDER_FAILED'
        assert fixture.current().project.template_operations[0].publication == operation.publication
        again = await exporter.export(fixture.project, snapshot, retry_attempt_id=first.attempt.id,
            publication_intent_id=operation.publication.intent_id)
        assert again.attempt.state == 'completed' and again.attempt.id != first.attempt.id
        assert calls[0] == calls[1] and len(fixture.transport.calls) == inference
        current = fixture.current()
        assert [value.state for value in current.project.exports] == ['failed', 'completed']
        assert len(current.project.export_inputs) == 2 and current.project.exports == current.project.template_operations[0].export_attempts
        assert calls[1].package == current.project.template_package
        path = fixture.canonical._blob(fixture.canonical._directory(fixture.project), 'renders', again.attempt.id)
        assert path.read_bytes() == again.artifact
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_export_rejects_stale_snapshot_before_renderer_or_attempt(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    snapshot = snapshot_identity(fixture.current())
    stale = snapshot.model_copy(update={'document_hash': '0' * 64})
    def render(_request):
        raise AssertionError('stale export must not reach renderer')
    exporter = TemplateExporter(fixture.pipeline,
        TemplateRendererIdentity(id='controlled', version='1', sha256=digest('renderer')), render)
    with pytest.raises(TemplateImportFailure, match='IMPORT_EXPORT_SNAPSHOT_STALE'):
        await exporter.export(fixture.project, stale)
    assert not fixture.current().project.exports


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
async def test_issue_export_remains_bound_to_old_revision_when_a_new_edit_saves(tmp_path, entry):
    fixture = RuntimeFixture(tmp_path, cap=1)
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.pipeline
    entered, release = threading.Event(), threading.Event()
    calls = []
    def render(request):
        calls.append(request)
        entered.set()
        assert release.wait(30)
        return b'controlled old revision artifact'
    try:
        if service:
            await queued(service, fixture, fixture.command)
        else:
            await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
        before = fixture.current()
        assert before.project.import_issues
        snapshot = snapshot_identity(before)
        inference = len(fixture.transport.calls)
        exporter = TemplateExporter(pipeline,
            TemplateRendererIdentity(id='controlled', version='1', sha256=digest('renderer')), render)
        pending = asyncio.create_task(exporter.export(fixture.project, snapshot))
        assert await asyncio.to_thread(entered.wait, 15)
        def edit(workspace):
            workspace.document_revision += 1
            workspace.project.document.revision = workspace.document_revision
            workspace.project.document.blocks()[0].content[0].text = 'Later authored text'
            return workspace
        await asyncio.to_thread(pipeline.checkpoint, fixture.project, edit)
        release.set()
        result = await pending
        current = fixture.current()
        assert result.attempt.state == 'completed' and result.snapshot == snapshot
        assert current.document_revision == snapshot.document_revision + 1
        assert calls[0].document == before.project.document and calls[0].facts == before.project.facts
        assert 'Later authored text' in fixture.text() and current.project.renders[-1].document_revision == snapshot.document_revision
        assert current.project.template_operations[0].publication.state == 'saved'
        assert len(fixture.transport.calls) == inference == 1
        assert all('diagnostics' not in str(block.model_dump()) for block in calls[0].document.blocks())
    finally:
        release.set()
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()


def owned_exporter(owner, render=None, *, render_async=None):
    return TemplateExporter(owner, TemplateRendererIdentity(id='controlled', version='1', sha256=digest('renderer')),
        render, render_async=render_async)


@pytest.mark.asyncio
async def test_async_exporter_awaits_renderer_directly_and_requires_one_callback(tmp_path):
    fixture, owner = authored_owner(tmp_path)
    async def render(_request):
        assert asyncio.current_task() is current
        return b'controlled asynchronous artifact'
    current = asyncio.current_task()
    with pytest.raises(ValueError):
        owned_exporter(owner)
    with pytest.raises(ValueError):
        owned_exporter(owner, lambda _: b'bytes', render_async=render)
    with pytest.raises(ValueError):
        owned_exporter(owner, render)
    result = await owned_exporter(owner, render_async=render).export(fixture.project, snapshot_identity(fixture.current()))
    assert result.attempt.state == 'completed' and not owner.publisher.template_export_tasks


@pytest.mark.asyncio
async def test_cancel_before_dispatch_marks_captured_attempt_failed_without_rendering(tmp_path, monkeypatch):
    fixture, owner = authored_owner(tmp_path, cleanup_seconds=1)
    entered, release = threading.Event(), threading.Event()
    publish = fixture.publisher.snapshot
    def blocked(*args, **kwargs):
        saved = publish(*args, **kwargs)
        if saved[0].project.exports[-1].state == 'pending':
            entered.set()
            assert release.wait(5)
        return saved
    monkeypatch.setattr(fixture.publisher, 'snapshot', blocked)
    async def render(_request):
        raise AssertionError('cancelled pending attempt must not dispatch')
    task = asyncio.create_task(owned_exporter(owner, render_async=render).export(fixture.project, snapshot_identity(fixture.current())))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    attempt = fixture.current().project.exports[-1]
    assert attempt.state == 'failed' and attempt.error_code == 'CANCELLED'
    assert not owner.artifacts and not owner.publisher.template_export_tasks


@pytest.mark.asyncio
async def test_async_renderer_cleanup_precedes_durable_cancel_outcome(tmp_path):
    fixture, owner = authored_owner(tmp_path)
    before = fixture.current()
    entered, drained = asyncio.Event(), asyncio.Event()
    async def render(_request):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            drained.set()
    task = asyncio.create_task(owned_exporter(owner, render_async=render).export(fixture.project, snapshot_identity(before)))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    after = fixture.current()
    assert drained.is_set() and after.project.exports[-1].error_code == 'CANCELLED'
    assert after.project.document == before.project.document and after.project.facts == before.project.facts
    assert not after.project.renders and not owner.artifacts


@pytest.mark.asyncio
async def test_cancelled_sync_renderer_remains_owned_until_drain_and_cannot_publish_late_bytes(tmp_path):
    fixture, owner = authored_owner(tmp_path, cleanup_seconds=.03)
    entered, release = threading.Event(), threading.Event()
    def render(_request):
        entered.set()
        assert release.wait(5)
        return b'late controlled artifact must not publish'
    task = asyncio.create_task(owned_exporter(owner, render).export(fixture.project, snapshot_identity(fixture.current())))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            await task
        assert {key[2] for key in fixture.publisher.template_export_tasks} == {'render', 'cleanup'}
        assert fixture.current().project.exports[-1].state == 'running'
        assert fixture.project in owner.checkpoint_fences and not owner.artifacts
    finally:
        release.set()
        await asyncio.gather(*fixture.publisher.template_export_tasks.values())
    assert fixture.current().project.exports[-1].error_code == 'CANCELLED'
    assert not fixture.current().project.renders and not owner.artifacts
    assert not fixture.publisher.template_export_tasks and fixture.project not in owner.checkpoint_fences


@pytest.mark.asyncio
async def test_cancel_after_terminal_commit_returns_actual_completed_outcome(tmp_path, monkeypatch):
    fixture, owner = authored_owner(tmp_path, cleanup_seconds=1)
    entered, release = threading.Event(), threading.Event()
    publish = fixture.publisher.snapshot
    def blocked(*args, **kwargs):
        saved = publish(*args, **kwargs)
        if saved[0].project.exports[-1].state == 'completed':
            entered.set()
            assert release.wait(5)
        return saved
    monkeypatch.setattr(fixture.publisher, 'snapshot', blocked)
    artifact = b'controlled committed artifact'
    task = asyncio.create_task(owned_exporter(owner, lambda _: artifact).export(fixture.project, snapshot_identity(fixture.current())))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
    finally:
        release.set()
    result = await task
    assert result.attempt.state == 'completed' and result.artifact == artifact
    assert fixture.current().project.exports[-1] == result.attempt


@pytest.mark.asyncio
async def test_terminal_checkpoint_failure_requires_actual_recovery_and_keeps_possible_artifact(tmp_path, monkeypatch):
    fixture, owner = authored_owner(tmp_path)
    publish = fixture.publisher.snapshot
    def failed_ack(*args, **kwargs):
        saved = publish(*args, **kwargs)
        if saved[0].project.exports[-1].state == 'completed':
            raise OSError('controlled lost acknowledgment after durable commit')
        return saved
    monkeypatch.setattr(fixture.publisher, 'snapshot', failed_ack)
    artifact = b'controlled committed artifact'
    with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
        await owned_exporter(owner, lambda _: artifact).export(fixture.project, snapshot_identity(fixture.current()))
    assert fixture.project in owner.pending_checkpoints and fixture.project in owner.checkpoint_fences
    actual = await owner.reconcile_checkpoint(fixture.project)
    attempt = actual.project.exports[-1]
    assert attempt.state == 'completed' and owner.artifacts[(fixture.project, attempt.id)] == artifact
    assert not owner.pending_checkpoints


@pytest.mark.asyncio
async def test_capture_publication_retry_reuses_one_attempt_and_one_request(tmp_path, monkeypatch):
    fixture, owner = authored_owner(tmp_path)
    publish, captures = fixture.publisher.snapshot, []
    def retry(*args, **kwargs):
        after = args[2]
        if after.project.exports[-1].state == 'pending':
            captures.append(after.project.export_inputs[-1].model_copy(deep=True))
            if len(captures) == 1:
                raise BackgroundFailure('DEPENDENCY_CHANGED')
        return publish(*args, **kwargs)
    monkeypatch.setattr(fixture.publisher, 'snapshot', retry)
    result = await owned_exporter(owner, lambda _: b'controlled artifact').export(fixture.project, snapshot_identity(fixture.current()))
    assert len(captures) == 2 and captures[0] == captures[1]
    assert len(fixture.current().project.exports) == 1 and result.attempt.id == captures[0].attempt_id


@pytest.mark.asyncio
async def test_cancelling_an_export_waiting_for_metadata_does_not_reconcile_another_export(tmp_path, monkeypatch):
    fixture, owner = authored_owner(tmp_path)
    entered, release = threading.Event(), threading.Event()
    publish = fixture.publisher.snapshot
    def blocked(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(30)
        return publish(*args, **kwargs)
    monkeypatch.setattr(fixture.publisher, 'snapshot', blocked)
    snapshot = snapshot_identity(fixture.current())
    first = asyncio.create_task(owned_exporter(owner, lambda _: b'first artifact').export(fixture.project, snapshot))
    second = None
    try:
        assert await asyncio.to_thread(entered.wait, 15)
        original_task = owner.pending_checkpoints[fixture.project]
        second = asyncio.create_task(owned_exporter(owner, lambda _: b'cancelled artifact').export(fixture.project, snapshot))
        await asyncio.sleep(0)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(second, 2)
        assert owner.pending_checkpoints[fixture.project] is original_task
        assert not owner.checkpoint_fences
    finally:
        release.set()
        await first
        if second is not None:
            await asyncio.gather(second, return_exceptions=True)
    assert len(fixture.current().project.exports) == 1
    assert fixture.current().project.exports[0].state == 'completed'
