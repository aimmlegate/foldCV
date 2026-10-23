"""Writer control stays separate from inference admission and runtime ownership."""

import asyncio

from ..template_responses import wire_response

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.background import (WriterAbandonV1, WriterAdvanceV1, WriterBarrierAckV1,
    WriterBarrierCommandV1, WriterCheckpointV1, WriterDraftCommandV1, WriterDraftReferenceV1, WriterMutationV1,
    WriterOpenV1, WriterProofV1, WriterPublicationV1, WriterPublishV1, WriterHistoryRequestV1, WriterHistoryCommandV1,
    WriterDraftResolveV1)
from packages.resume_core.models.template_writer import (WriterAdvanceV2, WriterBarrierAckV2, WriterCheckpointV2,
    WriterDraftResolveV2, WriterMutationV2, WriterLocalHistoryCommandV2, WriterPrepareEditV2,
    WriterCaptureClipboardV2, WriterReleaseClipboardV2, WriterRewritePreviewV2, WriterRewriteCancelV2,
    TemplateRewritePreviewV1, WriterRewriteCancelResultV2)


def mount_writers(app, service):
    prefix = "/v1/rich/projects/{project_id}/writer"

    async def call(project, method, payload=None):
        if not service.enabled:
            raise BackgroundFailure("JOB_DISABLED")
        function = getattr(service.writers, method)
        if method == "abandon":
            def abandon():
                with service.projects.state_lock:
                    previous = service.store.load(project).writer
                    result = function(project, payload)
                    if previous is not None:
                        session = service.projects.image_sessions.get((project, previous.incarnation))
                        if session is not None:
                            session.closed = True
                    return result
            result = await asyncio.to_thread(abandon)
        else:
            result = await asyncio.to_thread(function, project, *([] if payload is None else [payload]))
        if method in {"detach", "abandon", "restore_saved_draft", "discard_draft", "pending_input_draft", "reconcile"}:
            service.wake_publication(project)
        return wire_response(result)

    @app.get(prefix)
    async def bootstrap(project_id: str):
        if not service.enabled:
            raise BackgroundFailure("JOB_DISABLED")
        def read():
            service.store.open(project_id)
            try:
                service.publisher.recover(project_id)
            except BackgroundFailure as error:
                if error.code != "OUTCOME_UNKNOWN":
                    raise
            with service.writers.guard(project_id, uncertain=True) as (directory, state, workspace, checksum):
                service.writers.ensure(state, workspace)
                service.writers.write(directory, state)
                return service.writers.view(state, workspace, checksum)
        result = await asyncio.to_thread(read)
        return wire_response(result)

    @app.post(prefix + "/open")
    async def open_writer(project_id: str, payload: WriterOpenV1):
        return await call(project_id, "open", payload)

    @app.post(prefix + "/heartbeat")
    async def heartbeat(project_id: str, payload: WriterProofV1):
        return await call(project_id, "heartbeat", payload)

    @app.post(prefix + "/read")
    async def read(project_id: str, payload: WriterProofV1):
        return await call(project_id, "read_snapshot", payload)

    @app.post(prefix + "/suspend")
    async def suspend(project_id: str, payload: WriterProofV1):
        return await call(project_id, "suspend", payload)

    @app.post(prefix + "/flush")
    async def flush(project_id: str, payload: WriterAdvanceV1 | WriterAdvanceV2):
        return await call(project_id, "flush", payload)

    @app.post(prefix + "/reconcile")
    async def reconcile(project_id: str, payload: WriterAdvanceV1 | WriterAdvanceV2):
        return await call(project_id, "reconcile", payload)

    @app.post(prefix + "/detach")
    async def detach(project_id: str, payload: WriterAdvanceV1 | WriterAdvanceV2):
        return await call(project_id, "detach", payload)

    @app.post(prefix + "/barrier")
    async def barrier(project_id: str, payload: WriterBarrierAckV1 | WriterBarrierAckV2):
        return await call(project_id, "barrier", payload)

    @app.post(prefix + "/revoke")
    async def revoke(project_id: str, payload: WriterBarrierCommandV1):
        return await call(project_id, "revoke", payload)

    @app.post(prefix + "/checkpoint")
    async def checkpoint(project_id: str, payload: WriterCheckpointV1 | WriterCheckpointV2):
        return await call(project_id, "checkpoint", payload)

    @app.post(prefix + "/draft/read")
    async def draft(project_id: str, payload: WriterDraftReferenceV1):
        return await call(project_id, "read_draft", payload)

    @app.post(prefix + "/draft/discard")
    async def discard(project_id: str, payload: WriterDraftCommandV1):
        return await call(project_id, "discard_draft", payload)

    @app.post(prefix + "/draft/recover")
    async def recover(project_id: str, payload: WriterDraftCommandV1):
        return await call(project_id, "restore_saved_draft", payload)

    @app.post(prefix + "/draft/pending-input")
    async def pending_input(project_id: str, payload: WriterDraftCommandV1):
        return await call(project_id, "pending_input_draft", payload)

    @app.post(prefix + "/abandon")
    async def abandon(project_id: str, payload: WriterAbandonV1):
        return await call(project_id, "abandon", payload)

    @app.post(prefix + "/draft/use")
    async def use_draft(project_id: str, payload: WriterDraftResolveV1 | WriterDraftResolveV2):
        if not service.enabled:
            raise BackgroundFailure("JOB_DISABLED")
        def commit():
            view = service.writers.use_draft(project_id, payload, originals=service.projects.originals,
                artifacts=service.projects.artifacts, images=service.projects.images)
            with service.projects.state_lock:
                service.publication.adopt(project_id, view.workspace, view.workspace_sha256)
            return view
        result = await asyncio.to_thread(commit)
        return wire_response(result)

    @app.post(prefix + "/history/offer")
    async def history_offer(project_id: str, payload: WriterHistoryRequestV1):
        return await call(project_id, "history_offer", payload)

    @app.post(prefix + "/history/begin")
    async def history_begin(project_id: str, payload: WriterHistoryRequestV1):
        return await call(project_id, "begin_history_transfer", payload)

    @app.post(prefix + "/history/ack")
    async def history_ack(project_id: str, payload: WriterHistoryRequestV1):
        return await call(project_id, "acknowledge_history_transfer", payload)

    @app.post(prefix + "/history/command")
    async def history_command(project_id: str, payload: WriterHistoryCommandV1):
        if not service.enabled:
            raise BackgroundFailure("JOB_DISABLED")
        def commit():
            result = service.writers.history_command(project_id, payload, originals=service.projects.originals,
                artifacts=service.projects.artifacts, images=service.projects.images)
            with service.projects.state_lock:
                service.publication.adopt(project_id, result.view.workspace, result.view.workspace_sha256)
            return result
        result = await asyncio.to_thread(commit)
        job = service.store.read(project_id, payload.job_id)
        await service.supervisor._emit(job)
        return wire_response(result)

    @app.post(prefix + "/save")
    async def save(project_id: str, payload: WriterMutationV1 | WriterMutationV2):
        if not service.enabled:
            raise BackgroundFailure("JOB_DISABLED")
        def commit():
            view = service.writers.save(project_id, payload, originals=service.projects.originals,
                artifacts=service.projects.artifacts, images=service.projects.images)
            with service.projects.state_lock:
                current = (service.writers.read_snapshot(project_id, payload.proof)
                    if isinstance(payload, WriterMutationV2) and payload.response_mode == 'prepared_delta' else view)
                service.publication.adopt(project_id, current.workspace, current.workspace_sha256)
            return view
        result = await asyncio.to_thread(commit)
        return wire_response(result)

    @app.post(prefix + '/prepare')
    async def prepare_edit(project_id: str, payload: WriterPrepareEditV2):
        return await call(project_id, 'prepare_edit', payload)

    @app.post(prefix + '/clipboard/capture')
    async def capture_clipboard(project_id: str, payload: WriterCaptureClipboardV2):
        return await call(project_id, 'capture_clipboard', payload)

    @app.post(prefix + '/clipboard/release')
    async def release_clipboard(project_id: str, payload: WriterReleaseClipboardV2):
        return await call(project_id, 'release_clipboard', payload)

    @app.post(prefix + '/rewrite/preview')
    async def rewrite_preview(project_id: str, payload: WriterRewritePreviewV2):
        # Generation reads verified text and changes nothing; Apply is an ordinary prepared edit.
        generate = getattr(service.projects, 'template_rewrite_text', None)
        if not service.enabled or generate is None:
            raise BackgroundFailure('JOB_DISABLED')
        source = await asyncio.to_thread(service.writers.rewrite_source, project_id, payload)
        text = await generate(project_id, payload.request_id, payload.instruction, source)
        return wire_response(TemplateRewritePreviewV1(schemaVersion=1, requestId=payload.request_id,
            snapshot=payload.snapshot, range=payload.range, source=source, text=text))

    @app.post(prefix + '/rewrite/cancel')
    async def rewrite_cancel(project_id: str, payload: WriterRewriteCancelV2):
        cancel = getattr(service.projects, 'template_rewrite_cancel', None)
        if not service.enabled or cancel is None:
            raise BackgroundFailure('JOB_DISABLED')
        await asyncio.to_thread(service.writers.read_snapshot, project_id, payload.proof)
        return wire_response(WriterRewriteCancelResultV2(schemaVersion=2, requestId=payload.request_id,
            cancelled=cancel(project_id, payload.request_id)))

    @app.post(prefix + '/prepare-delta')
    async def prepare_edit_delta(project_id: str, payload: WriterPrepareEditV2):
        return await call(project_id, 'prepare_edit_delta', payload)

    @app.post(prefix + '/history/local')
    async def local_history(project_id: str, payload: WriterLocalHistoryCommandV2):
        if not service.enabled:
            raise BackgroundFailure('JOB_DISABLED')
        def commit():
            view = service.writers.local_history_command(project_id, payload, originals=service.projects.originals,
                artifacts=service.projects.artifacts, images=service.projects.images)
            with service.projects.state_lock:
                service.publication.adopt(project_id, view.workspace, view.workspace_sha256)
            return view
        result = await asyncio.to_thread(commit)
        return wire_response(result)

    @app.post(prefix + "/publish")
    async def publish(project_id: str, payload: WriterPublishV1):
        if not service.enabled:
            raise BackgroundFailure("JOB_DISABLED")
        known = await asyncio.to_thread(service.store.read, project_id, payload.job_id)
        claim = None if known.receipt is not None else await asyncio.to_thread(service.writers.publication_claim, project_id, payload)
        job = await asyncio.to_thread(service.publication.publish, project_id, payload.job_id,
            payload.proposal_sha256, expected_claim=claim, approved=payload.approve)
        await service.supervisor._emit(job)
        view = await asyncio.to_thread(service.writers.read_snapshot, project_id, payload.proof)
        result = WriterPublicationV1(schemaVersion=1, job=job, view=view)
        return wire_response(result)
