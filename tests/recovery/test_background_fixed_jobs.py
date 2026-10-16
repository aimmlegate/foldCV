"""Real fixed services run under durable jobs with no native inference."""

import asyncio
from pathlib import Path
import threading
from dataclasses import replace

import pytest

from packages.resume_core.models.background import JobFixedRequestV1
from packages.resume_core.models.rich_mutations import ActionCapture
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_history import digest_bytes
from packages.resume_core.models.background import WriterAdvanceV1
from packages.resume_core.models.rich_document import NarrativeCitation
from resume_api.providers.content import ContentFailure
from resume_api.gui_projects import ProjectFailure
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.test_background_agent import environment, hold_writer
from tests.recovery.test_rich_synchronization import selection, completion, capture
from tests.recovery.test_background_inverse import mutation, put
from tests.support.background import save_input


class HeldProvider(CreationProvider):
    def __init__(self):
        super().__init__()
        self.loop, self.entered, self.releases = asyncio.get_running_loop(), asyncio.Queue(), []
        self.replace_bound = False

    def generate(self, request, files, cancel):
        release = threading.Event()
        self.releases.append(release)
        self.loop.call_soon_threadsafe(self.entered.put_nowait, (request, release))
        if not release.wait(10):
            raise AssertionError("synthetic content gate was not released")
        if cancel.is_set():
            raise ContentFailure("CANCELLED")
        response = super().generate(request, files, cancel)
        if self.replace_bound:
            for replacement in response.value.replacements:
                for block in replacement.blocks:
                    for span in block.content if isinstance(block.content, list) else []:
                        if span.type == "fact_field":
                            span.text = "Rewritten"
        return response

    def release_all(self):
        for release in self.releases:
            release.set()


def rewrite_command(workspace, block="narrative", action="rewrite-action"):
    selected = selection(workspace, id=block)
    selected.capture.action_id = action
    return {"kind": "rewrite", "request": {"selection": selected.model_dump(by_alias=True), "instruction": "Clarify"}}


def completion_command(action="auto-action", block="title", interpret=False):
    return {"kind": "completion", "request": completion(capture=capture(action), blockIds=[block], interpret=interpret).model_dump(by_alias=True)}


def save_and_detach(service, project, command):
    proof = hold_writer(service, service.projects.storage.read_committed(project)[0])
    response = save_input(service, command, proof)
    view = service.writers.read_snapshot(project, proof)
    service.writers.detach(project, WriterAdvanceV1(schemaVersion=1, proof=proof,
        canonicalRevision=response.workspace.project_revision, canonicalSha256=digest_bytes(response.workspace),
        actionCursor=view.writer.acknowledged_cursor, touches=[]))
    return response.workspace


def linked_fixture(service, workspace):
    updated = service.projects.workspaces[workspace.project_id]
    block = next(b for b in updated.project.document.blocks() if b.id == "narrative")
    block.provenance = [NarrativeCitation(kind="citation", id="fixed-citation", recordId="candidate-1", fieldKeys=["title"], evidence=[])]
    assert service.projects.persist(workspace.project_id) == "durable"
    return service.projects.storage.read_committed(workspace.project_id)[0]


async def source_project(service, monkeypatch):
    from packages.resume_core.extraction.parser import extract
    async def inline_extract(data, name, pasted, _files):
        return extract(data, name, pasted)
    monkeypatch.setattr("resume_api.rich_projects.run_extract", inline_extract)
    return await service.projects.select(Path("tests/fixtures/recovery/E1.txt").read_bytes(), "pasted.txt", True)


async def blocked_agent(service, factory, payload, project="project-1"):
    factory.hold_results.add(payload.request.client_request_id)
    job, _created = await service.submit(project, payload)
    actor = await factory.actor(job)
    await asyncio.wait_for(actor.started.wait(), 10)
    return job, actor


def clone_project(service, workspace, identifier="zz-fixed-project"):
    value = workspace.model_copy(deep=True)
    value.project_id, value.project.project_id = identifier, identifier
    service.projects.storage.save(value, {}, {})
    _saved, checksum = service.projects.storage.read_committed(identifier)
    service.publication.adopt(identifier, value, checksum, preserve=False)
    return value


