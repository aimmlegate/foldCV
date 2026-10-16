"""Self-review regressions at real durable publication and service boundaries."""

import asyncio
from types import SimpleNamespace

import pytest

from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_store import BackgroundFailure, records
from packages.resume_core.models.agent import AgentEntityDependency, AgentQuery
from packages.resume_core.models.rich_document import NarrativeCitation
from tests.recovery.test_background_conflicts import apply, record_step
from tests.recovery.test_background_inverse import block, mutation, put
from tests.recovery.test_background_publication_crashes import attach
from tests.support.background_publication import PublicationFixture


def test_recovery_does_not_recreate_a_missing_history_activation_marker(tmp_path):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    def fail(name, _project):
        if name == "workspace_durable":
            raise OSError("Synthetic crash")
    fixture.coordinator.observer = fail
    with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
        fixture.publish(job, proposal)
    activation = fixture.jobs.projects / fixture.project / "history-activation.json"
    activation.unlink()
    restarted = fixture.fresh()
    with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
        restarted.coordinator.recover(fixture.project)
    assert not activation.exists()
    assert restarted.jobs.read(fixture.project, job.id).receipt is None
    assert len(restarted.current().mutation_replay) == 1


def test_inverse_capacity_is_reserved_before_canonical_claim(tmp_path):
    fixture = PublicationFixture(tmp_path)
    for index in range(LIMITS.inverse_project_records):
        job, proposal, _batch = fixture.accepted("saved-" + str(index),
            steps=[put(fixture.current(), "narrative", text="Saved input " + str(index))])
        assert fixture.publish(job, proposal).receipt.durable
    job, proposal, _batch = fixture.accepted("over-inverse-capacity",
        steps=[put(fixture.current(), "narrative", text="Another actual edit")])
    before = fixture.current()
    with pytest.raises(BackgroundFailure, match="JOB_STORAGE_FULL"):
        fixture.publish(job, proposal)
    state = fixture.jobs.load(fixture.project)
    assert len(state.inverses) == LIMITS.inverse_project_records
    assert len(state.intents) == LIMITS.inverse_project_records
    assert state.jobs[-1].publication == "waiting_for_sync" and fixture.current() == before


