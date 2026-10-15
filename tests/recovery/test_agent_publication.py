"""Canonical save proof, cancellation ordering and crash recovery without inference."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import sys

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.agent_store import AgentFailure, run_in
from packages.resume_core.models.agent import AgentCommitRequest, AgentOwner, AgentQuery
from packages.resume_core.models.rich_mutations import RichMutation, PutBlock
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_mutations import locate, inline_text
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.rules import RulesStore
from packages.resume_core.storage import StorageFailure
from resume_api.agent.edits import prepare
from resume_api.agent.service import AgentService
from resume_api.gui_projects import ProjectFailure
from resume_api.rich_projects import RichProjectService
from tests.recovery.test_agent_edits import command, replace
from tests.recovery.test_agent_tools import tools_setup


def block(workspace, identifier="narrative"):
    found = locate(workspace.project.document, identifier)
    return found[0][found[1]]


async def staged(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path)
    service.controls[session.run.id] = session.control
    read = session.book.read(AgentQuery(kind="document", ids=["narrative"]))
    result = prepare(session, command(replace(read.snapshot, "narrative", 0, 6, "Clear")))
    offer = asyncio.create_task(service.publication.offer(session, result.batch_id))
    async with asyncio.timeout(2):
        while True:
            _, _, journal = run_in(service.store.load(workspace.project_id), session.run.id)
            batch = journal.batches[0].batch
            if batch.state == "offered":
                break
            await asyncio.sleep(0.01)
    lease = service.leases.leases[workspace.project_id]
    owner = AgentOwner(token=lease.token, epoch=lease.epoch)
    claim = service.publication.claim(workspace.project_id, session.run.id, result.batch_id, owner)
    request = AgentCommitRequest(owner=owner, ticket=claim.ticket, requestSha256=batch.request_sha256)
    return session, service, workspace, batch, offer, request


def manual(workspace, *, action="manual:1", kind="typing", value="Manual text"):
    target = block(workspace).model_copy(deep=True)
    target.content[0].text = value
    return RichMutation(schemaVersion=1, projectId=workspace.project_id, clientMutationId="manual_" + kind,
        actionId=action, kind=kind, capture={"sessionId": "history_1", "actionId": action, "actionToken": 0, "dependencies": []},
        steps=[PutBlock(kind="put_block", parentId="job-section", afterId=None, beforeRevision=block(workspace).revision,
            block=target.model_copy(update={"children": []}), keepChildren=True)])


@pytest.mark.asyncio
async def test_concurrent_commits_save_once_and_ordinary_route_cannot_publish_reserved_request(tmp_path, monkeypatch):
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    projects = service.projects
    calls, original = [], projects.storage.save
    def save(*args, **kwargs):
        calls.append(args[0].project_revision)
        return original(*args, **kwargs)
    monkeypatch.setattr(projects.storage, "save", save)
    try:
        with pytest.raises(ProjectFailure, match="AGENT_TICKET_INVALID"):
            projects.mutate(workspace.project_id, batch.mutation)
        forged_undo = batch.mutation.model_copy(update={"client_mutation_id": "forged_undo", "kind": "undo"})
        with pytest.raises(ProjectFailure, match="AGENT_TICKET_INVALID"):
            projects.mutate(workspace.project_id, forged_undo)
        def commit():
            return service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        with ThreadPoolExecutor(2) as executor:
            first, second = list(executor.map(lambda _: commit(), range(2)))
        assert first.receipt == second.receipt and first.receipt.durable
        assert (await offer).durable and len(calls) == 1
        saved = projects.read(workspace.project_id)
        assert "".join(inline_text(span) for span in block(saved).content) == "Clear workExact URL"
        assert len(saved.mutation_replay) == 1 and not saved.sync_records
        persisted, _ = projects.storage.read_committed(workspace.project_id)
        assert persisted == saved
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_cancel_waiting_for_publication_lock_keeps_the_already_saved_batch(tmp_path, monkeypatch):
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    written, cancelled = threading.Event(), threading.Event()
    original = service.projects.storage.save
    def save(*args, **kwargs):
        callback = kwargs["after_workspace"]
        def after(checksum):
            callback(checksum)
            written.set()
        return original(*args, **{**kwargs, "after_workspace": after})
    monkeypatch.setattr(service.projects.storage, "save", save)
    def cancel():
        assert written.wait(2)
        service.cancel(workspace.project_id, session.run.id)
        cancelled.set()
    worker = threading.Thread(target=cancel)
    worker.start()
    try:
        result = service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        worker.join(timeout=2)
        assert cancelled.is_set() and result.receipt.durable and (await offer).durable
        finished = service.store.finish(workspace.project_id, session.run.id, "cancelled", error="AGENT_CANCELLED")
        assert finished.state == "cancelled" and finished.saved_batch_id == batch.id
        persisted, _ = service.projects.storage.read_committed(workspace.project_id)
        assert persisted.mutation_replay[0].request_sha256 == batch.request_sha256
    finally:
        worker.join(timeout=2)
        await session.close()


@pytest.mark.asyncio
async def test_wrong_ticket_is_rejected_before_save_and_receipt_wait_is_bounded(tmp_path):
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    try:
        wrong = request.model_copy(update={"ticket": "wrong_ticket_capability_0123456789"})
        with pytest.raises(AgentFailure, match="AGENT_TICKET_INVALID"):
            service.publication.commit(workspace.project_id, session.run.id, batch.id, wrong)
        assert not service.projects.read(workspace.project_id).mutation_replay
        service.publication.clock = lambda: 10 ** 12
        receipt = await asyncio.wait_for(offer, 1)
        assert receipt.disposition == "rejected" and receipt.error.code == "AGENT_RECEIPT_TIMEOUT"
        assert not service.projects.read(workspace.project_id).mutation_replay
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_failure_before_replace_does_not_enter_memory_or_later_manual_save(tmp_path, monkeypatch):
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    projects = service.projects
    original = projects.storage.save
    def failed(*args, **kwargs):
        raise ProjectStoreFailure("PROJECT_UNSAFE_STORAGE")
    monkeypatch.setattr(projects.storage, "save", failed)
    try:
        reply = service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        assert reply.receipt.disposition == "save_failed" and (await offer).disposition == "save_failed"
        assert projects.read(workspace.project_id).project.document == workspace.project.document
        assert not projects.read(workspace.project_id).mutation_replay
        monkeypatch.setattr(projects.storage, "save", original)
        projects.persist(workspace.project_id)
        persisted, _ = projects.storage.read_committed(workspace.project_id)
        assert persisted.project.document == workspace.project.document and not persisted.mutation_replay
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_post_fsync_registry_error_is_saved_and_future_manual_save_preserves_it(tmp_path, monkeypatch):
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    projects = service.projects
    original = projects.storage._write_registry
    monkeypatch.setattr(projects.storage, "_write_registry", lambda _: (_ for _ in ()).throw(StorageFailure("UNSAFE_STORAGE")))
    try:
        reply = service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        assert reply.receipt.disposition == "saved" and (await offer).durable
        assert "".join(inline_text(span) for span in block(reply.project.workspace).content) == "Clear workExact URL"
        monkeypatch.setattr(projects.storage, "_write_registry", original)
        projects.persist(workspace.project_id)
        persisted, _ = projects.storage.read_committed(workspace.project_id)
        assert persisted.mutation_replay[0].request_sha256 == batch.request_sha256
        assert "".join(inline_text(span) for span in block(persisted).content) == "Clear workExact URL"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_replace_without_fsync_is_fenced_until_exact_read_recovery(tmp_path, monkeypatch):
    import packages.resume_core.rich_project_store as module
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    projects = service.projects
    original = module.atomic_write
    def interrupted(path, raw):
        if path.name != "workspace.json":
            return original(path, raw)
        descriptor, temporary = tempfile.mkstemp(prefix=".foldcv-write-", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        raise StorageFailure("simulated directory fsync failure")
    monkeypatch.setattr(module, "atomic_write", interrupted)
    try:
        reply = service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        assert reply.receipt.disposition == "outcome_unknown" and (await offer).disposition == "outcome_unknown"
        assert projects.persist(workspace.project_id) == "failed"
        with pytest.raises(ProjectFailure, match="AGENT_OUTCOME_UNKNOWN"):
            projects.mutate(workspace.project_id, manual(projects.read(workspace.project_id)))
        with pytest.raises(ProjectFailure, match="AGENT_OUTCOME_UNKNOWN"):
            await projects.export(workspace.project_id)
        assert projects.read(workspace.project_id).project.document == workspace.project.document
        monkeypatch.setattr(module, "atomic_write", original)
        receipt = service.publication.recover(workspace.project_id, session.run.id, batch.id)
        assert receipt.durable and workspace.project_id not in projects.agent_recovery_fences
        assert "".join(inline_text(span) for span in block(projects.read(workspace.project_id)).content) == "Clear workExact URL"
        assert len(projects.read(workspace.project_id).mutation_replay) == 1
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_sidecar_crash_after_canonical_save_recovers_saved_without_reapplying(tmp_path, monkeypatch):
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    original = service.store.record_receipt
    monkeypatch.setattr(service.store, "record_receipt", lambda *a, **k: (_ for _ in ()).throw(AgentFailure("AGENT_STORE_SAVE_FAILED")))
    try:
        with pytest.raises(AgentFailure, match="AGENT_OUTCOME_UNKNOWN"):
            service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        offer.cancel()
        await asyncio.gather(offer, return_exceptions=True)
        monkeypatch.setattr(service.store, "record_receipt", original)
        storage = RichProjectStore(service.projects.storage.root)
        restarted_projects = RichProjectService(tmp_path / "restart-operations", RulesStore(storage.root), lambda: None, storage=storage)
        restarted = AgentService(restarted_projects, service.runtime, service.connection, tools=service.tools)
        restarted_projects.agent = restarted
        restarted.recover()
        _, run, journal = run_in(restarted.store.load(workspace.project_id), session.run.id)
        assert run.state == "interrupted" and run.saved_batch_id == batch.id and not run.outcome_unknown
        assert journal.batches[0].receipt.durable and not restarted_projects.agent_recovery_fences
        assert len(restarted_projects.read(workspace.project_id).mutation_replay) == 1
        assert not service.runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_cancel_before_publication_and_stale_commit_preserve_the_current_resume(tmp_path):
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    try:
        service.cancel(workspace.project_id, session.run.id)
        with pytest.raises(AgentFailure, match="AGENT_CANCELLED"):
            service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        assert (await offer).disposition == "cancelled"
        assert not service.projects.read(workspace.project_id).mutation_replay
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_targeted_typing_after_claim_rejects_but_unrelated_typing_is_preserved(tmp_path):
    for targeted in (True, False):
        session, service, workspace, batch, offer, request = await staged(tmp_path / str(targeted))
        try:
            current = service.projects.read(workspace.project_id)
            change = manual(current)
            if not targeted:
                replacement = block(current, "quote").model_copy(deep=True)
                replacement.content[0].text = "Unrelated user typing"
                change.steps[0].block, change.steps[0].before_revision = replacement, replacement.revision
                change.steps[0].after_id = "toggle"
            service.projects.mutate(workspace.project_id, change)
            reply = service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
            assert (await offer).disposition == ("stale" if targeted else "saved")
            assert reply.receipt.durable is not targeted
            if not targeted:
                assert block(reply.project.workspace, "quote").content[0].text == "Unrelated user typing"
        finally:
            await session.close()


@pytest.mark.asyncio
async def test_saved_action_undo_is_a_separate_manual_save_and_keeps_the_saved_receipt(tmp_path):
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    try:
        service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        assert (await offer).durable
        current = service.projects.read(workspace.project_id)
        undo = manual(current, action=batch.mutation.action_id, kind="undo", value="Styled")
        undo.steps[0].block = block(workspace).model_copy(update={"children": []})
        service.projects.mutate(workspace.project_id, undo)
        assert block(service.projects.read(workspace.project_id)).content == block(workspace).content
        _, run, journal = run_in(service.store.load(workspace.project_id), session.run.id)
        assert run.saved_batch_id == batch.id and journal.batches[0].receipt.durable
        assert [action.kind for action in journal.batches[0].history_actions] == ["undo"]
        assert not service.runtime.calls
    finally:
        await session.close()
