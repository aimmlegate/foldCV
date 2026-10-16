"""Proposal durability cuts, coherent paged reads and pre-publication revocation."""

import asyncio
from types import SimpleNamespace

import pytest

from packages.resume_core.background_store import BackgroundFailure, expiration
from packages.resume_core.background_supervisor import ExecutionOutcome
from packages.resume_core.models.agent import AgentApplyRequest, AgentQuery, AgentReadSnapshot
from packages.resume_core.models.background import WriterSessionV1
from spikes.background.fixtures import TIME
from tests.recovery.test_agent_edits import command, replace
from tests.recovery.test_background_agent import environment
from tests.recovery.test_background_inverse import block, mutation, put

CUTS = [(f"NB-D01:v{number:02d}", phase, side, writer)
    for start, phase in [(1, "payload_stored"), (5, "binding_stored")]
    for number, side, writer in [(start, "before", "clean_detached"), (start + 1, "before", "attached_uncertain"),
        (start + 2, "after", "clean_detached"), (start + 3, "after", "attached_uncertain")]]


@pytest.mark.asyncio
@pytest.mark.parametrize("variant,phase,side,writer", CUTS, ids=[item[0] for item in CUTS])
async def test_proposal_handoff_cut_does_not_create_canonical_authority(tmp_path, variant, phase, side, writer):
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    target, reached, replies = "before_" + phase if side == "before" else phase, [], []
    with service.store.guard(workspace.project_id) as directory:
        state = service.store._read(workspace.project_id, directory)
        state.writer = WriterSessionV1(schemaVersion=1, projectId=workspace.project_id, lineage=state.lineage,
            epoch=1, sessionId="session", incarnation="instance", resumeCredentialSha256="a" * 64,
            leaseExpiresAt=expiration(TIME, 15), status="clean_detached" if writer == "clean_detached" else "attached",
            acknowledgedRevision=1, acknowledgedCursor=0, touchGeneration=0, barrierGeneration=0, draftId=None)
        service.store._write(directory, state, service.store._all())
    async def observe(name, job_id):
        if name == target:
            reached.append(job_id)
            raise OSError("Synthetic handoff interruption at " + target)
    service.supervisor.observer = observe
    async def execute(control, _actor):
        session = service.tools.session(control)
        try:
            read = await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"]))
            prepared = await session.call("prepare_edit_batch", command(replace(
                AgentReadSnapshot.model_validate(read["snapshot"]), "narrative", 0, 6, "Pending")))
            replies.append(await session.call("apply_edit_batch", AgentApplyRequest(batchId=prepared["batchId"])))
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = execute
    try:
        job, _created = await service.submit(workspace.project_id, payload)
        await factory.actor(job)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        assert reached == [job.id] and replies[0]["error"]["code"] == "AGENT_PROTOCOL", variant
        from packages.resume_core.background_store import JobStore
        fresh = JobStore(service.store.root)
        fresh.recover(workspace.project_id)
        state = fresh.load(workspace.project_id)
        bound = phase == "binding_stored" and side == "after"
        assert bool(state.proposals) == bound
        assert state.jobs[0].publication == ("waiting_for_sync" if bound else "none")
        assert not state.intents and not state.inverses and service.supervisor.active is None
        assert not service.projects.storage.read_committed(workspace.project_id)[0].mutation_replay
        artifact = service.artifacts.record(workspace.project_id, job.id)[1]
        assert artifact.batches[0].batch is not None and len(factory.calls) == 1
        files = list((service.store.projects / workspace.project_id / "proposal-intents").glob("*.json"))
        assert bool(files) == (phase == "binding_stored" or side == "after")
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-P06:v03", "NB-P06:v04"])
async def test_page_membership_and_partial_rereads_preserve_all_old_dependencies(tmp_path, variant):
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    if variant == "NB-P06:v03":
        current, checksum = service.projects.storage.read_committed(workspace.project_id)
        block(current, "narrative").content[0].text = "Q" * 60000
        service.publisher.snapshot(workspace.project_id, checksum, current, "long-input")
        payload.request.project_revision = current.project_revision
    checked = []
    async def execute(control, _actor):
        session = service.tools.session(control)
        try:
            if variant == "NB-P06:v04":
                session.book.read(AgentQuery(kind="document", ids=["quote"]))
            first = session.book.read(AgentQuery(kind="document", ids=["narrative"]))
            current = service.projects.storage.read_committed(workspace.project_id)[0]
            if variant == "NB-P06:v03":
                assert first.snapshot.truncated and first.snapshot.next_cursor
                value = block(current, "quote").model_copy(update={"id": "new-child", "children": []})
                service.projects.mutate(workspace.project_id, mutation(current, [{"kind": "put_block", "parentId": "narrative",
                    "afterId": None, "beforeRevision": None, "block": value}], "membership-between-pages"))
                result = first
                pages = 1
                while result.snapshot.truncated:
                    result = session.book.read(AgentQuery(kind="document", ids=["narrative"], cursor=result.snapshot.next_cursor))
                    pages += 1
                assert pages > 1
            else:
                service.projects.mutate(workspace.project_id, mutation(current, [put(current, "quote", text="Old query is stale")], "stale-other-query"))
                first = session.book.read(AgentQuery(kind="document", ids=["narrative"]))
            denied = await session.call("prepare_edit_batch", command(replace(first.snapshot, "narrative", 0, 1, "Changed")))
            assert denied["error"]["code"] == "AGENT_STALE_READ", denied
            checked.append(control.job.id)
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = execute
    try:
        job, _created = await service.submit(workspace.project_id, payload)
        await factory.actor(job)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        assert checked == [job.id] and not service.store.load(workspace.project_id).proposals
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-P10:v01", "NB-P10:v02"])
async def test_queued_and_executing_revocation_never_reaches_publication(tmp_path, variant):
    for cause in ("stop", "account", "delete"):
        service, factory, workspace, payload, _connection, _old = await environment(tmp_path / cause)
        queued, waiting = variant == "NB-P10:v01", asyncio.Event()
        original = service.admission.reserve
        async def reserve(cancelled):
            waiting.set()
            return await original(cancelled)
        service.admission.reserve = reserve
        external = service.admission.acquire(blocking=False) if queued else False
        factory.hold_results.add(payload.request.client_request_id)
        try:
            job, _created = await service.submit(workspace.project_id, payload)
            if queued:
                await asyncio.wait_for(waiting.wait(), 10)
                assert service.store.read(workspace.project_id, job.id).execution == "queued"
            else:
                actor = await factory.actor(job)
                await asyncio.wait_for(actor.started.wait(), 10)
            if cause == "stop":
                await service.supervisor.cancel(workspace.project_id, job.id)
            elif cause == "account":
                service.supervisor.confirmed_account_change(2)
            else:
                result = await service.projects.delete_project(workspace.project_id)
                assert result.status == "deleted"
            await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
            if cause == "delete":
                with service.store.guard(workspace.project_id, deleted=True) as directory:
                    state = service.store._read(workspace.project_id, directory)
                    assert state.tombstoned and not state.jobs and not state.proposals and not state.intents
                    known = service.supervisor.controls[job.id].job
                assert service.supervisor.fenced is None
                assert not (service.projects.storage.projects / workspace.project_id).exists()
            else:
                known = service.store.read(workspace.project_id, job.id)
            assert known.receipt is None and known.publication == "cancelled"
            assert len(factory.calls) == (0 if queued else 1)
            assert service.supervisor.active is None
        finally:
            if external:
                service.admission.release()
            await service.shutdown()
            factory.verify(); service.supervisor.clock.verify()
