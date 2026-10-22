"""Isolated real service exports use captured workers without any model provider."""

import asyncio
import hashlib
import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.rich_api import RichGenerationState
from packages.resume_core.rendering.captured_docx import renderer_identity
from packages.resume_core.rendering.template import RenderFailure
from packages.resume_core.template_assembly import assemble_template
from packages.resume_core.template_export import capture_export, snapshot_identity
from resume_api.gui_projects import ProjectFailure
from resume_api.gui_rendering import RichDocxRenderer
from resume_api.importer.template_export import TemplateExporter
from resume_api.jobs.service import JobService
from resume_api.lifecycle import OperationFiles
from resume_api.rich_projects import RichProjectService
from tests.templates.pipeline_fixtures import source_draft
from tests.templates.test_captured_docx import emitted, xml
from tests.templates.test_materialize import admitted
from tests.templates.test_template_api import application, isolated_service
from tests.templates.test_template_employment import EmploymentFixture, scripted_employment
from tests.templates.employment_fixtures import employment_package, employment_source


async def service_for_export(tmp_path, *, unsupported=False, cleanup=True):
    if unsupported:
        src, raw = employment_source('F01')
        fixture = EmploymentFixture(tmp_path / 'controlled-import', captured=employment_package(), src=src, original_bytes=raw,
            scripted=scripted_employment(src, unsupported=True), cap=4, fallback=False)
        await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
        workspace = fixture.current()
        assert len(fixture.transport.calls) == 4 and workspace.project.import_issues
    else:
        operation, facts, package, src, raw = admitted()
        workspace = assemble_template(source_draft(operation, facts, captured=package, src=src), operation)
    service, identifier = isolated_service(tmp_path, workspace, {src.id: raw})
    jobs = JobService(service, None, lambda: SimpleNamespace(ready=False), enabled=False,
        template_cleanup_verified=lambda: cleanup)
    await jobs.start()
    return service, jobs, identifier


def edit_literal(service, identifier):
    before = service.storage.read_committed(identifier)[0]
    after = before.model_copy(deep=True)
    part = next(part for block in after.project.document.blocks() for part in block.content
        if part.type == 'text' and part.text)
    part.text = 'Concurrent human literal'
    after.project_revision += 1
    after.project.revision = after.project_revision
    after.document_revision += 1
    after.project.document.revision = after.document_revision
    service.template_jobs.publisher.snapshot(identifier, digest_bytes(before), after, 'controlled-human-edit',
        originals=service.originals, artifacts=service.artifacts, images=service.images)
    return after


@pytest.mark.asyncio
@pytest.mark.parametrize('unsupported', [False, True])
async def test_actual_http_export_returns_durable_captured_snapshot_and_docx_without_model_or_template_factory(tmp_path, unsupported):
    service, jobs, identifier = await service_for_export(tmp_path, unsupported=unsupported)
    before = service.storage.read_committed(identifier)[0]
    expected = snapshot_identity(before)
    assert jobs.templates is None and not jobs.runtime_available
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(service)), base_url='http://foldcv.test') as client:
            response = await client.post('/v1/rich/projects/' + identifier + '/export',
                json={'schemaVersion': 1, 'snapshot': expected.model_dump(mode='json', by_alias=True)})
        assert response.status_code == 200, response.text
        assert response.headers['content-type'] == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        assert response.headers['x-foldcv-sha256'] == hashlib.sha256(response.content).hexdigest()
        assert json.loads(response.headers['x-foldcv-snapshot']) == expected.model_dump(mode='json', by_alias=True)
        after = service.storage.read_committed(identifier)[0]
        attempt = after.project.exports[-1]
        assert attempt.id == response.headers['x-foldcv-export-attempt'] and attempt.state == 'completed'
        assert after.project.export_inputs[-1].snapshot == expected
        assert after.project.renders[-1].docx_sha256 == attempt.artifact_hash
        assert after.project.document == before.project.document and after.project.facts == before.project.facts
        text = emitted(xml(response.content))
        assert 'Example Labs' in text and '800 ms to 500 ms' in text and '80%' not in text
        assert 'diagnostics' not in text and after.project.import_issues == before.project.import_issues
        assert bool(after.project.import_issues) == unsupported
        assert service.response(identifier).durability == 'durable'
        assert not service.tasks and not service.files and not service.cancels
        assert not list(service.temp_root.glob('op-*'))
    finally:
        await service.shutdown()
        await jobs.shutdown()