def fixed_request(service, project, key, command):
    state = service.project(project)
    return JobFixedRequestV1(schemaVersion=1, lineage=state.lineage, requestEpoch=state.request_epoch,
        clientRequestId=key, command=command)


async def settled(service, project, identifier, *, publication=None):
    changed = asyncio.Event()
    service.supervisor.listeners.add(changed)
    try:
        while True:
            changed.clear()
            job = service.store.read(project, identifier)
            if job.execution in {"failed", "cancelled", "interrupted"} and publication is not None:
                raise AssertionError((job.execution, job.publication, job.error, job.attempts))
            if job.execution in {"completed", "failed", "cancelled", "interrupted"} and (publication is None or job.publication == publication):
                if identifier in service.supervisor.controls:
                    await asyncio.wait_for(service.supervisor.controls[identifier].task, 10)
                if publication == "saved" and project in service.publication_tasks:
                    await asyncio.wait_for(asyncio.shield(service.publication_tasks[project]), 10)
                return service.store.read(project, identifier)
            await asyncio.wait_for(changed.wait(), 10)
    finally:
        service.supervisor.listeners.discard(changed)


@pytest.mark.asyncio
async def test_cancelled_capture_survives_reload_before_fixed_submission(tmp_path):
    from packages.resume_core.background_store import JobStore, expiration
    from packages.resume_core.background_retention import JobRetention
    from packages.resume_core.background_limits import LIMITS
    service, factory, workspace, _request, _connection, _old = await environment(tmp_path)
    provider = CreationProvider()
    service.projects.provider_factory = lambda: (provider, "processing-model")
    try:
        command = rewrite_command(workspace, action="history-session:7")
        origin = ActionCapture.model_validate(command["request"]["selection"]["capture"])
        await service.fixed.invalidate_action(workspace.project_id, origin)
        await service.fixed.invalidate_action(workspace.project_id, origin)
        reopened = JobStore(service.store.root, clock=service.store.clock).load(workspace.project_id)
        assert len(reopened.fixed_invalidations) == 1 and not reopened.jobs
        with pytest.raises(ProjectFailure, match="STALE_SELECTION"):
            await service.fixed.submit(workspace.project_id, fixed_request(service, workspace.project_id, "late-request", command))
        assert not service.store.load(workspace.project_id).jobs and not provider.calls
        expired = fixed_request(service, workspace.project_id, "expired-late-request", command)
        before = service.store.clock()
        service.store.clock = lambda: expiration(before, LIMITS.request_replay_seconds + 1)
        retained = JobRetention(service.store).sweep(workspace.project_id)
        assert not retained.fixed_invalidations and retained.expired_through_epoch == expired.request_epoch
        with pytest.raises(BackgroundFailure, match="REQUEST_EXPIRED"):
            await service.fixed.submit(workspace.project_id, expired)
        directory = service.store.projects / workspace.project_id / "fixed-inputs"
        assert not directory.exists() and not provider.calls
    finally:
        await service.shutdown()
        factory.verify()
        service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_fixed_rewrite_uses_the_existing_service_and_one_owned_permit(tmp_path):
    service, factory, workspace, _request, _connection, _old = await environment(tmp_path)
    provider = CreationProvider()
    service.projects.provider_factory = lambda: (provider, "processing-model")
    try:
        request = fixed_request(service, workspace.project_id, "fixed-rewrite", {"kind": "rewrite",
            "request": {"selection": selection(workspace).model_dump(by_alias=True), "instruction": "Clarify"}})
        reply, created = await service.fixed.submit(workspace.project_id, request)
        assert created and reply.job.submission.models[0].model == "processing-model"
        done = await settled(service, workspace.project_id, reply.job.id, publication="saved")
        assert done.execution == "completed" and len(done.attempts) == 1 and done.attempts[0].cleanup_verified
        assert len(provider.calls) == 1 and not service.admission.locked()
        saved, _checksum = service.projects.storage.read_committed(workspace.project_id)
        record = next(s for s in saved.sync_records if s.id == reply.sync_id)
        assert record.action_id == reply.action_id and record.proposed_steps and not record.ready
        assert "Clearer:" in next(b for b in saved.project.document.blocks() if b.id == "narrative").content[0].text
        duplicate, created = await service.fixed.submit(workspace.project_id, request)
        assert not created and duplicate.job.receipt == done.receipt
    finally:
        await service.shutdown()
        factory.verify()
        service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_fixed_processing_reuses_two_stages_and_original_assembly(tmp_path, monkeypatch):
    service, factory, _workspace, _request, _connection, _old = await environment(tmp_path)
    provider = CreationProvider()
    service.projects.provider_factory = lambda: (provider, "processing-model")
    from packages.resume_core.extraction.parser import extract
    from tests.recovery.test_background_exports import HeldRenderer
    service.projects.renderer = HeldRenderer()
    service.projects.renderer.release.set()
    async def inline_extract(data, name, pasted, _files):
        return extract(data, name, pasted)
    monkeypatch.setattr("resume_api.rich_projects.run_extract", inline_extract)
    try:
        source = await service.projects.select(Path("tests/fixtures/recovery/E1.txt").read_bytes(), "pasted.txt", True)
        request = fixed_request(service, source.project_id, "process-source", {"kind": "processing"})
        reply, _created = await service.fixed.submit(source.project_id, request)
        done = await settled(service, source.project_id, reply.job.id, publication="saved")
        await asyncio.wait_for(service.fixed.renders[done.id], 10)
        assert [a.stage for a in done.attempts] == ["assessment", "extraction"]
        assert all(a.cleanup_verified for a in done.attempts) and len(provider.calls) == 2
        saved, _checksum = service.projects.storage.read_committed(source.project_id)
        assert saved.pre_draft is None and saved.project is not None
        assert saved.project.renders and not service.fixed.render_errors
        original = source.pre_draft.sources[0]
        kept = saved.project.sources[0]
        assert (kept.id, kept.revision, kept.byte_sha256, kept.byte_ref, kept.overlays,
            [u.text for u in kept.units]) == (original.id, original.revision, original.byte_sha256,
            original.byte_ref, original.overlays, [u.text for u in original.units])
        assert not service.admission.locked()
    finally:
        await service.shutdown()
        factory.verify()
        service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [f"NB-F03:v{i:02d}" for i in range(1, 9)])
