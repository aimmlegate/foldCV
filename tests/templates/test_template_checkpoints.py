"""Export metadata uses targeted canonical checkpoints without import authority."""

import asyncio
import threading

import pytest

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_history import digest_bytes
from packages.resume_core.models.template_render import TemplateRendererIdentity
from packages.resume_core.template_export import snapshot_identity
from packages.resume_core.template_import import digest
from resume_api.importer.template_checkpoints import TemplateCheckpoints
from resume_api.importer.template_export import TemplateExporter
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_template_publication import TemplatePublicationFixture
from tests.templates.storage_fixtures import workspace as authored_workspace


async def setup(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    owner = TemplateCheckpoints(fixture.publisher, originals=fixture.originals, artifacts=fixture.pipeline.artifacts,
        wall=lambda: fixture.now, export_only=True)
    return fixture, owner


def exporter(owner, render=lambda _request: b'controlled metadata artifact; not DOCX evidence'):
    return TemplateExporter(owner, TemplateRendererIdentity(id='controlled', version='1', sha256=digest('renderer')), render)


def authored_owner(tmp_path, **options):
    fixture = TemplatePublicationFixture(tmp_path, create=False)
    value, originals = authored_workspace()
    fixture.project = value.project_id
    fixture.originals = {(fixture.project, key): raw for key, raw in originals.items()}
    fixture.canonical.save(value, fixture.originals, {})
    fixture.jobs.open(fixture.project)
    owner = TemplateCheckpoints(fixture.publisher, originals=fixture.originals, wall=lambda: fixture.now,
        export_only=True, **options)
    return fixture, owner


@pytest.mark.asyncio
async def test_export_only_owner_shares_lock_without_replacing_import_authority(tmp_path):
    fixture, owner = await setup(tmp_path)
    authority = fixture.publisher.template_authority
    assert owner.checkpoint_locks is fixture.pipeline.checkpoint_locks is fixture.publisher.template_checkpoint_locks
    before = fixture.current()
    calls = len(fixture.transport.calls)
    result = await exporter(owner).export(fixture.project, snapshot_identity(before))
    after = fixture.current()
    assert result.attempt.state == 'completed'
    assert after.project.document == before.project.document and after.project.facts == before.project.facts
    assert fixture.publisher.template_authority is authority and len(fixture.transport.calls) == calls


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['document', 'facts', 'source', 'operation', 'terminal'])
async def test_export_only_scope_rejects_authoring_and_terminal_state_changes(tmp_path, field):
    fixture, owner = await setup(tmp_path)
    result = await exporter(owner).export(fixture.project, snapshot_identity(fixture.current()))
    before = fixture.current()
    def change(workspace):
        project = workspace.project
        if field == 'document':
            project.document.blocks()[0].content[0].text = 'Unauthorized export write'
        elif field == 'facts':
            project.facts.revision += 1
        elif field == 'source':
            project.sources[0].original_name = 'Changed by export'
        elif field == 'operation':
            project.template_operations[0].state = 'fenced'
        else:
            attempt = next(value for value in project.exports if value.id == result.attempt.id)
            attempt.state, attempt.error_code, attempt.artifact_hash = 'failed', 'CANCELLED', None
        return workspace
    with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
        owner.checkpoint(fixture.project, change)
    assert fixture.current() == before


@pytest.mark.asyncio
async def test_targeted_export_retry_preserves_a_manual_edit_between_read_and_publish(tmp_path, monkeypatch):
    fixture, owner = await setup(tmp_path)
    before = fixture.current()
    publish = fixture.publisher.snapshot
    interleaved = False
    def snapshot(project, checksum, after, command, **options):
        nonlocal interleaved
        if not interleaved and after.project.exports and after.project.exports[-1].state == 'running':
            interleaved = True
            def edit(workspace):
                workspace.document_revision += 1
                workspace.project.document.revision = workspace.document_revision
                workspace.project.document.blocks()[0].content[0].text = 'Concurrent human wording'
                return workspace
            current = fixture.current()
            changed = edit(current.model_copy(deep=True))
            changed.project_revision += 1
            changed.project.revision = changed.project_revision
            publish(project, digest_bytes(current), changed, 'controlled-manual-edit', originals=fixture.originals,
                artifacts=owner.artifacts, images=owner.images)
        return publish(project, checksum, after, command, **options)
    monkeypatch.setattr(fixture.publisher, 'snapshot', snapshot)
    requests = []
    def render(request):
        requests.append(request)
        return b'controlled earlier snapshot artifact'
    result = await exporter(owner, render).export(fixture.project, snapshot_identity(before))
    after = fixture.current()
    assert interleaved and result.attempt.state == 'completed'
    assert after.project.document.blocks()[0].content[0].text == 'Concurrent human wording'
    assert requests[0].document == before.project.document
    assert result.snapshot == snapshot_identity(before)


@pytest.mark.asyncio
async def test_two_exports_keep_independent_captures_and_terminal_outcomes(tmp_path):
    fixture, owner = await setup(tmp_path)
    entered, release = threading.Event(), threading.Event()
    first_snapshot = snapshot_identity(fixture.current())
    def render(_request):
        entered.set()
        assert release.wait(15)
        return b'first controlled artifact'
    pending = asyncio.create_task(exporter(owner, render).export(fixture.project, first_snapshot))
    try:
        assert await asyncio.to_thread(entered.wait, 10)
        second_snapshot = snapshot_identity(fixture.current())
        second = await exporter(owner).export(fixture.project, second_snapshot)
        release.set()
        first = await pending
        current = fixture.current()
        assert first.attempt.id != second.attempt.id
        assert first.snapshot == first_snapshot and second.snapshot == second_snapshot
        assert len(current.project.export_inputs) == 2
        assert all(value.state == 'completed' for value in current.project.exports)
        assert owner.artifacts[(fixture.project, first.attempt.id)] == first.artifact
        assert owner.artifacts[(fixture.project, second.attempt.id)] == second.artifact
    finally:
        release.set()
        await pending


