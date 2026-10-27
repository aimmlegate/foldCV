"""Cancel and delete of a running import task: a cancel survives a restart, resume repeats no finished call, and a
deleted project leaves no import files (plan 2.7, SR00 flag 2)."""

import asyncio
import threading

import pytest

from packages.resume_core.models.projects import DeleteRequestV1
from packages.resume_core.project_repository import RepositoryFailure
from packages.resume_core.template_import import spent_calls
from resume_api.projects.imports import ImportCommand, ImportService
from resume_api.projects.service import ProjectService
from tests.templates.pipeline_fixtures import blocks_package
from tests.templates.template_runtime_fixtures import RuntimeFixture, import_task


def services(fixture):
    projects = ProjectService(fixture.repository)
    projects.imports = ImportService(projects, fixture.pipeline, commands=lambda *_args: fixture.command)
    return projects


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
    with pytest.raises(RepositoryFailure, match='REQUEST_IN_PROGRESS'):
        projects.delete(fixture.project, DeleteRequestV1(confirmed=True))
    await projects.imports.runners[identifier]
    assert released == [True]
    [status] = projects.tasks.list(fixture.project)
    assert status['state'] == 'cancelled' and fixture.current().project is None
    deleted = projects.delete(fixture.project, DeleteRequestV1(confirmed=True))
    assert deleted['deleted'] is True and deleted['cleanupStatus'] == 'complete'
    assert not directory.exists() and projects.tasks.list(fixture.project) == []
    with pytest.raises(RepositoryFailure, match='PROJECT_DELETED'):
        fixture.repository.open(fixture.project)