async def test_processing_stage_boundaries_keep_captured_input_and_stop_authority(tmp_path, monkeypatch, variant):
    service, factory, _workspace, _request, _connection, _old = await environment(tmp_path)
    provider = HeldProvider() if variant == "NB-F03:v08" else CreationProvider(fail_kind="ResumeAssessment" if variant == "NB-F03:v05" else None)
    # The advisory service intentionally recovers INVALID_RESULT; infrastructure failures remain typed.
    if variant == "NB-F03:v05":
        def fail(_request, _files, _cancel):
            raise ContentFailure("AUTH_REQUIRED")
        provider.generate = fail
    service.projects.provider_factory = lambda: (provider, "processing-model")
    entered, release, deletion_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    late = variant == "NB-F03:v06"
    async def observe(name, job_id):
        control = service.supervisor.controls.get(job_id)
        if name == ("before_payload_stored" if late else "children_verified_dead") and control and (late or control.stage == 0):
            entered.set()
            await release.wait()
    if variant not in {"NB-F03:v05", "NB-F03:v08"}:
        service.supervisor.observer = observe
    deleted = None
    try:
        source = await source_project(service, monkeypatch)
        request = fixed_request(service, source.project_id, "processing-boundary", {"kind": "processing"})
        reply, _created = await service.fixed.submit(source.project_id, request)
        if variant == "NB-F03:v08":
            _content, model_release = await asyncio.wait_for(provider.entered.get(), 10)
            control = service.supervisor.controls[reply.job.id]
            service.supervisor.clock.advance(180)
            await asyncio.wait_for(control.cancelled.wait(), 10)
            model_release.set()
        elif variant != "NB-F03:v05":
            await asyncio.wait_for(entered.wait(), 10)
            if variant in {"NB-F03:v01", "NB-F03:v06"}:
                await service.projects.select(Path("tests/fixtures/recovery/E1.txt").read_bytes() + b"\nChanged source", "changed.txt", True, id=source.project_id)
            elif variant == "NB-F03:v02":
                await service.supervisor.cancel(source.project_id, reply.job.id)
            elif variant == "NB-F03:v03":
                stop = service.stop_project
                async def stopped(project):
                    deletion_started.set()
                    return await stop(project)
                monkeypatch.setattr(service, "stop_project", stopped)
                deleted = asyncio.create_task(service.projects.delete_project(source.project_id))
                await asyncio.wait_for(deletion_started.wait(), 10)
            elif variant == "NB-F03:v04":
                second = fixed_request(service, source.project_id, "second-processing", {"kind": "processing"})
                with pytest.raises(ProjectFailure, match="PROJECT_GENERATION_ACTIVE"):
                    await service.fixed.submit(source.project_id, second)
            elif variant == "NB-F03:v07":
                rules = service.projects.rules.load()
                service.projects.rules.save(rules.markdown + "\nKeep exact source units.\n", rules.revision)
            release.set()
        if deleted is not None:
            result = await asyncio.wait_for(deleted, 10)
            assert result.status == "deleted" and len(provider.calls) == 1
            owned = service.supervisor.controls[reply.job.id].owned
            assert owned is None or owned.verified_dead()
            assert service.supervisor.active is None and service.supervisor.fenced is None
        else:
            done = await settled(service, source.project_id, reply.job.id)
            if variant == "NB-F03:v04":
                done = await settled(service, source.project_id, reply.job.id, publication="saved")
                assert len(done.attempts) == 2 and len(provider.calls) == 2
            elif late:
                changed = asyncio.Event()
                service.supervisor.listeners.add(changed)
                try:
                    while service.store.read(source.project_id, reply.job.id).publication != "needs_review":
                        changed.clear()
                        if service.store.read(source.project_id, reply.job.id).publication == "needs_review":
                            break
                        await asyncio.wait_for(changed.wait(), 10)
                finally:
                    service.supervisor.listeners.discard(changed)
                assert len(provider.calls) == 2 and done.receipt is None
            else:
                assert len(done.attempts) == 1 and done.receipt is None
                expected = "CANCELLED" if variant == "NB-F03:v02" else "AUTH_REQUIRED" if variant == "NB-F03:v05" else "DEADLINE" if variant == "NB-F03:v08" else "DEPENDENCY_CHANGED"
                assert done.error.code == expected
            if variant != "NB-F03:v04":
                current = service.projects.storage.read_committed(source.project_id)[0]
                assert current.project is None and current.pre_draft is not None
            assert all(a.cleanup_verified for a in service.store.read(source.project_id, reply.job.id).attempts)
            assert not service.admission.locked()
    finally:
        release.set()
        if isinstance(provider, HeldProvider):
            provider.release_all()
        if deleted is not None and not deleted.done():
            await asyncio.gather(deleted, return_exceptions=True)
        await service.shutdown()
        factory.verify()
        service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [f"NB-F02:v{i:02d}" for i in range(1, 7)])
