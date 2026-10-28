"""Cancel and delete of running work: a cancel survives a restart and resume repeats no finished call, the publication
commit decides a cancelled import, and a delete stops the project's work, frees its permit and leaves no import files
(plan 2.7, SR00 flag 2)."""

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from packages.resume_core.models.projects import DeleteRequestV1
from packages.resume_core.project_repository import RepositoryFailure
from packages.resume_core.template_import import spent_calls
from resume_api.inference_admission import InferenceAdmission
from resume_api.projects import rewrite
from resume_api.projects.errors import ProjectFailure
from resume_api.projects.imports import ImportCommand, ImportService
from resume_api.projects.service import ProjectService
from tests.templates.pipeline_fixtures import blocks_package
from tests.templates.template_runtime_fixtures import RuntimeFixture, import_task


def services(fixture, **options):
    projects = ProjectService(fixture.repository)
    projects.imports = ImportService(projects, fixture.pipeline, commands=lambda *_args: fixture.command, **options)
    return projects


async def run_import(projects, fixture):
    identifier = await projects.imports.start(fixture.project, ImportCommand(kind='start', clientRequestId='request'),
        asyncio.Event())
    await projects.imports.runners[identifier]
    return next(value for value in projects.tasks.list(fixture.project) if value['id'] == identifier)


def cancel_after(fixture, projects, commit):
    """Cancel the running import right after the repository commit that `commit(options)` picks."""
    replace = fixture.repository.replace
    def replacing(project_id, **options):
        outcome = replace(project_id, **options)
        if commit(options):
            for task in projects.tasks.running(fixture.project, 'import'):
                projects.tasks.cancel(task.id)
        return outcome
    fixture.repository.replace = replacing


def finalizing(options):
    workspace = options['workspace']
    return options['reason'] == 'import' and any(operation.state == 'finalizing'
        for operation in (workspace.project or workspace.pre_draft).template_operations)


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_at,resumed_calls', [(0, 2), (3, 0)])
async def test_a_cancelled_import_stays_unsaved_after_a_restart_and_resume_repeats_no_finished_call(tmp_path, cancel_at,
        resumed_calls):
    # Two blocks, two calls each. A cancel during block one stops before block two; one during the last review stops
    # before publication, and the resume publishes without a model call.
    fixture = RuntimeFixture(tmp_path, captured=blocks_package(2), cap=20, fallback=False)
    projects = services(fixture)
    original = fixture.transport.generate
    def generate(request, cancel):
        if len(fixture.transport.calls) == cancel_at:
            for task in projects.tasks.running(fixture.project, 'import'):
                projects.tasks.cancel(task.id)
        return original(request, cancel)
    fixture.transport.generate = generate
    identifier = await projects.imports.start(fixture.project, ImportCommand(kind='start', clientRequestId='request'),
        asyncio.Event())
    await projects.imports.runners[identifier]
    [status] = projects.tasks.list(fixture.project)
    assert (status['state'], status['error']) == ('cancelled', None)
    calls = len(fixture.transport.calls)
    assert calls == 4 - resumed_calls
    fixture.restart()
    current = fixture.current()
    assert current.project is None
    operation = current.pre_draft.template_operations[0]
    assert operation.state != 'published' and spent_calls(operation) == calls
    fixture.transport.generate = original
    resumed = await import_task(fixture, kind='resume', operation_id=operation.id)
    assert (resumed['state'], resumed['error']) == ('succeeded', None)
    published = fixture.current().project.template_operations[0]
    assert published.state == 'published' and published.capture == operation.capture
    assert len(fixture.transport.calls) == spent_calls(published) == calls + resumed_calls == 4
    assert [task.state for task in published.tasks] == ['accepted', 'accepted']


@pytest.mark.asyncio
async def test_a_cancel_before_the_publication_commit_leaves_the_import_unpublished_and_resumable(tmp_path):
    # The cancel came after the finalization was saved; the import still published and its task said cancelled.
    fixture = RuntimeFixture(tmp_path)
    projects = services(fixture)
    cancel_after(fixture, projects, finalizing)
    status = await run_import(projects, fixture)
    assert (status['state'], status['error']) == ('cancelled', None)
    operation = fixture.current().pre_draft.template_operations[0]
    assert operation.state == 'finalizing' and operation.publication.state != 'saved'
    del fixture.repository.replace
    resumed = await import_task(fixture, kind='resume', operation_id=operation.id)
    assert (resumed['state'], resumed['error']) == ('succeeded', None)
    assert fixture.current().project.template_operations[0].state == 'published' and len(fixture.transport.calls) == 2