def test_receipt_metadata_capacity_is_reserved_before_canonical_claim(tmp_path):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    with fixture.jobs.guard(fixture.project) as directory:
        state = fixture.jobs._read(fixture.project, directory)
        index = 0
        while records(state) < LIMITS.metadata_project_records - 1:
            count = min(80, (LIMITS.metadata_project_records - 1 - records(state)) // 2)
            assert count > 0
            selectors = [AgentEntityDependency(kind="entity", stamp={"kind": "block", "id": "absent-" + str(index + offset),
                "revision": 1, "fingerprint": None}) for offset in range(count)]
            fixture.history.register(state, fixture.initial, selectors, write=True)
            index += count
        assert records(state) == LIMITS.metadata_project_records - 1
        fixture.jobs._write(directory, state, fixture.jobs._all())
    before = fixture.current()
    with pytest.raises(BackgroundFailure, match="JOB_STORAGE_FULL"):
        fixture.publish(job, proposal)
    assert fixture.current() == before and not fixture.jobs.load(fixture.project).intents


def test_inverse_reads_fence_a_new_user_reference_to_a_changed_fact(tmp_path):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted(queries=[AgentQuery(kind="facts", ids=["language-1"])],
        steps=[record_step(fixture.current(), "language-1")])
    assert fixture.publish(job, proposal).receipt.durable
    inverse = fixture.jobs.load(fixture.project).inverses[0]
    with fixture.jobs.guard(fixture.project) as directory:
        state = fixture.jobs._read(fixture.project, directory)
        assert fixture.history.validate(state, directory, fixture.canonical._read_committed_unlocked(fixture.project)[0], inverse.guards)
    value = put(fixture.current(), "quote")
    value["block"].provenance.append(NarrativeCitation(kind="citation", id="new-user-reference", recordId="language-1",
        fieldKeys=["name"], evidence=[]))
    apply(fixture, [value], "new-reference")
    with fixture.jobs.guard(fixture.project) as directory:
        state = fixture.jobs._read(fixture.project, directory)
        current = fixture.canonical._read_committed_unlocked(fixture.project)[0]
        with pytest.raises(BackgroundFailure, match="DEPENDENCY_CHANGED"):
            fixture.history.validate(state, directory, current, inverse.guards)


def test_duplicate_barrier_ack_does_not_extend_its_continuous_deadline(tmp_path):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    barrier = attach(fixture)
    state = fixture.jobs.load(fixture.project)
    fixture.coordinator.authority.clock.advance(LIMITS.local_barrier_ms / 1000)
    fixture.coordinator.authority.acknowledged(state.writer, barrier)
    assert fixture.publish(job, proposal).publication == "waiting_for_sync"


def test_native_saved_envelope_uses_the_retained_real_candidate_after_replay_pruning(tmp_path):
    from packages.resume_core.rules import RulesStore
    from resume_api.jobs.publication import JobPublication
    from resume_api.rich_projects import RichProjectService
    fixture = PublicationFixture(tmp_path)
    job, proposal, batch = fixture.accepted()
    saved = fixture.publish(job, proposal)
    fixture.edit("quote", "Later independent input")
    fixture.snapshot(lambda value: value.mutation_replay.clear(), "prune-replay")
    projects = RichProjectService(tmp_path / "operations", RulesStore(tmp_path), lambda: None, storage=fixture.canonical)
    adapter = JobPublication(SimpleNamespace(store=fixture.jobs, artifacts=fixture.artifacts,
        publisher=fixture.coordinator, projects=projects))
    result = adapter.native_result(fixture.project, job.id)
    assert result.result.receipt.client_mutation_id == saved.receipt.client_mutation_id
    assert result.result.receipt.request_sha256 == saved.receipt.request_sha256
    assert result.result.project.workspace.project_revision == saved.receipt.project_revision
    assert result.result.project.workspace.mutation_replay[0].request_sha256 == saved.receipt.request_sha256
    assert not fixture.current().mutation_replay
    assert block(fixture.current(), "quote").content[0].text == "Later independent input"
    assert fixture.artifacts.bound(fixture.project, job.id).legacy().run.saved_batch_id == batch.id
    assert fixture.artifacts.record(fixture.project, job.id)[1].batches[0].receipt is None


@pytest.mark.asyncio
async def test_manual_service_route_replays_and_stale_cache_save_cannot_overwrite_it(tmp_path):
    from tests.recovery.test_background_agent import environment, hold_writer
    from packages.resume_core.agent_store import digest
    from resume_api.gui_projects import ProjectFailure
    from tests.support.background import save_input
    service, factory, workspace, _payload, _connection, _old = await environment(tmp_path)
    request = mutation(workspace, [put(workspace, "narrative", text="Actual manual input")], "manual-route")
    try:
        with pytest.raises(ProjectFailure, match="WRITER_UNKNOWN"):
            service.projects.mutate(workspace.project_id, request)
        proof = hold_writer(service, workspace)
        saved = save_input(service, request, proof)
        assert saved.durability == "durable" and saved.workspace.project_revision == 2
        service.projects.workspaces[workspace.project_id] = workspace.model_copy(deep=True)
        assert service.projects.persist(workspace.project_id) == "failed"
        assert service.projects.storage.read_committed(workspace.project_id)[0] == saved.workspace
        replay = save_input(service, request, proof)
        assert replay.workspace == saved.workspace and replay.durability == "durable"
        assert not factory.calls
        assert service.projects.saved_hashes[workspace.project_id] == digest(saved.workspace)
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_lost_history_fences_only_its_project_and_another_project_still_runs(tmp_path):
    from packages.resume_core.agent_store import AgentStore
    from tests.recovery.test_background_agent import environment
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    second = workspace.model_copy(deep=True)
    second.project_id = second.project.project_id = "second-project"
    service.projects.storage.save(second, {}, {})
    service.projects.workspaces[second.project_id] = second
    service.projects.saved_revisions[second.project_id] = (1, 1)
    from packages.resume_core.agent_store import digest
    service.projects.saved_hashes[second.project_id] = digest(second)
    conversation = AgentStore(service.store.root).create_conversation(second.project_id)
    service.history.open(workspace.project_id)
    (service.store.projects / workspace.project_id / "history-activation.json").unlink()
    with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
        service.history.open(workspace.project_id)
    second_state = service.project(second.project_id)
    following = payload.model_copy(deep=True)
    following.lineage, following.request_epoch = second_state.lineage, second_state.request_epoch
    following.request.client_request_id, following.request.conversation_id = "other-project", conversation.id
    try:
        blocked, _created = await service.submit(workspace.project_id, payload)
        allowed, _created = await service.submit(second.project_id, following)
        actor = await factory.actor(allowed)
        await asyncio.wait_for(actor.closed.wait(), 10)
        await asyncio.wait_for(service.supervisor.controls[allowed.id].task, 10)
        assert service.store.read(second.project_id, allowed.id).execution == "completed"
        assert service.store.read(workspace.project_id, blocked.id).execution == "queued"
        assert factory.calls == [(allowed.id, "agent")] and service.supervisor.fenced is None
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()