async def test_fixed_publication_keeps_independence_and_exact_proposal_ownership(tmp_path, variant):
    service, factory, workspace, _request, _connection, _old = await environment(tmp_path)
    provider = HeldProvider()
    provider.replace_bound = variant == "NB-F02:v06"
    service.projects.provider_factory = lambda: (provider, "processing-model")
    try:
        if variant == "NB-F02:v03":
            workspace = linked_fixture(service, workspace)
        target = "title" if variant == "NB-F02:v06" else "narrative"
        command = rewrite_command(workspace, target)
        request = fixed_request(service, workspace.project_id, "fixed-overlap", command)
        reply, _created = await service.fixed.submit(workspace.project_id, request)
        _content, release = await asyncio.wait_for(provider.entered.get(), 10)
        if variant == "NB-F02:v05":
            proof = hold_writer(service, workspace)
            release.set()
            first = await settled(service, workspace.project_id, reply.job.id, publication="waiting_for_sync")
            current = service.projects.storage.read_committed(workspace.project_id)[0]
            second, _ = await service.fixed.submit(workspace.project_id,
                fixed_request(service, workspace.project_id, "fixed-other", rewrite_command(current, "quote", "other-action")))
            _content, second_release = await asyncio.wait_for(provider.entered.get(), 10)
            second_release.set()
            await settled(service, workspace.project_id, second.job.id, publication="waiting_for_sync")
            before = service.projects.storage.read_committed(workspace.project_id)[0]
            with pytest.raises(ProjectFailure, match="JOB_SCOPE_INVALID"):
                service.projects.disposition(workspace.project_id, reply.sync_id, "applied")
            after = service.projects.storage.read_committed(workspace.project_id)[0]
            assert before == after and all(s.proposed_steps for s in after.sync_records if s.id in {reply.sync_id, second.sync_id})
            assert first.receipt is None and service.store.read(workspace.project_id, second.job.id).receipt is None
            assert proof.epoch == service.store.load(workspace.project_id).writer.epoch
        else:
            if variant == "NB-F02:v04":
                await service.fixed.invalidate_action(workspace.project_id, ActionCapture.model_validate(command["request"]["selection"]["capture"]))
            elif variant in {"NB-F02:v03", "NB-F02:v06"}:
                record = workspace.project.facts.records[0].model_copy(deep=True)
                record.location.value = record.location.raw_text = "Independent new location"
                save_and_detach(service, workspace.project_id, mutation(workspace,
                    [{"kind": "put_record", "beforeRevision": record.revision, "record": record}], "manual-fact"))
            else:
                changed_target = "quote" if variant == "NB-F02:v01" else "narrative"
                save_and_detach(service, workspace.project_id,
                    mutation(workspace, [put(workspace, changed_target, text="Independent manual input")], "manual-input"))
            release.set()
            expected = "saved" if variant == "NB-F02:v01" else "needs_review"
            done = await settled(service, workspace.project_id, reply.job.id, publication=expected)
            current = service.projects.storage.read_committed(workspace.project_id)[0]
            assert len(provider.calls) == 1 and len(done.attempts) == 1 and done.attempts[0].cleanup_verified
            assert (done.receipt is not None) == (variant == "NB-F02:v01")
            if variant in {"NB-F02:v01", "NB-F02:v02"}:
                assert next(b for b in current.project.document.blocks() if b.id == changed_target).content[0].text == "Independent manual input"
            if variant in {"NB-F02:v03", "NB-F02:v06"}:
                assert current.project.facts.records[0].location.value == "Independent new location"
            original = next(b for b in workspace.project.document.blocks() if b.id == target)
            kept = next(b for b in current.project.document.blocks() if b.id == target)
            if variant == "NB-F02:v04":
                assert kept == original and done.capture_invalidated
            if variant != "NB-F02:v01":
                assert next(s for s in current.sync_records if s.id == reply.sync_id).proposed_steps
        assert not service.admission.locked()
    finally:
        provider.release_all()
        await service.shutdown()
        factory.verify()
        service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [f"NB-Q04:v{i:02d}" for i in range(1, 8)])
