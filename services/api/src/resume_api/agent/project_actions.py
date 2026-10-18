"""Bound project operations reuse domain stores and the captured edit authority."""

import base64
import hashlib
import json
import re

from packages.resume_core.agent_store import AgentFailure, digest, run_in
from packages.resume_core.dates import partial_date
from packages.resume_core.gui_normalization import canonical_source
from packages.resume_core.project_catalog import AccessChanged
from packages.resume_core.rich_images import normalize_image
from packages.resume_core.rich_limits import retained_image_bytes, ImageReferences
from packages.resume_core.storage import atomic_write, private_directory
from resume_api.extracting import run_extract
from resume_api.lifecycle import OperationFiles


def owned_projects(session):
    projects = session.service.projects
    return getattr(projects, "projects", projects)


async def project_action(session, request):
    projects, project_id = owned_projects(session), session.control.project_id
    session.write_guard()
    if request.action in {"undo", "redo"}:
        from .edits import prepare
        from packages.resume_core.models.agent import AgentPrepareRequest
        return prepare(session, AgentPrepareRequest(key=request.key, snapshotIds=[request.snapshot_id],
            operations=[{"kind": "history", "snapshotId": request.snapshot_id, "direction": request.action}]))
    capture = session.book.require(request.snapshot_id, kind="resources")
    key = digest([project_id, session.control.run_id, request.key])
    checksum = digest(request)
    prior = projects.catalog.actions().get(key)
    if prior is not None:
        if prior["payloadSha256"] != checksum:
            raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
        return prior["result"]
    with projects.state_lock:
        session.guard()
        workspace = projects.read(project_id).model_copy(deep=True)
        if workspace.project_revision != capture.workspace.project_revision:
            raise AgentFailure("AGENT_STALE_READ")
        actions = projects.catalog.actions().values()
        if any(action["runId"] == session.control.run_id for action in actions):
            raise AgentFailure("AGENT_EDIT_LIMIT")
        raw_message = run_in(session.service.store.load(project_id), session.control.run_id)[2].request.message
        message = raw_message.casefold()
        commands = {"archive": ("архив", "archive"), "restore": ("восстанов", "верни", "restore"),
            "delete": ("удал", "delete"), "remove_source": ("удал", "remove", "delete"),
            "remove_asset": ("удал", "remove", "delete")}
        if request.action in commands and not any(word in message for word in commands[request.action]):
            raise AgentFailure("AGENT_TOOL_DENIED")
        if request.action == "delete" and not re.search(
                r"(?:удал\w*\s+(?:этот\s+)?(?:проект|резюме)|delete\s+(?:(?:this|the)\s+)?(?:project|resume))", message):
            raise AgentFailure("AGENT_TOOL_DENIED")
        if request.action == "add_source_text" and request.value not in raw_message:
            raise AgentFailure("AGENT_EVIDENCE_INVALID")
    source, asset, blob, extension = None, None, None, None
    if request.action == "add_source_text":
        if not request.value.strip():
            raise AgentFailure("AGENT_ARGUMENT_INVALID")
        blob = request.value.encode()
        source_id = "source_" + key[:32]
        files = OperationFiles(projects.temp_root)
        with files.open():
            result = await run_extract(blob, "assistant-source.txt", True, files)
        source = canonical_source(result, source_id=source_id)
    elif request.action == "import_asset":
        asset, blob = normalize_image(base64.b64decode(request.value, validate=True), "asset_" + key[:32])
    elif request.action in {"export_docx", "export_project"}:
        images = {aid: data for (pid, aid), data in projects.images.items() if pid == project_id}
        if request.action == "export_docx":
            files = OperationFiles(projects.temp_root)
            with files.open():
                blob = await projects.renderer.render(workspace.project.document, images, files, workspace.project.facts)
            extension = "docx"
        else:
            blob = projects._portable(project_id, workspace,
                {sid: data for (pid, sid), data in projects.originals.items() if pid == project_id}, images)
            extension = "foldcv"
    try:
        with projects.state_lock, projects.catalog.authority(project_id, session.run.access_revision):
            session.guard()
            current = projects.read(project_id)
            if current.project_revision != workspace.project_revision:
                raise AgentFailure("AGENT_STALE_READ")
            result = {"action": request.action, "projectId": project_id, "durable": True}
            status = "completed"
            if extension:
                checksum_bytes = hashlib.sha256(blob).hexdigest()
                folder = private_directory(projects.storage._directory(project_id) / "renders")
                target = folder / (checksum_bytes + ".docx" if extension == "docx" else checksum_bytes + ".foldcv")
                atomic_write(target, blob)
                result.update(sha256=checksum_bytes, bytes=len(blob),
                    downloadUrl=f"/v1/rich/projects/{project_id}/assistant/exports/{checksum_bytes}.{extension}")
            elif request.action in {"archive", "restore"}:
                projects.archive_entry(project_id, request.action == "archive")
            elif request.action == "delete":
                status = "pending"
                result.update(durable=False, durableIntent=True, disposition="after_turn_cleanup")
            else:
                updated = current.model_copy(deep=True)
                if request.action == "rename":
                    if not request.value.strip():
                        raise AgentFailure("AGENT_ARGUMENT_INVALID")
                    updated.title, updated.title_manually_set = request.value.strip(), True
                elif request.action == "formatting_date":
                    updated.formatting_as_of = partial_date(request.value)
                elif source is not None:
                    updated.project.sources.append(source)
                    projects.originals[(project_id, source.id)] = blob
                    result.update(sourceId=source.id)
                elif asset is not None:
                    updated.project.assets.append(asset)
                    retained_image_bytes(updated.project.assets,
                        ImageReferences(durable=tuple(item.id for item in updated.project.assets)))
                    projects.images[(project_id, asset.id)] = blob
                    result.update(assetId=asset.id)
                elif request.action == "remove_source":
                    if not any(item.id == request.target_id for item in updated.project.sources):
                        raise AgentFailure("AGENT_NOT_FOUND")
                    evidence = json.dumps({"document": updated.project.document.model_dump(by_alias=True),
                        "facts": updated.project.facts.model_dump(by_alias=True)}, separators=(",", ":"))
                    if json.dumps(request.target_id) in evidence:
                        raise AgentFailure("AGENT_EVIDENCE_INVALID")
                    updated.project.sources = [item for item in updated.project.sources if item.id != request.target_id]
                    updated.project.import_coverage = [item for item in updated.project.import_coverage if item.source_id != request.target_id]
                elif request.action == "remove_asset":
                    if not any(item.id == request.target_id for item in updated.project.assets):
                        raise AgentFailure("AGENT_NOT_FOUND")
                    refs = projects.image_references(project_id)
                    if request.target_id in {*refs.live, *refs.history, *refs.in_flight}:
                        raise AgentFailure("AGENT_EVIDENCE_INVALID")
                    updated.project.assets = [item for item in updated.project.assets if item.id != request.target_id]
                updated.project_revision += 1
                updated.project.revision = updated.project_revision
                updated.updated_at = projects.clock().isoformat()
                projects.workspaces[project_id] = updated
                if projects.persist(project_id) != "durable":
                    raise AgentFailure("AGENT_SAVE_FAILED")
                result.update(projectRevision=updated.project_revision)
            projects.catalog.record_action(key, {"projectId": project_id, "runId": session.control.run_id,
                "key": request.key, "action": request.action, "accessRevision": session.run.access_revision,
                "projectRevision": current.project_revision,
                "payloadSha256": checksum, "status": status, "result": result})
            return result
    except AccessChanged:
        raise AgentFailure("AGENT_TOOL_DENIED") from None
