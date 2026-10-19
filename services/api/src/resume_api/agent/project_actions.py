"""Bound project operations reuse domain stores and the captured edit authority."""

import base64
import hashlib
import json
import re

from packages.resume_core.agent_store import AgentFailure, digest, run_in
from packages.resume_core.dates import partial_date
from packages.resume_core.gui_normalization import canonical_source
from packages.resume_core.project_catalog import AccessChanged
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.models.rich_workspace import RichMutationReplay
from packages.resume_core.rich_images import normalize_image
from packages.resume_core.rich_limits import retained_image_bytes, ImageReferences
from packages.resume_core.storage import StorageFailure, atomic_write, private_directory
from .project_action_recovery import reconcile_action, recover_actions
from resume_api.extracting import run_extract
from resume_api.lifecycle import OperationFiles


def owned_projects(session):
    projects = session.service.projects
    return getattr(projects, "projects", projects)


async def project_action(session, request):
    projects, project_id = owned_projects(session), session.control.project_id
    key = digest([project_id, session.control.run_id, request.key])
    checksum = digest(request)
    if project_id in projects.catalog_recovery_fences:
        recover_actions(projects)
    prior = projects.catalog.actions(synchronize=True).get(key)
    if prior is not None:
        if prior["payloadSha256"] != checksum:
            raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
        if prior["status"] == "applying":
            return reconcile_action(projects, key, prior)
        return prior["result"]
    session.write_guard()
    if session.run.scope.kind != "resume":
        raise AgentFailure("AGENT_SCOPE_INVALID")
    if request.action in {"undo", "redo"}:
        from .edits import prepare
        from packages.resume_core.models.agent import AgentPrepareRequest
        return prepare(session, AgentPrepareRequest(key=request.key, snapshotIds=[request.snapshot_id],
            operations=[{"kind": "history", "snapshotId": request.snapshot_id, "direction": request.action}]))
    capture = session.book.require(request.snapshot_id, kind="resources")
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
            prior = projects.catalog.actions().get(key)
            if prior is not None:
                if prior["payloadSha256"] != checksum:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                return reconcile_action(projects, key, prior) if prior["status"] == "applying" else prior["result"]
            session.guard()
            session.write_guard()
            current = projects.read(project_id)
            if current.project_revision != workspace.project_revision:
                raise AgentFailure("AGENT_STALE_READ")
            if any(action["runId"] == session.control.run_id for action in projects.catalog.actions().values()):
                raise AgentFailure("AGENT_EDIT_LIMIT")
            result = {"action": request.action, "projectId": project_id, "durable": True}
            command = {"projectId": project_id, "runId": session.control.run_id, "key": request.key,
                "action": request.action, "accessRevision": session.run.access_revision,
                "projectRevision": current.project_revision, "payloadSha256": checksum, "status": "applying", "result": result}
            if extension:
                checksum_bytes = hashlib.sha256(blob).hexdigest()
                folder = private_directory(projects.storage._directory(project_id) / "renders")
                target = folder / (checksum_bytes + ".docx" if extension == "docx" else checksum_bytes + ".foldcv")
                result.update(sha256=checksum_bytes, bytes=len(blob),
                    downloadUrl=f"/v1/rich/projects/{project_id}/assistant/exports/{checksum_bytes}.{extension}")
                command.update(commitKind="file", fileName=target.name)
                projects.catalog.reserve_action(key, command)
                try:
                    atomic_write(target, blob)
                except (StorageFailure, OSError):
                    pass
                return reconcile_action(projects, key, command)
            elif request.action in {"archive", "restore"}:
                projects.catalog.archive_action(project_id, request.action == "archive", key, {**command, "status": "completed"})
                return result
            elif request.action == "delete":
                result.update(durable=False, durableIntent=True, disposition="after_turn_cleanup")
                projects.catalog.reserve_action(key, {**command, "status": "pending"})
                return result
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
                    result.update(sourceId=source.id)
                elif asset is not None:
                    updated.project.assets.append(asset)
                    retained_image_bytes(updated.project.assets,
                        ImageReferences(durable=tuple(item.id for item in updated.project.assets)))
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
                proof_id = "catalog_" + key
                updated.mutation_replay.append(RichMutationReplay(clientMutationId=proof_id,
                    requestSha256=checksum, resultingRevision=updated.project_revision))
                _before, before_sha256 = projects.storage.read_committed(project_id)
                result.update(projectRevision=updated.project_revision)
                command.update(commitKind="workspace", proofId=proof_id, beforeSha256=before_sha256)
                projects.catalog.reserve_action(key, command)
                originals, images = dict(projects.originals), dict(projects.images)
                if source is not None:
                    projects.originals[(project_id, source.id)] = blob
                if asset is not None:
                    projects.images[(project_id, asset.id)] = blob
                projects.workspaces[project_id] = updated
                try:
                    projects.persist(project_id)
                except (ProjectStoreFailure, StorageFailure, OSError):
                    pass
                result = reconcile_action(projects, key, command)
                retained, retained_sha256 = projects.storage.read_committed(project_id)
                projects.adopt_committed(project_id, retained, retained_sha256)
                if not result.get("durable"):
                    projects.originals, projects.images = originals, images
                return result
    except AccessChanged:
        raise AgentFailure("AGENT_TOOL_DENIED") from None
    except (ProjectStoreFailure, StorageFailure, OSError):
        try:
            retained = projects.catalog.actions(synchronize=True).get(key)
        except (ProjectStoreFailure, StorageFailure, OSError):
            retained = None
            projects.catalog_recovery_fences.add(project_id)
            raise AgentFailure("AGENT_OUTCOME_UNKNOWN") from None
        if retained is not None and retained["status"] in {"completed", "failed", "pending"}:
            return retained["result"]
        if retained is not None and retained["status"] == "applying":
            # A reservation may have reached disk before its writer reported failure.
            return reconcile_action(projects, key, retained)
        if project_id in projects.catalog_recovery_fences:
            projects.catalog_recovery_fences.add(project_id)
            raise AgentFailure("AGENT_OUTCOME_UNKNOWN") from None
        raise AgentFailure("AGENT_SAVE_FAILED") from None