async def test_real_fixed_dispatch_respects_project_fairness_and_eligibility(tmp_path, variant):
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    provider = CreationProvider()
    service.projects.provider_factory = lambda: (provider, "processing-model")
    dispatched, eligible = [], {"sync": variant != "NB-Q04:v06"}
    project = workspace.project_id
    old_eligible = service.supervisor.eligible
    service.supervisor.eligible = lambda job: old_eligible(job) and (job.submission.kind != "reconciliation" or eligible["sync"])
    async def observe(name, identifier):
        if name != "slot_granted":
            return
        job = service.supervisor.controls[identifier].job
        dispatched.append((identifier, job.submission.identity.project_id, job.submission.scheduling_class,
            service.supervisor.order.interactive_streak[project]))
        if job.submission.kind == "rewrite":
            eligible["sync"] = True
    service.supervisor.observer = observe
    actor = None
    try:
        _blocker, actor = await blocked_agent(service, factory, payload)
        service.supervisor.order.interactive_streak[project] = 2 if variant not in {"NB-Q04:v02", "NB-Q04:v03"} else 3 if variant == "NB-Q04:v02" else 4
        service.supervisor.order.last_class[project] = "reconciliation"
        dispatched.clear()
        sync, _ = await service.fixed.submit(project, fixed_request(service, project, "auto-first", completion_command()))
        interactive, _ = await service.fixed.submit(project, fixed_request(service, project, "interactive-first", rewrite_command(workspace)))
        if variant == "NB-Q04:v04":
            other = clone_project(service, workspace)
            other_reply, _ = await service.fixed.submit(other.project_id, fixed_request(service, other.project_id, "other-project", rewrite_command(other)))
        else:
            other_reply = None
        if variant == "NB-Q04:v07":
            previous = sync
            sync, _ = await service.fixed.submit(project, fixed_request(service, project, "auto-new", completion_command("new-auto")))
            superseded = service.store.read(project, previous.job.id)
            assert superseded.execution == "cancelled" and not superseded.attempts
        assert service.store.read(project, sync.job.id).execution == "queued"
        assert not dispatched and not provider.calls
        actor.result.set()
        await settled(service, project, sync.job.id)
        await settled(service, project, interactive.job.id)
        if other_reply is not None:
            await settled(service, other_reply.project_id, other_reply.job.id)
            other_dispatch = next(item for item in dispatched if item[0] == other_reply.job.id)
            assert other_dispatch[3] == 2
        local = [item for item in dispatched if item[1] == project]
        sync_position = next(i for i, item in enumerate(local) if item[0] == sync.job.id)
        assert sum(item[2] == "interactive" for item in local[:sync_position]) <= 1
        if variant in {"NB-Q04:v02", "NB-Q04:v03"}:
            assert sync_position == 0
        assert len(provider.calls) == (2 if other_reply else 1)
        assert all(a.cleanup_verified for job in service.store.load(project).jobs for a in job.attempts)
    finally:
        if actor is not None:
            actor.result.set()
        await service.shutdown()
        factory.verify()
        service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [f"NB-Q07:v{i:02d}" for i in range(1, 5)])
