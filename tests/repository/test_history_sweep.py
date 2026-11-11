"""History files no import record names are removed after the outcome commit and on close (R8); the live record, a
resumable import and a sidecar keep theirs."""

import hashlib
import logging
import os
from pathlib import Path

import pytest

from packages.resume_core import storage
from packages.resume_core.models.template_workspace import history_bytes
from packages.resume_core.repository.project_repository import blob_path
from tests.templates.pipeline_fixtures import resume_command
from tests.templates.template_runtime_fixtures import RuntimeFixture

LATER = '2026-10-21T00:00:01+00:00'


class Crash(BaseException):
    """The process dies here: nothing after this point runs."""


def files(fixture):
    return sorted(path.name for path in (fixture.directory / 'history').iterdir())


def named(fixture):
    workspace = fixture.repository.read(fixture.project)
    return sorted(blob_path(fixture.directory, 'history', ref.sha256).name for ref in workspace.project.import_history)


def unnamed_record(fixture, operation):
    """A record file nothing names, as builds before R8 left the first record of each publication."""
    raw = history_bytes(operation)
    path = blob_path(fixture.directory, 'history', hashlib.sha256(raw).hexdigest())
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def new_process(fixture):
    """A new service on the same store; the crashed one closes nothing."""
    fixture.repository = fixture.open_repository()
    fixture.pipeline = fixture.fresh_pipeline()


def crash_on_project_file(monkeypatch):
    original = os.replace
    def replace(source, target):
        if str(target).endswith('workspace.json'):
            raise Crash()
        return original(source, target)
    monkeypatch.setattr(storage.os, 'replace', replace)


async def published(fixture):
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and result.publication.state == 'saved'
    return result


@pytest.mark.asyncio
async def test_an_import_leaves_only_the_history_file_its_record_names(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    result = await published(fixture)
    # The publication commit wrote the record in state `finalizing`; the outcome commit's record replaced it.
    assert len(named(fixture)) == 1 and files(fixture) == named(fixture)
    fixture.restart()
    assert fixture.current().project.template_operations == [result]


@pytest.mark.asyncio
async def test_a_crash_in_the_outcome_commit_keeps_the_live_record_and_the_resume_leaves_only_its_own(
        tmp_path, monkeypatch):
    fixture = RuntimeFixture(tmp_path)
    record = fixture.pipeline.record_publication
    def crashing(*args):
        # The outcome's record file is written; the process dies before the project file names it.
        crash_on_project_file(monkeypatch)
        return record(*args)
    monkeypatch.setattr(fixture.pipeline, 'record_publication', crashing)
    with pytest.raises(Crash):
        await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    monkeypatch.undo()
    new_process(fixture)
    live = named(fixture)
    assert len(live) == 1 and len(files(fixture)) == 2
    fixture.repository.close(fixture.project)
    # The record the publication commit wrote is still the live one, and its import is resumable.
    assert files(fixture) == live
    operation = fixture.current().project.template_operations[0]
    assert operation.state == 'finalizing' and operation.publication.state == 'pending'
    resumed = await fixture.pipeline.recover(fixture.project, operation.id)
    assert resumed.state == 'published' and resumed.publication.state == 'saved'
    assert files(fixture) == named(fixture) != live
    fixture.restart()
    assert fixture.current().project.template_operations == [resumed]


@pytest.mark.asyncio
async def test_a_crash_in_the_publication_commit_keeps_the_pre_draft_files_until_the_resume_publishes(
        tmp_path, monkeypatch):
    fixture = RuntimeFixture(tmp_path)
    replace = fixture.repository.replace
    def crashing(project_id, **options):
        if options['reason'] == 'publication':
            crash_on_project_file(monkeypatch)
        return replace(project_id, **options)
    fixture.repository.replace = crashing
    with pytest.raises(Crash):
        await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    monkeypatch.undo()
    new_process(fixture)
    leftover = files(fixture)
    assert fixture.repository.read(fixture.project).project is None and len(leftover) == 1
    # A pre-draft names no record file, and its own import still runs: when in doubt, every file stays.
    fixture.repository.close(fixture.project)
    assert files(fixture) == leftover
    operation = fixture.current().pre_draft.template_operations[0]
    resumed = await fixture.pipeline.run(fixture.project, resume_command(operation), admitted=fixture.admitted)
    assert resumed.publication.state == 'saved'
    assert len(named(fixture)) == 1 and files(fixture) == named(fixture)


@pytest.mark.asyncio
async def test_an_old_project_with_unnamed_history_files_is_cleaned_when_it_closes(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    result = await published(fixture)
    live = named(fixture)
    stale = unnamed_record(fixture, result.model_copy(update={'state': 'finalizing'}))
    # A record write the process did not finish.
    partial = fixture.directory / 'history' / '.foldcv-write-interrupted'
    partial.write_bytes(history_bytes(result)[:100])
    partial.chmod(0o600)
    new_process(fixture)
    assert fixture.current().project.template_operations == [result] and stale.exists() and partial.exists()
    fixture.repository.close(fixture.project)
    assert not stale.exists() and not partial.exists() and files(fixture) == live
    assert fixture.current().project.template_operations == [result]


@pytest.mark.asyncio
async def test_a_sidecar_keeps_every_history_file_until_it_is_removed(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    result = await published(fixture)
    workspace = fixture.repository.read(fixture.project)
    earlier = result.model_copy(update={'last_observed_at': LATER})
    stale = unnamed_record(fixture, earlier)
    # A sidecar a commit folded but could not remove; its operation is the record in the unnamed file.
    fixture.sidecar.write(fixture.project, workspace.project_revision - 1, earlier, workspace.project.facts)
    fixture.repository.close(fixture.project)
    assert stale.exists()
    fixture.sidecar.discard(fixture.project, result.id)
    fixture.repository.close(fixture.project)
    assert not stale.exists() and files(fixture) == named(fixture)


@pytest.mark.asyncio
async def test_a_failed_removal_changes_nothing_and_the_next_sweep_removes_the_file(tmp_path, monkeypatch, caplog):
    fixture = RuntimeFixture(tmp_path)
    result = await published(fixture)
    stale = unnamed_record(fixture, result.model_copy(update={'state': 'finalizing'}))
    unlink = Path.unlink
    def refused(path, *args, **kwargs):
        if path == stale:
            raise PermissionError('open in another process')
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', refused)
    with caplog.at_level(logging.WARNING):
        fixture.repository.close(fixture.project)
    monkeypatch.undo()
    assert stale.exists() and 'history file left for a later sweep' in caplog.text
    assert fixture.current().project.template_operations == [result]
    fixture.repository.close(fixture.project)
    assert not stale.exists() and files(fixture) == named(fixture)


@pytest.mark.asyncio
async def test_a_project_file_written_outside_the_repository_keeps_every_history_file(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    result = await published(fixture)
    stale = unnamed_record(fixture, result.model_copy(update={'state': 'finalizing'}))
    target = fixture.directory / 'workspace.json'
    copy = target.with_name('outside-write')
    copy.write_bytes(target.read_bytes())
    copy.chmod(0o600)
    os.replace(copy, target)
    # The session has not read the new file, so the records it names are not known.
    fixture.repository.close(fixture.project)
    assert stale.exists()
    fixture.repository.read(fixture.project)
    fixture.repository.close(fixture.project)
    assert not stale.exists() and files(fixture) == named(fixture)