@pytest.mark.asyncio
async def test_service_concurrent_edit_and_two_real_exports_keep_independent_snapshots(tmp_path):
    service, jobs, identifier = await service_for_export(tmp_path)
    first_snapshot = snapshot_identity(service.storage.read_committed(identifier)[0])
    entered, release = asyncio.Event(), asyncio.Event()
    actual = RichDocxRenderer()
    calls = []
    class DelayedRenderer:
        async def render_template(self, request, files):
            calls.append(request)
            if len(calls) == 1:
                entered.set()
                await release.wait()
            return await actual.render_template(request, files)
    service.renderer = DelayedRenderer()
    first = asyncio.create_task(service.export_template(identifier, first_snapshot))
    try:
        await asyncio.wait_for(entered.wait(), 15)
        changed = edit_literal(service, identifier)
        second_snapshot = snapshot_identity(changed)
        second = await service.export_template(identifier, second_snapshot)
        release.set()
        earlier = await first
        assert earlier.snapshot == first_snapshot and second.snapshot == second_snapshot
        assert earlier.attempt.id != second.attempt.id
        assert 'Concurrent human literal' not in emitted(xml(earlier.artifact))
        assert 'Concurrent human literal' in emitted(xml(second.artifact))
        current = service.storage.read_committed(identifier)[0]
        assert current.project.document == changed.project.document
        assert [value.state for value in current.project.exports] == ['completed', 'completed']
        assert service.response(identifier).workspace.project.document == changed.project.document
    finally:
        release.set()
        await asyncio.gather(first, return_exceptions=True)
        await service.shutdown()
        await jobs.shutdown()


@pytest.mark.asyncio
async def test_http_export_protocol_and_stale_capture_fail_before_attempt_or_dispatch(tmp_path):
    service, jobs, identifier = await service_for_export(tmp_path)
    snapshot = snapshot_identity(service.storage.read_committed(identifier)[0])
    stale = snapshot.model_copy(update={'document_hash': '0' * 64})
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(service)), base_url='http://foldcv.test') as client:
            path = '/v1/rich/projects/' + identifier + '/export'
            wrong = await client.post(path, json={})
            assert wrong.status_code == 409 and wrong.json()['error']['code'] == 'IMPORT_PROTOCOL_MISMATCH'
            rejected = await client.post(path, json={'schemaVersion': 1, 'snapshot': stale.model_dump(mode='json', by_alias=True)})
            assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'IMPORT_EXPORT_SNAPSHOT_STALE'
        assert not service.storage.read_committed(identifier)[0].project.exports and not service.tasks
    finally:
        await service.shutdown()
        await jobs.shutdown()


@pytest.mark.asyncio
async def test_http_retry_renders_retained_failure_capture_after_new_human_edit(tmp_path):
    service, jobs, identifier = await service_for_export(tmp_path)
    snapshot = snapshot_identity(service.storage.read_committed(identifier)[0])
    requests = []
    class FailedRenderer:
        async def render_template(self, request, _files):
            requests.append(request)
            raise RenderFailure('RICH_RENDER_FAILED')
    service.renderer = FailedRenderer()
    try:
        with pytest.raises(ProjectFailure, match='RICH_RENDER_FAILED'):
            await service.export_template(identifier, snapshot)
        failed = service.storage.read_committed(identifier)[0].project.exports[-1]
        changed = edit_literal(service, identifier)
        service.renderer = RichDocxRenderer()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(service)), base_url='http://foldcv.test') as client:
            response = await client.post('/v1/rich/projects/' + identifier + '/exports/' + failed.id + '/retry', json={})
        assert response.status_code == 200, response.text
        assert json.loads(response.headers['x-foldcv-snapshot']) == snapshot.model_dump(mode='json', by_alias=True)
        assert response.headers['x-foldcv-export-attempt'] != failed.id
        assert 'Concurrent human literal' not in emitted(xml(response.content))
        after = service.storage.read_committed(identifier)[0]
        assert after.project.document == changed.project.document
        assert after.project.export_inputs[0].request == after.project.export_inputs[1].request
        assert [value.state for value in after.project.exports] == ['failed', 'completed']
    finally:
        await service.shutdown()
        await jobs.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('shutdown', [False, True])