async def test_fixed_queue_invalidates_stale_work_without_hidden_model_retries(tmp_path, variant):
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    provider = HeldProvider() if variant == "NB-Q07:v04" else CreationProvider()
    service.projects.provider_factory = lambda: (provider, "processing-model")
    actor = None
    try:
        if variant == "NB-Q07:v04":
            workspace = linked_fixture(service, workspace)
            command = completion_command(block="narrative", interpret=True)
            reply, _ = await service.fixed.submit(workspace.project_id, fixed_request(service, workspace.project_id, "running-auto", command))
            _content, release = await asyncio.wait_for(provider.entered.get(), 10)
            save_and_detach(service, workspace.project_id,
                mutation(workspace, [put(workspace, "narrative", text="Newer canonical input")], "newer-source"))
            release.set()
            done = await settled(service, workspace.project_id, reply.job.id, publication="needs_review")
            assert len(provider.calls) == 1 and len(done.attempts) == 1 and done.receipt is None
        else:
            _blocker, actor = await blocked_agent(service, factory, payload)
            if variant == "NB-Q07:v01":
                reply, _ = await service.fixed.submit(workspace.project_id,
                    fixed_request(service, workspace.project_id, "queued-selection", rewrite_command(workspace)))
                save_and_detach(service, workspace.project_id,
                    mutation(workspace, [put(workspace, "narrative", text="Newer canonical input")], "newer-source"))
            else:
                reply, _ = await service.fixed.submit(workspace.project_id,
                    fixed_request(service, workspace.project_id, "auto-old", completion_command("auto-old")))
                if variant == "NB-Q07:v03":
                    explicit, _ = await service.fixed.submit(workspace.project_id,
                        fixed_request(service, workspace.project_id, "explicit-rewrite", rewrite_command(workspace)))
                newer, _ = await service.fixed.submit(workspace.project_id,
                    fixed_request(service, workspace.project_id, "auto-new", completion_command("auto-new")))
                assert service.store.read(workspace.project_id, reply.job.id).execution == "cancelled"
                assert not service.store.read(workspace.project_id, reply.job.id).attempts
            actor.result.set()
            done = await settled(service, workspace.project_id, reply.job.id)
            if variant == "NB-Q07:v01":
                assert done.execution == "failed" and done.error.code == "DEPENDENCY_CHANGED" and not done.attempts and not provider.calls
            else:
                await settled(service, workspace.project_id, newer.job.id)
                if variant == "NB-Q07:v03":
                    finished = await settled(service, workspace.project_id, explicit.job.id, publication="saved")
                    assert finished.receipt is not None and len(provider.calls) == 1
                else:
                    assert not provider.calls
        current = service.projects.storage.read_committed(workspace.project_id)[0]
        if variant in {"NB-Q07:v01", "NB-Q07:v04"}:
            assert next(b for b in current.project.document.blocks() if b.id == "narrative").content[0].text == "Newer canonical input"
        assert not service.admission.locked()
    finally:
        if actor is not None:
            actor.result.set()
        if isinstance(provider, HeldProvider):
            provider.release_all()
        await service.shutdown()
        factory.verify()
        service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["before-dispatch", "between-stages"])
