"""Keep resource reserves, queue order and idle rotation independent."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from tests.recovery.test_background_parallel import other_project, finish
from tests.recovery.test_background_queue import captured
from tests.recovery.test_background_supervisor import environment


@pytest.mark.asyncio
async def test_capacity_three_keeps_fifo_and_progress_behind_an_ineligible_project_head(tmp_path):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    supervisor.parallel = True
    supervisor.pause("RATE_LIMITED")
    other = other_project(tmp_path, store, state)
    third = other_project(tmp_path, store, state, "parallel-third")
    blocked = set()
    supervisor.eligible = lambda job: job.id not in blocked
    factory.hold_results.update({"head", "following", "B", "C", "rewrite"})
    try:
        head, _ = await supervisor.submit(captured(state, "head"))
        following, _ = await supervisor.submit(captured(state, "following"))
        blocked.add(head.id)
        background = [(await supervisor.submit(captured(context, key)))[0] for context, key in ((other, "B"), (third, "C"))]
        rewrite, _ = await supervisor.submit(captured(state, "rewrite", "rewrite"))
        supervisor.resume(1)
        active = [*background, rewrite]
        actors = [await factory.actor(job) for job in active]
        await asyncio.wait_for(asyncio.gather(*(actor.started.wait() for actor in actors)), 10)
        assert len(supervisor.active_controls) == 3
        assert not store.read(state.project_id, head.id).attempts and not store.read(state.project_id, following.id).attempts
        assert [job for job, _stage in factory.calls] == [job.id for job in active]
        blocked.clear()
        actors[0].result.set()
        await asyncio.wait_for(supervisor.controls[background[0].id].task, 10)
        first = await factory.actor(head)
        await asyncio.wait_for(first.started.wait(), 10)
        assert not store.read(state.project_id, following.id).attempts
        first.result.set()
        await asyncio.wait_for(supervisor.controls[head.id].task, 10)
        last = await factory.actor(following)
        await asyncio.wait_for(last.started.wait(), 10)
        assert [job for job, _stage in factory.calls][-2:] == [head.id, following.id]
    finally:
        await finish(supervisor, factory, clock)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-Q09:v02", "NB-Q09:v03"])
async def test_two_render_positions_and_a_queued_export_do_not_block_models_or_save(tmp_path, variant):
    from spikes.background.writer_bridge import Bridge
    from tests.recovery.test_background_agent import hold_writer
    from tests.recovery.test_background_exports import HeldRenderer
    from tests.recovery.test_background_inverse import mutation, put
    from tests.recovery.test_background_release import submit
    from tests.support.background import save_input
    bridge = Bridge(tmp_path, parallel=True)
    ready = asyncio.Queue()
    bridge.send = lambda row: ready.put_nowait(row["job"]) if row.get("token") == "held-models" else None
    await bridge.start()
    renderer, renders = HeldRenderer(), []
    attempted, queued = 0, asyncio.Event()
    try:
        service = bridge.service
        other = await bridge.handle({"kind": "clone"})
        third = await bridge.handle({"kind": "clone"})
        peer = SimpleNamespace(service=service, project=other["project"], conversation=SimpleNamespace(id=other["conversation"]),
            handle=bridge.handle)
        await bridge.handle(dict(kind="hold", token="held-models", name="scripted_model_ready", family="job"))
        first, second = await submit(bridge, "model-A"), await submit(peer, "model-B")
        assert {await asyncio.wait_for(ready.get(), 10) for _ in range(2)} == {first.id, second.id}
        slot = service.projects.worker_slot
        @asynccontextmanager
        async def observed_slot(cancel):
            nonlocal attempted
            attempted += 1
            if attempted == 3:
                queued.set()
            async with slot(cancel):
                yield
        service.projects.worker_slot = observed_slot
        service.projects.renderer = renderer
        for project in (bridge.project, other["project"]):
            renders.append(asyncio.create_task(bridge.client.post(f"/v1/rich/projects/{project}/export", json={})))
        await asyncio.wait_for(renderer.both_entered.wait(), 10)
        renders.append(asyncio.create_task(bridge.client.post(f"/v1/rich/projects/{third['project']}/export", json={})))
        await asyncio.wait_for(queued.wait(), 10)
        assert renderer.calls == 2 and not renders[2].done()
        assert len(service.parallel_owner.permits) == 2 and service.admission.locked()
        workspace = service.projects.storage.read_committed(third["project"])[0]
        proof = hold_writer(service, workspace)
        command = mutation(workspace, [put(workspace, "quote", text="Saved while two models and two renders wait")], "parallel-render-save")
        saved = await asyncio.wait_for(asyncio.to_thread(save_input, service, command, proof), 10)
        assert saved.workspace.project_revision == workspace.project_revision + 1
        status = await bridge.client.get(f"/v1/rich/projects/{bridge.project}/jobs")
        assert status.status_code == 200 and renderer.calls == 2
        assert service.store.read(bridge.project, first.id).execution == "running"
        assert service.store.read(other["project"], second.id).execution == "running"
        renderer.release.set()
        replies = await asyncio.wait_for(asyncio.gather(*renders), 10)
        assert all(response.status_code == 200 for response in replies) and renderer.calls == 3
        assert not service.projects.tasks and not service.projects.files
        await bridge.handle(dict(kind="release", token="held-models"))
        await asyncio.wait_for(asyncio.gather(service.supervisor.controls[first.id].task,
            service.supervisor.controls[second.id].task), 10)
    finally:
        renderer.release.set()
        if renders:
            await asyncio.gather(*renders, return_exceptions=True)
        await bridge.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["next-turn", "two-stage", "cancel-waiter"])
async def test_context_bound_drains_owned_turns_before_rotation_without_releasing_the_profile(tmp_path, mode):
    from resume_api.inference_admission import InferenceAdmission, AdmissionCancelled
    from resume_api.jobs.parallel import ParallelOwner
    from resume_api.jobs.process_ownership import guard_server
    from tests.recovery.test_background_appserver import shared_peer, shared_input, complete_shared
    driver = guard_server(shared_peer(tmp_path / "transport"))
    service = SimpleNamespace(admission=InferenceAdmission(), supervisor=SimpleNamespace(active_controls={}))
    owner = ParallelOwner(service, lambda: driver, native=False)
    tasks, permits = [], []
    def control(count=1):
        return SimpleNamespace(cancelled=asyncio.Event(), job=SimpleNamespace(submission=SimpleNamespace(models=[None] * count)))
    async def turn(key):
        ready = asyncio.Event()
        task = asyncio.create_task(driver.run(shared_input(key, started=ready.set)))
        tasks.append(task)
        await asyncio.wait_for(ready.wait(), 10)
        return task
    try:
        for index in range(7):
            task = await turn("warm_" + str(index))
            complete_shared(driver, "warm_" + str(index), "Warm context finished")
            assert (await asyncio.wait_for(task, 10))["cleanupVerified"]
        first = await owner.reserve(control())
        permits.append(first)
        active = await turn("active")
        pid = driver.pipe.process.pid
        reached = asyncio.Event()
        wait = owner.changed.wait
        async def observed_wait():
            reached.set()
            await wait()
        owner.changed.wait = observed_wait
        waiting_control = control(2 if mode == "two-stage" else 1)
        waiting = asyncio.create_task(owner.reserve(waiting_control))
        tasks.append(waiting)
        await asyncio.wait_for(reached.wait(), 10)
        assert not waiting.done() and driver.generation == 1 and driver.pipe.process.pid == pid
        assert driver.test_owner_events == [True] and service.admission.locked()
        if mode == "cancel-waiter":
            waiting_control.cancelled.set()
            with pytest.raises(AdmissionCancelled):
                await asyncio.wait_for(waiting, 10)
        complete_shared(driver, "active", "Active context finished")
        assert (await asyncio.wait_for(active, 10))["cleanupVerified"]
        first.release()
        if mode != "cancel-waiter":
            following = await asyncio.wait_for(waiting, 10)
            permits.append(following)
            assert driver.generation == 2 and driver.pipe.process.pid != pid and driver.test_owner_events == [True]
            for index in range(2 if mode == "two-stage" else 1):
                task = await turn("following_" + str(index))
                complete_shared(driver, "following_" + str(index), "Following context finished")
                assert (await asyncio.wait_for(task, 10))["cleanupVerified"]
            following.release()
        await owner.idle()
        assert not service.admission.locked() and owner.login_allowed() and driver.test_owner_events == [True, False]
        assert all(row["ownedGroupCleanupVerified"] and row["operationRemoved"] for row in driver.shutdowns)
    finally:
        await driver.close()
        await asyncio.gather(*tasks, return_exceptions=True)
        for permit in permits:
            if permit.active:
                permit.release()
        await owner.idle()