@pytest.mark.asyncio
async def test_checkpoint_timeout_retains_thread_and_blocks_sync_noop_until_reconciliation(tmp_path, monkeypatch):
    fixture, owner = authored_owner(tmp_path, checkpoint_seconds=.03, cleanup_seconds=.03)
    entered, release = threading.Event(), threading.Event()
    checkpoint = owner.checkpoint
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return checkpoint(*args, **kwargs)
    monkeypatch.setattr(owner, 'checkpoint', blocked)
    try:
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            await owner.checkpoint_async(fixture.project, lambda value: value)
        assert entered.is_set()
        retained = owner.pending_checkpoints[fixture.project]
        assert not retained.done() and not retained.cancelled()
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            checkpoint(fixture.project, lambda value: value)
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            fixture.publisher._writable(fixture.jobs.load(fixture.project))
        fixture.jobs.fences[fixture.project] = 'JOB_STORE_UNAVAILABLE'
    finally:
        release.set()
        await asyncio.gather(*owner.pending_checkpoints.values(), return_exceptions=True)
    current = await owner.reconcile_checkpoint(fixture.project)
    assert current == fixture.current()
    assert fixture.project not in owner.pending_checkpoints and fixture.project not in owner.checkpoint_fences
    assert fixture.jobs.fences[fixture.project] == 'JOB_STORE_UNAVAILABLE'


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [False, True])
async def test_recovery_has_bounded_retained_ownership_and_preserves_other_unknown_fence(tmp_path, monkeypatch, cancel):
    fixture, owner = authored_owner(tmp_path, checkpoint_seconds=.05, cleanup_seconds=.03)
    entered, release = threading.Event(), threading.Event()
    recover = fixture.publisher.recover
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return recover(*args, **kwargs)
    monkeypatch.setattr(fixture.publisher, 'recover', blocked)
    owner.fence_checkpoint(fixture.project)
    fixture.jobs.fences[fixture.project] = 'OUTCOME_UNKNOWN'
    task = asyncio.create_task(owner.reconcile_checkpoint(fixture.project))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else BackgroundFailure):
            await task
        retained = owner.pending_checkpoints[fixture.project]
        assert not retained.done() and not retained.cancelled()
        assert fixture.project in owner.checkpoint_fences
    finally:
        release.set()
        await asyncio.gather(*owner.pending_checkpoints.values(), return_exceptions=True)
    await owner.reconcile_checkpoint(fixture.project)
    assert fixture.project not in owner.checkpoint_fences
    assert fixture.jobs.fences[fixture.project] == 'OUTCOME_UNKNOWN'


@pytest.mark.asyncio
async def test_cancelled_checkpoint_drains_actual_thread_before_releasing_ownership(tmp_path, monkeypatch):
    fixture, owner = authored_owner(tmp_path, cleanup_seconds=1)
    entered, release = threading.Event(), threading.Event()
    checkpoint = owner.checkpoint
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return checkpoint(*args, **kwargs)
    monkeypatch.setattr(owner, 'checkpoint', blocked)
    task = asyncio.create_task(owner.checkpoint_async(fixture.project, lambda value: value))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert fixture.project in owner.pending_checkpoints
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fixture.project not in owner.pending_checkpoints and fixture.project not in owner.checkpoint_fences


@pytest.mark.asyncio
async def test_checkpoint_io_failure_stays_uncertain_until_authoritative_recovery(tmp_path, monkeypatch):
    fixture, owner = authored_owner(tmp_path)
    def broken(*_args, **_kwargs):
        raise OSError('controlled filesystem error')
    monkeypatch.setattr(owner, 'checkpoint', broken)
    with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
        await owner.checkpoint_async(fixture.project, lambda value: value)
    assert owner.pending_checkpoints[fixture.project].done() and fixture.project in owner.checkpoint_fences
    await owner.reconcile_checkpoint(fixture.project)
    assert fixture.project not in owner.pending_checkpoints and fixture.project not in owner.checkpoint_fences


@pytest.mark.asyncio
async def test_sync_checkpoint_refuses_async_owner_before_waiting_for_its_held_lock(tmp_path, monkeypatch):
    fixture, owner = authored_owner(tmp_path)
    entered, release = threading.Event(), threading.Event()
    publish = fixture.publisher.snapshot
    def blocked(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(30)
        return publish(*args, **kwargs)
    monkeypatch.setattr(fixture.publisher, 'snapshot', blocked)
    pending = asyncio.create_task(exporter(owner).export(fixture.project, snapshot_identity(fixture.current())))
    refused = None
    try:
        assert await asyncio.to_thread(entered.wait, 15)
        refused = asyncio.create_task(asyncio.to_thread(owner.checkpoint, fixture.project, lambda value: value))
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            await asyncio.wait_for(asyncio.shield(refused), 2)
    finally:
        release.set()
        await pending
        if refused is not None:
            await asyncio.gather(refused, return_exceptions=True)
