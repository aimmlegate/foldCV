"""Prepare one exact project action without changing canonical content or history."""

import base64
import hashlib

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_store import AgentFailure, digest, run_in
from packages.resume_core.assistant_actions import action_baseline_digest, action_content_digest, action_proposal_digest, lifecycle_preview, workspace_action_candidate
from packages.resume_core.assistant_proposals import POLICY_REVISION, VERSION_COUNT, expiry
from packages.resume_core.gui_normalization import canonical_source
from packages.resume_core.models.assistant_actions import AssistantProjectActionPayloadV1, AssistantProjectActionPreviewV1, AssistantStoredActionV1
from packages.resume_core.models.assistant_proposals import AssistantChangeV1, AssistantCoverageV1, AssistantProposalV1
from packages.resume_core.rich_images import ImageFailure, normalize_image

from .proposals import result

ACTION_TASKS = {"rename": "project_metadata", "formatting_date": "project_metadata", "add_source_text": "sources",
    "remove_source": "sources", "import_asset": "images", "remove_asset": "images", "archive": "archive_project",
    "restore": "restore_project", "delete": "delete_project"}


def date_label(value):
    return "-".join([str(value.year), *([f"{value.month:02d}"] if value.month is not None else []),
        *([f"{value.day:02d}"] if value.day is not None else [])])


def comparison(workspace, request, candidate, archived):
    if request.action in {"archive", "restore", "delete"}:
        return lifecycle_preview(workspace, request, archived=archived)
    if request.action == "rename":
        before = workspace.title + ("\nНазвание закреплено пользователем." if workspace.title_manually_set else "\nНазвание выбрано автоматически.")
        return before, candidate.title + "\nНазвание закреплено пользователем.", "Изменить название проекта. Текст и факты сохраняются. Название можно изменить снова через свойства проекта."
    if request.action == "formatting_date":
        return date_label(workspace.formatting_as_of), date_label(candidate.formatting_as_of), "Изменить дату оформления. Текущие факты и их точность сохраняются. Дату можно изменить через свойства проекта."
    if request.action == "add_source_text":
        return "Исходник отсутствует", request.value, "Добавить показанный текст как исходник проекта. Текущие текст и факты сохраняются. В истории текста отмены этого действия нет."
    if request.action == "remove_source":
        source = next(source for source in workspace.project.sources if source.id == request.target_id)
        return source.original_name + " (" + source.id + ")", "Исходник удалён", "Удалить указанный исходник. Для возврата потребуется добавить его снова. Текущие текст и факты сохраняются. В истории текста отмены этого действия нет."
    if request.action == "import_asset":
        asset = next(asset for asset in candidate.project.assets if asset.id not in {item.id for item in workspace.project.assets})
        return "Изображение отсутствует", f"{asset.mime_type}, {asset.width} × {asset.height}", "Добавить показанное изображение в ресурсы проекта. Оно станет доступным для вставки в редакторе. В истории текста отмены этого действия нет."
    asset = next(asset for asset in workspace.project.assets if asset.id == request.target_id)
    return f"{asset.id}: {asset.mime_type}, {asset.width} × {asset.height}", "Изображение удалено", "Удалить указанное неиспользуемое изображение из ресурсов проекта. Для возврата потребуется добавить его снова. В истории текста отмены этого действия нет."