@pytest.mark.asyncio
async def test_a_cancel_after_the_publication_commit_leaves_the_task_succeeded(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    projects = services(fixture)
    cancel_after(fixture, projects, lambda options: options['reason'] == 'publication')
    status = await run_import(projects, fixture)
    assert (status['state'], status['error']) == ('succeeded', None)
    assert fixture.current().project.template_operations[0].state == 'published'


@pytest.mark.asyncio
async def test_deleting_a_project_during_its_import_cancels_the_import_and_then_removes_its_files(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    projects = services(fixture)
    entered, released = threading.Event(), []
    original = fixture.transport.generate
    def generate(request, cancel):
        if not entered.is_set():
            entered.set()
            # The delete sets the task's cancel event, which the running call receives.
            released.append(cancel.wait(10))
        return original(request, cancel)
    fixture.transport.generate = generate
    identifier = await projects.imports.start(fixture.project, ImportCommand(kind='start', clientRequestId='request'),
        asyncio.Event())
    assert await asyncio.to_thread(entered.wait, 10)
    directory = fixture.directory
    assert (directory / 'imports').is_dir()
    # The delete waits, in its worker thread, until the cancelled import has ended; it was refused at once before.
    deleted = await asyncio.to_thread(projects.delete, fixture.project, DeleteRequestV1(confirmed=True))
    assert deleted['deleted'] is True and deleted['cleanupStatus'] == 'complete'
    assert released == [True] and identifier not in projects.imports.runners
    assert not directory.exists() and projects.tasks.list(fixture.project) == []
    with pytest.raises(RepositoryFailure, match='PROJECT_DELETED'):
        fixture.repository.open(fixture.project)


@pytest.mark.asyncio
async def test_deleting_a_project_frees_the_permit_its_stopped_import_kept(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    fixture.transport.cleanup_unknown = True
    admission = InferenceAdmission()
    projects = services(fixture, admission=admission)
    assert (await run_import(projects, fixture))['state'] == 'failed'
    # An unproven process end keeps the permit; nothing could prove it once the project is gone.
    assert admission.locked() and fixture.project in projects.imports.retained
    await asyncio.to_thread(projects.delete, fixture.project, DeleteRequestV1(confirmed=True))
    assert not admission.locked() and projects.imports.retained == {}


@pytest.mark.asyncio
async def test_deleting_a_project_stops_its_rewrite_preview_through_the_rewrite_cancel(tmp_path, monkeypatch):
    fixture = RuntimeFixture(tmp_path)
    projects = services(fixture)
    cancels = {}
    async def rewrite_text(project_id, request_id, _instruction, _source):
        stop = cancels[(project_id, request_id)] = threading.Event()
        await asyncio.to_thread(stop.wait, 10)
        raise ProjectFailure('CANCELLED', 409)
    def rewrite_cancel(project_id, request_id):
        stop = cancels.get((project_id, request_id))
        if stop is not None:
            stop.set()
        return stop is not None
    projects.rewrite_text, projects.rewrite_cancel = rewrite_text, rewrite_cancel
    monkeypatch.setattr(rewrite, 'preview_source', lambda *_args: 'Selected text')
    payload = SimpleNamespace(request_id='rewrite-1', instruction='Shorter', snapshot=None, range=None)
    preview = asyncio.create_task(rewrite.preview(projects, fixture.project, payload))
    while not cancels:
        await asyncio.sleep(0.01)
    # The rewrite watches only its own cancel: the task event alone kept the delete refused until the model returned.
    deleted = await asyncio.to_thread(projects.delete, fixture.project, DeleteRequestV1(confirmed=True))
    assert deleted['deleted'] is True
    with pytest.raises(ProjectFailure, match='CANCELLED'):
        await preview


def test_a_deletion_is_refused_while_work_outlives_its_wait(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    projects = services(fixture)
    export = projects.tasks.start(fixture.project, 'export', stage='rendering')
    with pytest.raises(RepositoryFailure, match='REQUEST_IN_PROGRESS'):
        projects.delete(fixture.project, DeleteRequestV1(confirmed=True), wait=0.2)
    assert export.cancel.is_set() and fixture.repository.read(fixture.project).project_id == fixture.project
    assert projects.tasks.start(fixture.project, 'import').state == 'running'


@pytest.mark.asyncio
@pytest.mark.parametrize('busy', ['start', 'call'])
async def test_an_import_waits_for_a_busy_project_lock_off_the_event_loop(tmp_path, busy):
    # Another request keeps the project lock (a long commit); the import's open, pin and reads waited on the loop.
    fixture = RuntimeFixture(tmp_path)
    projects = services(fixture)
    session = fixture.repository.open(fixture.project)
    held, release = threading.Event(), threading.Event()
    def hold():
        with session.lock:
            held.set()
            release.wait(10)
    original = fixture.transport.generate
    def generate(request, cancel):
        result = original(request, cancel)
        if busy == 'call' and not held.is_set():
            threading.Thread(target=hold, daemon=True).start()
            held.wait(5)
        return result
    fixture.transport.generate = generate
    if busy == 'start':
        threading.Thread(target=hold, daemon=True).start()
    identifier = await projects.imports.start(fixture.project, ImportCommand(kind='start', clientRequestId='request'),
        asyncio.Event())
    # This loop keeps turning while the import waits for the lock; a blocked event loop stops it until the hold ends.
    gaps, last, after = [], time.monotonic(), 0
    while after < 20 and len(gaps) < 1000:
        await asyncio.sleep(0.01)
        gaps.append(time.monotonic() - last)
        last = time.monotonic()
        after += held.is_set()
    release.set()
    await projects.imports.runners[identifier]
    assert held.is_set() and max(gaps) < 1
    assert projects.tasks.list(fixture.project)[0]['state'] == 'succeeded'
