"""Pure project-action candidates shared by preparation and existing execution."""

import json
import base64
import hashlib

from .agent_store import AgentFailure, digest
from .assistant_proposals import content_digest
from .dates import partial_date
from .rich_limits import ImageReferences, retained_image_bytes


def action_content_digest(workspace):
    return digest({"format": "assistant-project-content-v1", "content": content_digest(workspace),
        "title": workspace.title, "titleManuallySet": workspace.title_manually_set,
        "formattingAsOf": workspace.formatting_as_of.model_dump(mode="json", by_alias=True)})


def action_baseline_digest(workspace, archived):
    return digest({"projectId": workspace.project_id, "content": action_content_digest(workspace), "archived": archived})


def action_proposal_digest(action, candidate):
    if (action.blob_base64 is None) != (action.blob_sha256 is None):
        raise ValueError("resource bytes need an exact digest")
    if action.blob_base64 is not None and hashlib.sha256(base64.b64decode(action.blob_base64, validate=True)).hexdigest() != action.blob_sha256:
        raise ValueError("resource bytes changed")
    return digest({"format": "assistant-project-action-v1", "request": action.request.model_dump(mode="json", by_alias=True,
        exclude={"key", "snapshot_id"}), "candidate": action_content_digest(candidate) if candidate else None,
        "archivedBefore": action.archived_before, "archivedAfter": action.archived_after,
        "blobSha256": action.blob_sha256, "preview": action.preview.model_dump(mode="json", by_alias=True)})


def workspace_action_candidate(workspace, request, *, source=None, asset=None, image_references=None):
    updated, result = workspace.model_copy(deep=True), {}
    if request.action == "rename":
        if not request.value.strip():
            raise AgentFailure("AGENT_ARGUMENT_INVALID")
        updated.title, updated.title_manually_set = request.value.strip(), True
    elif request.action == "formatting_date":
        try:
            updated.formatting_as_of = partial_date(request.value)
        except ValueError:
            raise AgentFailure("AGENT_ARGUMENT_INVALID") from None
    elif request.action == "add_source_text" and source is not None:
        updated.project.sources.append(source.model_copy(deep=True))
        result["sourceId"] = source.id
    elif request.action == "import_asset" and asset is not None:
        updated.project.assets.append(asset.model_copy(deep=True))
        retained_image_bytes(updated.project.assets, ImageReferences(durable=tuple(item.id for item in updated.project.assets)))
        result["assetId"] = asset.id
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
        if image_references is None or request.target_id in {
                *image_references.live, *image_references.history, *image_references.in_flight}:
            raise AgentFailure("AGENT_EVIDENCE_INVALID")
        updated.project.assets = [item for item in updated.project.assets if item.id != request.target_id]
    else:
        raise AgentFailure("AGENT_ARGUMENT_INVALID")
    return updated, result


def lifecycle_preview(workspace, request, *, archived):
    target = f"«{workspace.title}» ({workspace.project_id})"
    if request.action == "delete":
        if request.target_id != workspace.project_id:
            raise AgentFailure("AGENT_ARGUMENT_INVALID")
        return target, "Удалён", f"Удалить проект {target}. Локальные файлы будут удалены окончательно. Отмены в редакторе нет."
    if request.action in {"archive", "restore"}:
        destination = "В архиве" if request.action == "archive" else "В списке проектов"
        before = "В архиве" if archived else "В списке проектов"
        reason = f"Проект {target}: {before} → {destination}. Это действие не входит в историю текста; его можно обратить через список проектов."
        return before, destination, reason
    raise AgentFailure("AGENT_ARGUMENT_INVALID")
