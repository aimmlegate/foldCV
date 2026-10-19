"""Existing service writers share the guarded canonical publication boundary."""

from types import SimpleNamespace

import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.rich_workspace import RichOperation
from packages.resume_core.models.agent import AgentSettingsRequest
from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_snapshot_merge import merge_snapshot
from packages.resume_core.rules import RulesStore
from tests.support.background_publication import PublicationFixture


def projects_for(fixture, directory):
    from resume_api.jobs.publication import JobPublication
    from resume_api.rich_projects import RichProjectService
    service = RichProjectService(directory / "operations", RulesStore(fixture.root), lambda: None, storage=fixture.canonical)
    settings = AgentSettingsStore(fixture.root)
    current = settings.load()
    if not current.enabled:
        settings.save(AgentSettingsRequest(expectedRevision=current.revision, enabled=True,
            selectedAgentModel="synthetic-model"), ("synthetic-model",))
    jobs = SimpleNamespace(enabled=True, store=fixture.jobs, publisher=fixture.coordinator, projects=service,
        artifacts=fixture.artifacts, fixed=SimpleNamespace(generation=lambda _project: None), settings=settings)
    jobs.publication = JobPublication(jobs)
    service.background_jobs = jobs
    service.ensure_loaded()
    return service


def test_stale_save_and_async_metadata_preserve_an_independent_committed_edit(tmp_path):
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    identifier = fixture.project
    operation = service.new_operation(identifier, "render")
    held_workspace = service.workspaces[identifier]
    held_owner = held_workspace.project
    fixture.edit("quote", "Changed while the renderer was waiting")
    operation.status = "completed"
    assert service.persist(identifier) == "durable"
    assert held_workspace is service.workspaces[identifier] and held_owner is held_workspace.project
    assert operation is next(item for item in held_owner.operations if item.id == operation.id)
    assert operation.status == "completed" and service.read(identifier) == fixture.current()
    assert fixture.current().project.document == held_owner.document
    assert fixture.current().document_revision == 2
    assert service.persist(identifier) == "durable"
    assert fixture.jobs.load(identifier).history.workspace_sha256 == digest_bytes(fixture.current())


def test_live_callback_object_survives_job_publication_adoption(tmp_path):
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    operation = service.new_operation(fixture.project, "rewrite_prose")
    job, proposal, _batch = fixture.accepted()
    result = service.background_jobs.publication.publish(fixture.project, job.id, proposal.payload_sha256)
    assert result.receipt.durable
    operation.status = "failed"
    operation.error_code = "SYNTHETIC_PROVIDER_FAILURE"
    assert service.persist(fixture.project) == "durable"
    committed = fixture.current()
    saved = next(item for item in committed.project.operations if item.id == operation.id)
    assert saved.status == "failed" and saved.error_code == "SYNTHETIC_PROVIDER_FAILURE"
    assert committed.document_revision == result.receipt.document_revision


def test_changed_stale_document_is_rejected_but_metadata_is_not_globally_stale(tmp_path):
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    before = fixture.current()
    fixture.edit("quote", "Concurrent committed edit")
    stale = service.workspaces[fixture.project]
    stale.project.document.revision += 1
    stale.document_revision += 1
    stale.project.document.regions[2].blocks[0].revision += 1
    assert service.persist(fixture.project) == "failed"
    assert service.save_errors[fixture.project] == "DEPENDENCY_CHANGED"
    assert fixture.current().document_revision == 2 and fixture.current() != before
    assert len(fixture.current().mutation_replay) == 1


def test_direct_storage_callback_cannot_bypass_activated_history(tmp_path):
    fixture = PublicationFixture(tmp_path)
    before = fixture.current()
    candidate = before.model_copy(deep=True)
    candidate.title = "Uncoordinated callback"
    with pytest.raises(ProjectStoreFailure, match="PROJECT_COORDINATOR_REQUIRED"):
        fixture.canonical.save(candidate, {}, {})
    assert fixture.current() == before
    assert fixture.jobs.load(fixture.project).history.workspace_sha256 == digest_bytes(before)


def test_metadata_collision_rejects_a_competing_change_to_the_same_operation(tmp_path):
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    operation = service.new_operation(fixture.project, "render")
    fixture.snapshot(lambda value: setattr(value.project.operations[0], "status", "cancelled"), "other-callback")
    operation.status = "completed"
    assert service.persist(fixture.project) == "failed"
    assert service.save_errors[fixture.project] == "DEPENDENCY_CHANGED"
    assert fixture.current().project.operations[0].status == "cancelled"


def test_snapshot_claim_failure_cannot_return_a_false_success(tmp_path):
    fixture = PublicationFixture(tmp_path)
    before = fixture.current()
    after = before.model_copy(deep=True)
    after.title = "Prepared metadata"
    def invalidate(name, project):
        if name == "before_commit_claim":
            with fixture.jobs.guard(project) as directory:
                state = fixture.jobs._read(project, directory)
                state.generations[-1].generation += 1
                fixture.jobs._write(directory, state, fixture.jobs._all())
    fixture.coordinator.observer = invalidate
    with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
        fixture.coordinator.snapshot(fixture.project, digest_bytes(before), after, "claim-lost")
    assert fixture.current() == before


def test_merge_keeps_distinct_source_revisions_and_rejects_reordering(tmp_path):
    fixture = PublicationFixture(tmp_path)
    before = fixture.current()
    after = before.model_copy(deep=True)
    after.project.operations = [RichOperation(id="first", kind="render", status="queued", actionId=None,
        dependencies=[], errorCode=None), RichOperation(id="second", kind="render", status="queued", actionId=None,
        dependencies=[], errorCode=None)]
    current = merge_snapshot(before, after, before)
    changed = current.model_copy(deep=True)
    changed.project.operations.reverse()
    latest = current.model_copy(deep=True)
    latest.project.operations[0].status = "running"
    with pytest.raises(BackgroundFailure, match="DEPENDENCY_CHANGED"):
        merge_snapshot(current, changed, latest)