async def prepare_action(session, wrapper):
    service = getattr(session.service, "catalog_service", session.service)
    request, project = wrapper.request, session.control.project_id
    if len(wrapper.model_dump_json(by_alias=True).encode()) > limits.TOOL_BYTES:
        raise AgentFailure("AGENT_TOOL_LIMIT")
    task = ACTION_TASKS.get(request.action)
    if not getattr(service, "assistant_protocol_enabled", False) or task is None or task != session.planned_task:
        raise AgentFailure("AGENT_TOOL_DENIED")
    with service.projects.state_lock:
        session.guard()
        capture = session.book.require(request.snapshot_id, kind="resources")
        workspace = session.service.projects.read(project).model_copy(deep=True)
        if session.run.scope.kind != "resume" or capture.query.ids:
            raise AgentFailure("AGENT_SCOPE_INVALID")
        if workspace.schema_version != 6 or not session.book.validate(workspace):
            raise AgentFailure("AGENT_STALE_READ")
        conversation, run, journal = run_in(session.service.store.load(project), session.control.run_id)
        identifier = "proposal_" + digest([project, run.id, request.key])[:48]
        request_sha = digest(wrapper)
        values = service.proposals.list(project)
        prior = next((value for value in values if value.proposal.id == identifier), None)
        if prior is not None:
            if not isinstance(prior, AssistantStoredActionV1) or prior.calls.get(request.key) != request_sha:
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            return result(prior).model_dump(mode="json", by_alias=True)
        if any(value.proposal.origin_run_id == run.id for value in values):
            raise AgentFailure("AGENT_EDIT_LIMIT")
        if len([value for value in values if value.proposal.state != "expired"]) >= VERSION_COUNT:
            raise AgentFailure("AGENT_PROJECT_FULL")
        archived = service.projects.catalog.get(project).archived
        raw_messages = [message.text for message in conversation.messages if message.role == "user"]
        raw_messages.append(journal.request.message)
    source = asset = blob = None
    suffix = digest([project, run.id, request.key])[:32]
    if request.action in {"add_source_text", "import_asset"}:
        if not request.value.strip() or not any(request.value in message for message in raw_messages):
            raise AgentFailure("AGENT_EVIDENCE_INVALID")
        if request.action == "add_source_text":
            from resume_api.extracting import run_extract
            from resume_api.lifecycle import OperationFiles
            blob = request.value.encode()
            with OperationFiles(service.projects.temp_root).open() as files:
                extracted = await run_extract(blob, "assistant-source.txt", True, files)
            source = canonical_source(extracted, source_id="source_" + suffix)
        else:
            try:
                asset, blob = normalize_image(base64.b64decode(request.value, validate=True), "asset_" + suffix)
            except (ImageFailure, ValueError):
                raise AgentFailure("AGENT_ARGUMENT_INVALID") from None
    with service.projects.state_lock:
        session.guard()
        current = session.service.projects.read(project)
        if (action_baseline_digest(current, service.projects.catalog.get(project).archived) != action_baseline_digest(workspace, archived)
                or not session.book.validate(current)):
            raise AgentFailure("AGENT_STALE_READ")
        lifecycle = request.action in {"archive", "restore", "delete"}
        candidate = None
        if not lifecycle:
            candidate, _metadata = workspace_action_candidate(workspace, request, source=source, asset=asset,
                image_references=service.projects.image_references(project) if request.action == "remove_asset" else None)
            type(workspace).model_validate(candidate.model_dump(by_alias=True))
        before, after, consequence = comparison(workspace, request, candidate, archived)
        payload = AssistantProjectActionPayloadV1(request=request, archivedBefore=archived,
            archivedAfter=(request.action == "archive") if request.action in {"archive", "restore"} else None if lifecycle else archived,
            blobBase64=base64.b64encode(blob).decode() if blob is not None else None,
            blobSha256=hashlib.sha256(blob).hexdigest() if blob is not None else None,
            preview=AssistantProjectActionPreviewV1(action=request.action, targetId=project, targetLabel=workspace.title,
                consequence=consequence, imagePreviewUrl=f"/v1/rich/projects/{project}/assistant/proposals/{identifier}/versions/1/image-preview"
                    if request.action in {"import_asset", "remove_asset"} else None))
        no_change = (before == after if lifecycle else action_content_digest(candidate) == action_content_digest(workspace))
        created = service.store.clock()
        proposal = AssistantProposalV1(id=identifier, version=1, projectId=project, lineage=digest([project, workspace.created_at]),
            editorFamily="ordinary", originRequestId=run.client_request_id, originRunId=run.id, taskId=task,
            state="incomplete" if no_change else "ready", createdAt=created, expiresAt=expiry(created),
            beforeSha256=action_baseline_digest(workspace, archived), contentSha256=action_proposal_digest(payload, candidate),
            coverage=[AssistantCoverageV1(unitId="project:" + project, state="unchanged" if no_change else "changed", reason=consequence, read=True)],
            changes=[] if no_change else [AssistantChangeV1(unitId="project:" + project, before=before, after=after, effect="structure")],
            operationCount=0, reason="Изменений нет." if no_change else consequence)
        value = AssistantStoredActionV1(policyRevision=POLICY_REVISION, proposal=proposal, action=payload,
            accountEpoch=run.connection_epoch, accessRevision=run.access_revision, scope=run.scope,
            dependencies=capture.dependencies, baseline=workspace, candidate=candidate, batch=None, operations=[],
            snapshotIds=[request.snapshot_id], calls={request.key: request_sha}, unchanged=[], noChange=no_change)
        def retain(values):
            prior = next((item for item in values if item.proposal.origin_run_id == run.id), None)
            if prior is not None:
                if prior.proposal.id != identifier or prior.calls.get(request.key) != request_sha:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                return prior
            return value
        return result(service.proposals.update(project, retain)).model_dump(mode="json", by_alias=True)
