"""The real tool adapter retains one proposal and reads only committed input."""

import asyncio

import pytest

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_supervisor import ExecutionOutcome
from packages.resume_core.models.agent import AgentApplyRequest, AgentQuery, AgentReadSnapshot
from packages.resume_core.models.background import WriterSessionV1
from tests.recovery.test_agent_edits import command, replace
from tests.recovery.test_background_agent import environment
from tests.recovery.test_background_inverse import mutation, put


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-J06:v01", "NB-J06:v02", "NB-J06:v03", "NB-J05:v04"])
async def test_one_turn_cannot_replace_or_duplicate_its_accepted_payload(tmp_path, variant):
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    sessions, results = [], []
    async def execute(control, _actor):
        session = service.tools.session(control)
        sessions.append(session)
        try:
            read = await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"]))
            request = command(replace(AgentReadSnapshot.model_validate(read["snapshot"]), "narrative", 0, 6, "PROPOSED"))
            prepared = await session.call("prepare_edit_batch", request)
            assert prepared["disposition"] == "prepared", prepared
            applied = await session.call("apply_edit_batch", AgentApplyRequest(batchId=prepared["batchId"]))
            assert applied["disposition"] == "waiting_for_sync", applied
            if variant == "NB-J06:v01":
                assert await session.call("apply_edit_batch", AgentApplyRequest(batchId=prepared["batchId"])) == applied
            elif variant == "NB-J06:v02":
                candidate = service.store.load(workspace.project_id).proposals[0].model_copy(update={"payload_sha256": "b" * 64})
                with pytest.raises(BackgroundFailure, match="JOB_SCOPE_INVALID"):
                    await service.proposals_for(workspace.project_id).accept(control, candidate)
            elif variant == "NB-J06:v03":
                another = request.model_copy(update={"key": "another-batch"})
                denied = await session.call("prepare_edit_batch", another)
                assert denied["error"]["code"] in {"AGENT_BUSY", "AGENT_EDIT_LIMIT"}
            results.append(applied)
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = execute
    try:
        job, _created = await service.submit(workspace.project_id, payload)
        await factory.actor(job)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        if variant == "NB-J05:v04":
            late = await sessions[0].call("apply_edit_batch", AgentApplyRequest(batchId="old-batch"))
            assert late["error"]["code"] == "AGENT_CANCELLED"
        state = service.store.load(workspace.project_id)
        assert len(state.proposals) == len(results) == 1
        assert len(service.artifacts.record(workspace.project_id, job.id)[1].batches) == 1
        assert not service.projects.storage.read_committed(workspace.project_id)[0].mutation_replay
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("restart", [False, True], ids=["after-runtime-exit", "startup-recovery"])
async def test_compiled_proposal_saves_through_the_service_after_owned_runtime_cleanup(tmp_path, restart):
    from packages.resume_core.background_store import expiration
    from packages.resume_core.models.agent import wire_bytes
    service, factory, workspace, payload, connection, _old = await environment(tmp_path)
    results = []
    async def execute(control, _actor):
        session = service.tools.session(control)
        try:
            read = await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"]))
            prepared = await session.call("prepare_edit_batch", command(replace(
                AgentReadSnapshot.model_validate(read["snapshot"]), "narrative", 0, 6, "Published")))
            results.append(await session.call("apply_edit_batch", AgentApplyRequest(batchId=prepared["batchId"])))
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = execute
    replacement, next_factory = None, None
    try:
        job, _created = await service.submit(workspace.project_id, payload)
        actor = await factory.actor(job)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        assert actor.verified_dead() and not service.admission.locked() and service.supervisor.active is None
        assert results[0]["disposition"] == "waiting_for_sync"
        accepted = service.store.load(workspace.project_id).proposals[0]
        original = service.artifacts.payload_for(workspace.project_id, accepted.payload)
        pending = service.publication.publish(workspace.project_id, job.id, accepted.payload_sha256)
        assert pending.publication == "waiting_for_sync" and pending.publication_error.code == "WRITER_UNKNOWN"
        current = service.projects.storage.read_committed(workspace.project_id)[0]
        service.projects.mutate(workspace.project_id,
            mutation(current, [put(current, "quote", text="Independent user input")], "independent-before-publication"))
        with service.store.guard(workspace.project_id) as directory:
            state = service.store._read(workspace.project_id, directory)
            state.writer = WriterSessionV1(schemaVersion=1, projectId=workspace.project_id, lineage=state.lineage,
                epoch=1, sessionId="session", incarnation="instance", resumeCredentialSha256="a" * 64,
                leaseExpiresAt=expiration(service.store.clock(), 15), status="clean_detached", acknowledgedRevision=2,
                acknowledgedCursor=1, touchGeneration=1, barrierGeneration=0, draftId=None)
            service.store._write(directory, state, service.store._all())
        owner = service
        if restart:
            from packages.resume_core.background_clock import ControlledDeadlines
            from packages.resume_core.rich_project_store import RichProjectStore
            from packages.resume_core.rules import RulesStore
            from resume_api.inference_admission import InferenceAdmission
            from resume_api.jobs.service import JobService
            from resume_api.rich_projects import RichProjectService
            from tests.support.background import PipeExecutions
            reached = []
            def interrupt(name, _project):
                if name == "workspace_durable":
                    reached.append(name)
                    raise OSError("Synthetic crash before receipt")
            service.publisher.observer = interrupt
            with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
                service.publication.publish(workspace.project_id, job.id, accepted.payload_sha256)
            assert reached == ["workspace_durable"]
            await service.shutdown()
            storage = RichProjectStore(service.store.root)
            projects = RichProjectService(tmp_path / "restart-operations", RulesStore(service.store.root), lambda: None,
                storage=storage)
            clock = ControlledDeadlines()
            next_factory = PipeExecutions(tmp_path / "restart-pipes", clock)
            replacement = JobService(projects, None, lambda: connection["value"], enabled=True,
                factory=next_factory, clock=clock, admission=InferenceAdmission())
            await replacement.start()
            owner = replacement
            assert not next_factory.calls and replacement.store.read(workspace.project_id, job.id).receipt.durable
        saved = owner.publication.publish(workspace.project_id, job.id, accepted.payload_sha256)
        result = owner.publication.native_result(workspace.project_id, job.id)
        assert saved.receipt.durable and result.durable and result.result.receipt.request_sha256 == saved.receipt.request_sha256
        assert len(wire_bytes(result)) <= 64 * 1024
        persisted = owner.projects.storage.read_committed(workspace.project_id)[0]
        assert persisted == owner.projects.read(workspace.project_id)
        assert len(persisted.mutation_replay) == 2
        from tests.recovery.test_background_inverse import block
        assert block(persisted, "quote").content[0].text == "Independent user input"
        assert block(persisted, "narrative").content[0].text.startswith("Published")
        assert owner.artifacts.payload_for(workspace.project_id, accepted.payload) == original
        assert owner.publication.publish(workspace.project_id, job.id, accepted.payload_sha256).receipt == saved.receipt
        assert factory.calls == [(job.id, "agent")]
    finally:
        if replacement is not None:
            await replacement.shutdown()
            next_factory.verify(); replacement.supervisor.clock.verify()
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-J06:v04", "NB-J05:v03"])
async def test_a_new_turn_reads_canonical_and_supersession_is_durable_before_dispatch(tmp_path, variant):
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    accepted, checked = [], []
    async def first(control, _actor):
        session = service.tools.session(control)
        try:
            read = await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"]))
            prepared = await session.call("prepare_edit_batch", command(replace(
                AgentReadSnapshot.model_validate(read["snapshot"]), "narrative", 0, 6, "UNPUBLISHED")))
            accepted.append(await session.call("apply_edit_batch", AgentApplyRequest(batchId=prepared["batchId"])))
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    async def second(control, _actor):
        session = service.tools.session(control)
        try:
            read = await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"]))
            assert "UNPUBLISHED" not in read["content"] and "Styled" in read["content"]
            if variant == "NB-J05:v03":
                state = service.store.load(workspace.project_id)
                assert state.proposals[0].authority == "revoked" and state.proposals[0].revocation == "superseded"
            checked.append(control.job.id)
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id], factory.callbacks["next-turn"] = first, second
    try:
        job, _created = await service.submit(workspace.project_id, payload)
        await factory.actor(job)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        assert accepted[0]["disposition"] == "waiting_for_sync"
        if variant == "NB-J05:v03":
            service.store.discard(workspace.project_id, job.id, superseded=True)
        following = payload.model_copy(deep=True)
        following.request.client_request_id = "next-turn"
        next_job, _created = await service.submit(workspace.project_id, following)
        await factory.actor(next_job)
        await asyncio.wait_for(service.supervisor.controls[next_job.id].task, 10)
        assert checked == [next_job.id] and len(factory.calls) == 2
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()