@pytest.mark.parametrize("reason", ["AUTH_REQUIRED", "RATE_LIMITED"])
async def test_account_preflight_pauses_dispatch_without_repeated_attempts(tmp_path, monkeypatch, boundary, reason):
    service, factory, workspace, payload, connection, _old = await environment(tmp_path)
    provider = CreationProvider()
    service.projects.provider_factory = lambda: (provider, "processing-model")
    actor = None
    reached, release = asyncio.Event(), asyncio.Event()
    try:
        if boundary == "before-dispatch":
            _job, actor = await blocked_agent(service, factory, payload)
            project = workspace.project_id
            command = rewrite_command(workspace)
        else:
            async def observe(name, identifier):
                control = service.supervisor.controls.get(identifier)
                if name == "children_verified_dead" and control and control.stage == 0:
                    reached.set()
                    await release.wait()
            service.supervisor.observer = observe
            source = await source_project(service, monkeypatch)
            project, command = source.project_id, {"kind": "processing"}
        reply, _ = await service.fixed.submit(project, fixed_request(service, project, "account-boundary", command))
        if boundary == "between-stages":
            await asyncio.wait_for(reached.wait(), 10)
        connection["value"] = replace(connection["value"], ready=False,
            reason="AGENT_QUOTA" if reason == "RATE_LIMITED" else "AGENT_AUTH_REQUIRED")
        if actor is not None:
            actor.result.set()
        release.set()
        changed = asyncio.Event()
        service.supervisor.listeners.add(changed)
        try:
            while service.supervisor.paused is None:
                changed.clear()
                if service.supervisor.paused is None:
                    await asyncio.wait_for(changed.wait(), 10)
        finally:
            service.supervisor.listeners.discard(changed)
        control = service.supervisor.controls[reply.job.id]
        await asyncio.wait_for(control.task, 10)
        done = service.store.read(project, reply.job.id)
        assert service.supervisor.paused == reason and service.store.dispatch_state().paused == reason
        assert done.error.code == reason and done.receipt is None
        assert len(done.attempts) == (1 if boundary == "between-stages" else 0)
        assert len(provider.calls) == (1 if boundary == "between-stages" else 0)
        assert done.execution == ("failed" if boundary == "between-stages" else "queued")
    finally:
        release.set()
        if actor is not None:
            actor.result.set()
        await service.shutdown()
        factory.verify()
        service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_failed_automatic_replacement_keeps_the_old_job_and_removes_inert_input(tmp_path, monkeypatch):
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    service.projects.provider_factory = lambda: (CreationProvider(), "processing-model")
    actor = None
    try:
        _job, actor = await blocked_agent(service, factory, payload)
        old, _ = await service.fixed.submit(workspace.project_id,
            fixed_request(service, workspace.project_id, "retained-auto", completion_command("old-auto")))
        capacity = service.store._capacity
        def reject(state, states, **options):
            if any(r.identity.request_id == "rejected-auto" for r in state.requests):
                raise BackgroundFailure("JOB_STORAGE_FULL")
            return capacity(state, states, **options)
        monkeypatch.setattr(service.store, "_capacity", reject)
        with pytest.raises(BackgroundFailure, match="JOB_STORAGE_FULL"):
            await service.fixed.submit(workspace.project_id,
                fixed_request(service, workspace.project_id, "rejected-auto", completion_command("new-auto")))
        assert service.store.read(workspace.project_id, old.job.id).execution == "queued"
        with service.store.guard(workspace.project_id) as directory:
            assert len(list((directory / "fixed-inputs").glob("*.json"))) == 1
        monkeypatch.setattr(service.store, "_capacity", capacity)
        actor.result.set()
        await settled(service, workspace.project_id, old.job.id)
    finally:
        if actor is not None:
            actor.result.set()
        await service.shutdown()
        factory.verify()
        service.supervisor.clock.verify()