async def test_cancel_or_shutdown_stops_actual_owned_worker_before_failed_checkpoint(tmp_path, monkeypatch, shutdown):
    service, jobs, identifier = await service_for_export(tmp_path)
    entered = asyncio.Event()
    spawn = OperationFiles.spawn
    def observed(files, *args, **kwargs):
        process = spawn(files, *args, **kwargs)
        entered.set()
        return process
    monkeypatch.setattr(OperationFiles, 'spawn', observed)
    pending = asyncio.create_task(service.export_template(identifier, snapshot_identity(service.storage.read_committed(identifier)[0])))
    try:
        await asyncio.wait_for(entered.wait(), 15)
        key = next(iter(service.tasks))
        if shutdown:
            await service.shutdown()
        else:
            await service.cancel(*key)
        with pytest.raises(ProjectFailure):
            await pending
        attempt = service.storage.read_committed(identifier)[0].project.exports[-1]
        assert attempt.state == 'failed' and attempt.error_code == 'CANCELLED'
        assert not service.tasks and not service.files and not service.cancels
        assert not list(service.temp_root.glob('op-*'))
    finally:
        await asyncio.gather(pending, return_exceptions=True)
        await service.shutdown()
        await jobs.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('cleanup', [False, True])
async def test_startup_export_recovery_requires_owned_cleanup_and_preserves_completed_attempt(tmp_path, cleanup):
    service, jobs, identifier = await service_for_export(tmp_path)
    owner = service.template_checkpoints
    jobs.store.open(identifier)
    complete = await TemplateExporter(owner, renderer_identity(), lambda _: b'controlled recovery artifact, not DOCX').export(
        identifier, snapshot_identity(service.storage.read_committed(identifier)[0]))
    current = service.storage.read_committed(identifier)[0]
    attempt, captured = capture_export(current, snapshot_identity(current), renderer_identity())
    def pending(value):
        value.project.exports.append(attempt.model_copy(deep=True))
        value.project.export_inputs.append(captured.model_copy(deep=True))
        return value
    await owner.checkpoint_async(identifier, pending, operation_id=attempt.id)
    await service.shutdown()
    await jobs.shutdown()
    reopened = RichProjectService(tmp_path / 'reopened-workers', service.rules, lambda: (_ for _ in ()).throw(AssertionError('No inference')))
    fresh = JobService(reopened, None, lambda: SimpleNamespace(ready=False), enabled=False,
        template_cleanup_verified=lambda: cleanup)
    try:
        await fresh.start()
        actual = reopened.storage.read_committed(identifier)[0]
        assert actual.project.exports[0] == complete.attempt
        assert reopened.artifacts[(identifier, complete.attempt.id)] == complete.artifact
        last = actual.project.exports[-1]
        if cleanup:
            assert last.state == 'failed' and last.error_code == 'OPERATION_INTERRUPTED'
        else:
            assert last.state == 'pending' and identifier in reopened.template_checkpoints.checkpoint_fences
    finally:
        await reopened.shutdown()
        await fresh.shutdown()


@pytest.mark.asyncio
async def test_export_cache_read_and_adoption_cannot_regress_a_newer_cache(tmp_path, monkeypatch):
    service, jobs, identifier = await service_for_export(tmp_path)
    jobs.store.open(identifier)
    owner = service.template_checkpoints
    read = owner.read
    entered, release, second_started, second_read = (threading.Event() for _ in range(4))
    def blocked(project):
        value = read(project)
        if not entered.is_set():
            entered.set()
            assert release.wait(30)
        else:
            second_read.set()
        return value
    monkeypatch.setattr(owner, 'read', blocked)
    first = asyncio.create_task(asyncio.to_thread(service._adopt_template_export, identifier))
    second = None
    try:
        assert await asyncio.to_thread(entered.wait, 15)
        changed = edit_literal(service, identifier)
        def adopt_newer():
            second_started.set()
            service._adopt_template_export(identifier)
        second = asyncio.create_task(asyncio.to_thread(adopt_newer))
        assert await asyncio.to_thread(second_started.wait, 15)
        await asyncio.sleep(.03)
        assert not second_read.is_set()
        release.set()
        await asyncio.gather(first, second)
        assert service.read_memory(identifier).project.document == changed.project.document
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second is not None else []), return_exceptions=True)
        await service.shutdown()
        await jobs.shutdown()


