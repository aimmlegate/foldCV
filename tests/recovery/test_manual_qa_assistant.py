"""Whole-project reading, shared formatting and live edit authority."""

import asyncio
import json

import pytest

from packages.resume_core.agent_store import AgentFailure, run_in
from packages.resume_core.models.agent import AgentPrepareRequest, AgentQuery
from packages.resume_core.models.rich_document import ParagraphBlock, StyledText
from packages.resume_core.rich_mutations import apply_rich_mutation
from resume_api.agent.edits import prepare
from tests.recovery.test_agent_tools import tools_setup
from tests.recovery.test_agent_publication import staged


@pytest.mark.asyncio
async def test_whole_document_pages_read_every_block_once_beyond_100_and_old_byte_budget(tmp_path):
    session, _, workspace, _ = tools_setup(tmp_path, allow_edits=False)
    try:
        parent = workspace.project.document.regions[-1]
        parent.blocks.extend(ParagraphBlock(id=f"marker_{index}", revision=1, type="paragraph", props={},
            content=[StyledText(type="text", text=f"UNIQUE_{index}:" + "Ж" * 1100, styles={})],
            children=[], provenance=[]) for index in range(137))
        expected = {block.id for block in workspace.project.document.blocks()}
        seen, total, cursor = [], 0, None
        while True:
            reply = await session.call("get_resume_context", AgentQuery(kind="document", cursor=cursor))
            assert "error" not in reply, reply
            raw = json.dumps(reply, ensure_ascii=False).encode()
            assert len(raw) <= 16384 + 200
            total += len(raw)
            page = json.loads(reply["content"])
            assert "fragment" not in page
            seen.extend(block["id"] for block in page.get("blocks", []))
            assert all(block["children"] == [] for block in page.get("blocks", []))
            cursor = reply["snapshot"]["nextCursor"]
            if cursor is None:
                break
        assert set(seen) == expected and len(seen) == len(expected)
        assert total > 256 * 1024
        assert session.book.require(reply["snapshot"]["id"]).complete
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_argument_error_is_correctable_and_read_only_keeps_fact_and_source_access(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path, allow_edits=False)
    try:
        error = session.preflight({"name": "get_resume_context", "arguments": {"kind": "document"}})
        assert error == "AGENT_ARGUMENT_INVALID" and session.argument_issues
        before = workspace.model_dump_json()
        service.projects.catalog.update(workspace.project_id, read_only=True)
        for name, query in [("get_resume_context", AgentQuery(kind="document")),
                ("get_working_facts", AgentQuery(kind="facts")), ("get_original_source", AgentQuery(kind="source"))]:
            assert "error" not in await session.call(name, query)
        assert workspace.model_dump_json() == before
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["undo", "redo"])
async def test_foreground_assistant_uses_owned_editor_history_and_the_shared_publisher(direction, tmp_path):
    from packages.resume_core.background_inverse import inverse_mutation
    from packages.resume_core.models.agent import AgentHistoryOffer, AgentOwner, AgentProjectAction, AgentCommitRequest
    from tests.recovery.test_agent_publication import manual, block
    session, service, workspace, _ = tools_setup(tmp_path, message=direction.title() + " the latest change.")
    service.controls[session.run.id] = session.control
    try:
        before = workspace.model_copy(deep=True)
        service.projects.mutate(workspace.project_id, manual(before, value="User edit 42"))
        edited = service.projects.read(workspace.project_id).model_copy(deep=True)
        inverse = inverse_mutation(before, edited, mutation_id="owner-undo", session_id="history_1")
        assert inverse is not None
        if direction == "redo":
            service.projects.mutate(workspace.project_id, inverse)
            current = service.projects.read(workspace.project_id).model_copy(deep=True)
            inverse = inverse_mutation(edited, current, mutation_id="owner-redo", session_id="history_1")
            inverse.kind = "redo"
        current = service.projects.read(workspace.project_id)
        lease = service.leases.leases[workspace.project_id]
        owner = AgentOwner(token=lease.token, epoch=lease.epoch)
        offered = AgentHistoryOffer(owner=owner, projectRevision=current.project_revision,
            documentRevision=current.document_revision, factsRevision=current.project.facts.revision,
            undo=inverse if direction == "undo" else None, redo=inverse if direction == "redo" else None)
        service.publication.offer_editor_history(workspace.project_id, offered)
        snapshot = session.book.read(AgentQuery(kind="document")).snapshot
        assert snapshot.next_cursor is None
        result = await session.call("project_action", AgentProjectAction(key="history", snapshotId=snapshot.id, action=direction))
        assert result.get("disposition") == "prepared", result
        pending = asyncio.create_task(service.publication.offer(session, result["batchId"]))
        async with asyncio.timeout(2):
            while True:
                batch = run_in(service.store.load(workspace.project_id), session.run.id)[2].batches[0].batch
                if batch.state == "offered": break
                await asyncio.sleep(.01)
        claim = service.publication.claim(workspace.project_id, session.run.id, batch.id, owner)
        saved = service.publication.commit(workspace.project_id, session.run.id, batch.id,
            AgentCommitRequest(owner=owner, ticket=claim.ticket, requestSha256=batch.request_sha256))
        assert saved.receipt.durable and (await pending).durable
        assert block(saved.project.workspace).content[0].text == (block(before).content[0].text if direction == "undo" else "User edit 42")
        assert service.projects.storage.read_committed(workspace.project_id)[0] == saved.project.workspace
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["foreign_session", "read_only", "new_revision"])
async def test_editor_history_offer_cannot_cross_owner_mode_or_revision(fault, tmp_path):
    from packages.resume_core.background_inverse import inverse_mutation
    from packages.resume_core.models.agent import AgentHistoryOffer, AgentOwner
    from tests.recovery.test_agent_publication import manual
    session, service, workspace, _ = tools_setup(tmp_path, message="Undo the latest change.")
    try:
        before = workspace.model_copy(deep=True)
        service.projects.mutate(workspace.project_id, manual(before, value="User edit"))
        current = service.projects.read(workspace.project_id)
        mutation = inverse_mutation(before, current, mutation_id="owner-undo", session_id="foreign" if fault == "foreign_session" else "history_1")
        lease = service.leases.leases[workspace.project_id]
        offered = AgentHistoryOffer(owner=AgentOwner(token=lease.token, epoch=lease.epoch),
            projectRevision=current.project_revision, documentRevision=current.document_revision,
            factsRevision=current.project.facts.revision, undo=mutation, redo=None)
        if fault == "read_only": service.projects.catalog.update(workspace.project_id, read_only=True)
        durable = service.projects.storage.read_committed(workspace.project_id)[0]
        if fault == "new_revision":
            service.publication.offer_editor_history(workspace.project_id, offered)
            with pytest.raises(AgentFailure, match="AGENT_STALE_READ"):
                service.publication.resolve_editor_history(workspace.project_id, lease.epoch, current.project_revision + 1, "undo")
        else:
            with pytest.raises(AgentFailure, match="AGENT_EDIT_INVALID" if fault == "foreign_session" else "AGENT_TOOL_DENIED"):
                service.publication.offer_editor_history(workspace.project_id, offered)
        assert service.projects.storage.read_committed(workspace.project_id)[0] == durable
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_format_template_uses_current_edits_preserves_words_and_is_one_idempotent_mutation(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path)
    try:
        document = workspace.project.document
        roots = [block for region in document.regions for block in region.blocks]
        for region in document.regions:
            region.blocks = []
        document.regions[-1].blocks = roots
        original = next(block for block in document.blocks() if block.type == "paragraph")
        original.content = [StyledText(type="text", text="Current edited wording 42", styles={})]
        words = " ".join(span.text for block in document.blocks() if isinstance(block.content, list)
            for span in block.content if hasattr(span, "text")).split()
        read = session.book.read(AgentQuery(kind="document"))
        assert read.snapshot.next_cursor is None
        request = AgentPrepareRequest(key="format", snapshotIds=[read.snapshot.id],
            operations=[{"kind": "format_template", "snapshotId": read.snapshot.id}])
        result = prepare(session, request)
        assert result.disposition == "prepared"
        journal = run_in(service.store.load(workspace.project_id), session.run.id)[2]
        batch = journal.batches[0].batch
        formatted = apply_rich_mutation(workspace, batch.mutation)[0]
        after = " ".join(span.text for block in formatted.project.document.blocks() if isinstance(block.content, list)
            for span in block.content if hasattr(span, "text")).split()
        from collections import Counter
        assert Counter(words) <= Counter(after)
        assert "Current edited wording 42" in " ".join(after)
        assert prepare(session, request) == result
        assert len(journal.batches) == 1
        assert len(formatted.mutation_replay) == len(workspace.mutation_replay) + 1
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_access_toggle_fences_prepared_commit_and_reenable_does_not_revive_it(tmp_path):
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    try:
        before = service.projects.storage.read_committed(workspace.project_id)[0]
        service.projects.catalog.update(workspace.project_id, read_only=True)
        with pytest.raises(AgentFailure, match="AGENT_TOOL_DENIED"):
            service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        service.projects.catalog.update(workspace.project_id, read_only=False)
        with pytest.raises(AgentFailure, match="AGENT_TOOL_DENIED"):
            service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        assert service.projects.storage.read_committed(workspace.project_id)[0] == before
    finally:
        service.revoke(session.control, "AGENT_CANCELLED")
        await asyncio.gather(offer, return_exceptions=True)
        await session.close()