@pytest.mark.asyncio
async def test_shutdown_drain_waits_for_cleanup_tasks_spawned_during_its_first_wait(tmp_path):
    service, jobs, identifier = await service_for_export(tmp_path)
    owner = service.template_checkpoints
    exporter = TemplateExporter(owner, renderer_identity(), lambda _: b'not executed')
    release_first, entered_inner, release_inner = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def inner():
        entered_inner.set()
        await release_inner.wait()
    async def first():
        await release_first.wait()
        exporter._retain((identifier, 'controlled-inner', 'cleanup'), inner(), retain_failure=True)
    exporter._retain((identifier, 'controlled-first', 'cleanup'), first(), retain_failure=True)
    draining = asyncio.create_task(service.drain_template_exports())
    try:
        await asyncio.sleep(0)
        release_first.set()
        await asyncio.wait_for(entered_inner.wait(), 2)
        await asyncio.sleep(.03)
        assert not draining.done()
        release_inner.set()
        await asyncio.wait_for(draining, 2)
        assert not owner.publisher.template_export_tasks
        service.template_export_stopping = True
        with pytest.raises(ProjectFailure, match='CANCELLED'):
            await service.export_template(identifier, snapshot_identity(service.storage.read_committed(identifier)[0]))
        assert not service.tasks
    finally:
        release_first.set()
        release_inner.set()
        await asyncio.gather(draining, return_exceptions=True)
        await service.shutdown()
        await jobs.shutdown()


@pytest.mark.asyncio
async def test_cache_io_error_cannot_replace_a_known_durable_export_result(tmp_path, monkeypatch):
    service, jobs, identifier = await service_for_export(tmp_path)
    owner = service.template_checkpoints
    read = owner.read
    def failed_cache(project):
        value = read(project)
        if value.project.exports and value.project.exports[-1].state == 'completed':
            raise OSError('controlled cache read failure after durable export')
        return value
    monkeypatch.setattr(owner, 'read', failed_cache)
    try:
        result = await service.export_template(identifier, snapshot_identity(service.storage.read_committed(identifier)[0]))
        actual = service.storage.read_committed(identifier)[0]
        assert result.attempt.state == 'completed' and actual.project.exports[-1] == result.attempt
        assert hashlib.sha256(result.artifact).hexdigest() == result.attempt.artifact_hash
        assert service.save_errors[identifier] == 'PROJECT_SAVE_FAILED'
        assert not service.tasks and not service.template_export_keys
    finally:
        await service.shutdown()
        await jobs.shutdown()


@pytest.mark.asyncio
async def test_service_cancel_propagates_uncertain_failure_checkpoint_and_retains_ownership(tmp_path, monkeypatch):
    service, jobs, identifier = await service_for_export(tmp_path)
    owner = service.template_checkpoints
    entered = asyncio.Event()
    class ControlledRenderer:
        async def render_template(self, _request, files):
            entered.set()
            while not files.closed:
                await asyncio.sleep(0)
            raise RenderFailure('RICH_RENDER_FAILED')
    service.renderer = ControlledRenderer()
    publish = jobs.publisher.snapshot
    def failed_cancel(*args, **kwargs):
        if args[2].project.exports[-1].state == 'failed':
            raise OSError('controlled cancellation checkpoint failure')
        return publish(*args, **kwargs)
    monkeypatch.setattr(jobs.publisher, 'snapshot', failed_cancel)
    task = asyncio.create_task(service.export_template(identifier, snapshot_identity(service.storage.read_committed(identifier)[0])))
    try:
        await asyncio.wait_for(entered.wait(), 15)
        key = next(iter(service.tasks))
        with pytest.raises(ProjectFailure, match='OUTCOME_UNKNOWN'):
            await service.cancel(*key)
        with pytest.raises(ProjectFailure, match='OUTCOME_UNKNOWN'):
            await task
        attempt = service.storage.read_committed(identifier)[0].project.exports[-1]
        assert attempt.state == 'running' and attempt.artifact_hash is None
        assert owner.checkpoint_owners[identifier] == attempt.id and identifier in owner.checkpoint_fences
        assert identifier in owner.pending_checkpoints and not service.artifacts
    finally:
        await asyncio.gather(task, return_exceptions=True)
        monkeypatch.setattr(jobs.publisher, 'snapshot', publish)
        await owner.reconcile_checkpoint(identifier)
        service._adopt_template_export(identifier)
        await service.recover_template_exports()
        await service.shutdown()
        await jobs.shutdown()


@pytest.mark.asyncio
async def test_http_cancel_targets_active_export_before_a_retained_completed_generation(tmp_path, monkeypatch):
    service, jobs, identifier = await service_for_export(tmp_path)
    entered = asyncio.Event()
    class ControlledRenderer:
        async def render_template(self, _request, files):
            entered.set()
            while not files.closed:
                await asyncio.sleep(0)
            raise RenderFailure('RICH_RENDER_FAILED')
    service.renderer = ControlledRenderer()
    generation = RichGenerationState(id='old-generation', status='completed', stage='render', errorCode=None)
    jobs.enabled = True
    service.background_jobs = jobs
    monkeypatch.setattr(jobs.fixed, 'generation', lambda _identifier: generation)
    async def wrong_cancel(*_args):
        raise AssertionError('active export cancellation must not target the old completed generation')
    monkeypatch.setattr(jobs, 'cancel', wrong_cancel)
    pending = asyncio.create_task(service.export_template(identifier, snapshot_identity(service.storage.read_committed(identifier)[0])))
    try:
        await asyncio.wait_for(entered.wait(), 15)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(service)), base_url='http://foldcv.test') as client:
            response = await client.post('/v1/rich/projects/' + identifier + '/cancel', json={})
        assert response.status_code == 200, response.text
        assert response.json()['workspace']['project']['exports'][-1]['errorCode'] == 'CANCELLED'
        assert response.json()['generation']['status'] == 'completed'
        with pytest.raises(ProjectFailure, match='CANCELLED'):
            await pending
        assert not service.template_export_keys and not service.tasks
    finally:
        await asyncio.gather(pending, return_exceptions=True)
        await service.shutdown()
        await jobs.shutdown()


@pytest.mark.asyncio
async def test_cancel_after_running_checkpoint_before_slot_admission_records_cancelled_without_dispatch(tmp_path, monkeypatch):
    service, jobs, identifier = await service_for_export(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    checkpoint = service.template_checkpoints.checkpoint_async
    async def gated(*args, **kwargs):
        saved = await checkpoint(*args, **kwargs)
        if saved.project.exports[-1].state == 'running':
            entered.set()
            await release.wait()
        return saved
    monkeypatch.setattr(service.template_checkpoints, 'checkpoint_async', gated)
    class ForbiddenRenderer:
        async def render_template(self, _request, _files):
            raise AssertionError('cancelled slot admission must not dispatch a worker')
    service.renderer = ForbiddenRenderer()
    before = service.storage.read_committed(identifier)[0]
    pending = asyncio.create_task(service.export_template(identifier, snapshot_identity(before)))
    cancellation = None
    try:
        await asyncio.wait_for(entered.wait(), 15)
        key = next(iter(service.tasks))
        cancellation = asyncio.create_task(service.cancel(*key))
        await asyncio.sleep(0)
        assert service.cancels[key].is_set()
        release.set()
        await asyncio.wait_for(cancellation, 15)
        with pytest.raises(ProjectFailure, match='CANCELLED'):
            await pending
        after = service.storage.read_committed(identifier)[0]
        assert after.project.exports[-1].state == 'failed' and after.project.exports[-1].error_code == 'CANCELLED'
        assert after.project.document == before.project.document and after.project.facts == before.project.facts
        assert not after.project.renders and not service.artifacts
        assert not service.tasks and not service.files and not service.cancels
        assert not list(service.temp_root.glob('op-*'))
    finally:
        release.set()
        await asyncio.gather(pending, *([cancellation] if cancellation is not None else []), return_exceptions=True)
        await service.shutdown()
        await jobs.shutdown()