@pytest.mark.asyncio
async def test_background_proposal_remains_fenced_after_runtime_exit_and_reenable(tmp_path):
    from packages.resume_core.background_store import BackgroundFailure
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from packages.resume_core.models.agent import AgentApplyRequest, AgentReadSnapshot
    from tests.recovery.test_agent_edits import command, replace
    from tests.recovery.test_background_agent import environment, hold_writer
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    hold_writer(service, workspace)
    async def execute(control, _actor):
        session = service.tools.session(control)
        try:
            read = await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"]))
            result = await session.call("prepare_edit_batch", command(replace(
                AgentReadSnapshot.model_validate(read["snapshot"]), "narrative", 0, 6, "Pending")))
            pending = await session.call("apply_edit_batch", AgentApplyRequest(batchId=result["batchId"]))
            assert pending["disposition"] == "waiting_for_sync"
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = execute
    try:
        job, _ = await service.submit(workspace.project_id, payload)
        await factory.actor(job)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        proposal = service.store.load(workspace.project_id).proposals[0]
        before = service.projects.storage.read_committed(workspace.project_id)[0]
        for read_only in (True, False):
            service.projects.catalog.update(workspace.project_id, read_only=read_only)
            with pytest.raises(BackgroundFailure, match="DEPENDENCY_CHANGED"):
                service.publication.publish(workspace.project_id, job.id, proposal.payload_sha256)
            assert service.projects.storage.read_committed(workspace.project_id)[0] == before
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_assistant_undo_and_redo_use_guarded_canonical_history_and_saved_receipts(tmp_path):
    from packages.resume_core.background_history import digest_bytes
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from packages.resume_core.models.agent import AgentProjectAction, AgentApplyRequest
    from tests.recovery.test_background_agent import environment
    from tests.recovery.test_background_inverse import mutation, put, block
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    original = block(workspace, "narrative").content[0].text
    results = []
    changed, _ = service.publisher.manual(workspace.project_id,
        mutation(workspace, [put(workspace, "narrative", text="Changed by user")], "manual-before-undo"),
        originals=service.projects.originals, artifacts=service.projects.artifacts, images=service.projects.images)
    service.publication.adopt(workspace.project_id, changed, digest_bytes(changed))
    try:
        for epoch, direction, expected in [(1, "undo", original), (2, "redo", "Changed by user")]:
            current = service.projects.storage.read_committed(workspace.project_id)[0]
            request = payload.model_copy(deep=True)
            request.request_epoch = payload.request_epoch
            request.request.client_request_id = "history_" + direction
            request.request.message = direction.title() + " the latest change."
            request.request.project_revision, request.request.document_revision = current.project_revision, current.document_revision
            request.request.facts_revision = current.project.facts.revision
            async def execute(control, _actor):
                session = service.tools.session(control)
                try:
                    query = AgentQuery(kind="document")
                    page = session.book.read(query)
                    while page.snapshot.next_cursor:
                        page = session.book.read(query.model_copy(update={"cursor": page.snapshot.next_cursor}))
                    prepared = await session.call("project_action", AgentProjectAction(key="history", snapshotId=page.snapshot.id, action=direction))
                    results.append(prepared)
                    assert prepared.get("disposition") == "prepared", prepared
                    result = await session.call("apply_edit_batch", AgentApplyRequest(batchId=prepared["batchId"]))
                    results.append(result)
                    assert result.get("durable") is True, result
                    return ExecutionOutcome(finished_at=service.supervisor.clock.now())
                finally:
                    await session.close()
            factory.callbacks[request.request.client_request_id] = execute
            job, _ = await service.submit(workspace.project_id, request)
            await factory.actor(job)
            await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
            assert block(service.projects.storage.read_committed(workspace.project_id)[0], "narrative").content[0].text == expected, results
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_background_format_saves_more_than_100_blocks_with_a_bounded_receipt(tmp_path):
    from packages.resume_core.background_history import digest_bytes
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from packages.resume_core.models.agent import AgentApplyRequest
    from tests.recovery.test_background_agent import environment
    from tests.recovery.test_background_inverse import mutation
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    region = workspace.project.document.regions[-1]
    blocks = [ParagraphBlock(id=f"long_{index}", revision=1, type="paragraph", props={},
        content=[StyledText(type="text", text=f"MARKER_{index}:" + "Длинный текст " * 80, styles={})],
        children=[], provenance=[]) for index in range(137)]
    previous, steps = region.blocks[-1].id, []
    for block in blocks:
        steps.append({"kind": "put_block", "parentId": region.id, "afterId": previous,
            "beforeRevision": None, "block": block.model_dump(by_alias=True)})
        previous = block.id
    current, _ = service.publisher.manual(workspace.project_id, mutation(workspace, steps, "long-input"),
        originals=service.projects.originals, artifacts=service.projects.artifacts, images=service.projects.images)
    service.publication.adopt(workspace.project_id, current, digest_bytes(current))
    payload.request.project_revision, payload.request.document_revision = current.project_revision, current.document_revision
    payload.request.facts_revision = current.project.facts.revision
    results = []
    async def execute(control, _actor):
        session = service.tools.session(control)
        try:
            query = AgentQuery(kind="document")
            page = await session.call("get_resume_context", query)
            while page["snapshot"]["nextCursor"]:
                page = await session.call("get_resume_context", query.model_copy(update={"cursor": page["snapshot"]["nextCursor"]}))
            prepared = await session.call("prepare_edit_batch", AgentPrepareRequest(key="format-long", snapshotIds=[page["snapshot"]["id"]],
                operations=[{"kind": "format_template", "snapshotId": page["snapshot"]["id"]}]))
            results.append(prepared)
            assert prepared.get("disposition") == "prepared", prepared
            saved = await session.call("apply_edit_batch", AgentApplyRequest(batchId=prepared["batchId"]))
            results.append(saved)
            assert saved.get("schemaVersion") == 3 and saved.get("durable"), saved
            assert len(json.dumps(saved).encode()) <= 4096
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = execute
    try:
        job, _ = await service.submit(workspace.project_id, payload)
        await factory.actor(job)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 30)
        saved = service.store.read(workspace.project_id, job.id)
        assert saved.receipt is not None, results
        document = service.projects.storage.read_committed(workspace.project_id)[0].project.document
        text = " ".join(span.text for block in document.blocks() if isinstance(block.content, list)
            for span in block.content if hasattr(span, "text"))
        for index in range(137):
            assert text.count(f"MARKER_{index}:") == 1
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_typed_sections_tables_and_retained_assets_share_one_validated_batch(tmp_path):
    from io import BytesIO
    from PIL import Image
    from packages.resume_core.rich_images import normalize_image
    session, service, workspace, _ = tools_setup(tmp_path)
    try:
        image = BytesIO(); Image.new("RGB", (3, 2), "red").save(image, format="PNG")
        asset, data = normalize_image(image.getvalue(), "retained")
        workspace.project.assets.append(asset)
        service.projects.images[(workspace.project_id, asset.id)] = data
        service.projects.persist(workspace.project_id)
        read = session.book.read(AgentQuery(kind="document"))
        destination = {"snapshotId": read.snapshot.id, "parentId": "main", "afterId": None}
        inside = {**destination, "parentId": "new_section"}
        request = AgentPrepareRequest(key="typed-structure", snapshotIds=[read.snapshot.id], operations=[
            {"kind": "insert_blocks", "destination": destination, "blocks": [{"key": "new_section", "kind": "section", "content": [{"text": "Evidence table"}]}]},
            {"kind": "insert_table", "destination": inside, "rows": [["Tool", "Evidence"], ["Python", "42"]]},
            {"kind": "insert_asset", "destination": inside, "assetId": asset.id, "alt": "Retained asset", "width": 30, "height": 20}])
        result = prepare(session, request)
        assert result.disposition == "prepared"
        journal = run_in(service.store.load(workspace.project_id), session.run.id)[2]
        changed = apply_rich_mutation(workspace, journal.batches[0].batch.mutation)[0]
        section = next(block for block in changed.project.document.blocks() if block.type == "section" and block.id not in {old.id for old in workspace.project.document.blocks()})
        assert {block.type for block in section.children} == {"table", "image"}
        assert changed.project.facts == workspace.project.facts and changed.project.sources == workspace.project.sources
        assert len(changed.mutation_replay) == len(workspace.mutation_replay) + 1
    finally:
        await session.close()
