"""Portable v6 dispatch without legacy migration or trusted foreign render caches."""

from pydantic import ValidationError

from .archive_zip import ArchiveFailure, alias, digest, json_bytes, parse_json, read_zip, write_zip
from .models.rich_workspace import ArchiveManifestV6, WorkspaceV6
from .rich_images import ImageFailure, verify_image_bytes
from .rendering.rich_template import require_rich_template
from .rendering.template import RenderFailure
from .template_archive import inert_sync_history, referenced_assets


def archive_payload(workspace, originals, images, current_render=None, *, history=True):
    if workspace.schema_version == 7:
        from .template_archive import archive_payload_v7
        return archive_payload_v7(workspace,originals,images,current_render,history=history)
    workspace = WorkspaceV6.model_validate(workspace.model_dump(by_alias=True))
    inert_sync_history(workspace)
    owner = workspace.project or workspace.pre_draft
    payload, roles = {}, {}

    def add(path, role, content):
        if alias(path) in {alias(name) for name in payload}:
            raise ArchiveFailure("ARCHIVE_INVALID_PATH")
        payload[path], roles[path] = content, role

    for source in owner.sources:
        content = originals.get(source.id)
        if content is None or digest(content) != source.byte_sha256:
            raise ArchiveFailure("ARCHIVE_SOURCE_MISMATCH")
        add(source.byte_ref, "source_original", content)
    if workspace.project:
        workspace.project.assets = referenced_assets(workspace.project)
        for asset in workspace.project.assets:
            content = images.get(asset.id)
            if content is None:
                raise ArchiveFailure("ARCHIVE_IMAGE_MISMATCH")
            try:
                verify_image_bytes(asset, content)
            except ImageFailure:
                raise ArchiveFailure("ARCHIVE_IMAGE_MISMATCH") from None
            if asset.path not in payload:
                add(asset.path, "user_image", content)
        workspace.project.renders = []
    required = dict(payload)

    def build(render):
        content = dict(required)
        role_map = dict(roles)
        if render:
            snapshot, blob = render
            workspace.project.renders = [snapshot]
            content[snapshot.docx_path] = blob
            role_map[snapshot.docx_path] = "render"
        elif workspace.project:
            workspace.project.renders = []
        content["workspace.json"] = json_bytes(workspace.model_dump(mode="json", by_alias=True))
        role_map["workspace.json"] = "workspace"
        try:
            manifest = ArchiveManifestV6(schemaVersion=6, appVersion="0.1.0", projectId=workspace.project_id,
                entries=[{"path": path, "role": role_map[path], "sha256": digest(blob), "size": len(blob)}
                         for path, blob in content.items()])
        except ValidationError:
            raise ArchiveFailure("ARCHIVE_CAPACITY_LIMIT") from None
        return {"manifest.json": manifest.model_dump_json(by_alias=True).encode(), **content}

    if current_render:
        try:
            return build(current_render)
        except ArchiveFailure as error:
            if error.code not in {"ARCHIVE_CAPACITY_LIMIT", "ARCHIVE_JSON_LIMIT"}:
                raise
    return build(None)


def export_rich_archive(workspace, originals, artifacts, images):
    if workspace.schema_version == 7:
        return write_zip(archive_payload(workspace,originals,images))
    from .rendering.rich_docx import current_snapshot
    try:
        current = current_snapshot(workspace, artifacts)
    except RenderFailure:
        current = None
    return write_zip(archive_payload(workspace, originals, images, current))


def open_rich_archive(data, project_id):
    try:
        files = read_zip(data)
        raw = parse_json(files.get("manifest.json")) if "manifest.json" in files else {}
        if isinstance(raw,dict) and type(raw.get("schemaVersion")) is int and raw["schemaVersion"] == 7:
            from .template_archive import open_archive_v7
            return open_archive_v7(data,project_id)
        if not isinstance(raw, dict) or type(raw.get("schemaVersion")) is not int or raw["schemaVersion"] != 6:
            raise ArchiveFailure("ARCHIVE_VERSION_UNSUPPORTED")
        manifest = ArchiveManifestV6.model_validate(raw)
        entries = {entry.path: entry for entry in manifest.entries}
        if set(entries) != set(files) - {"manifest.json"}:
            raise ArchiveFailure("ARCHIVE_MANIFEST_INVALID")
        for path, entry in entries.items():
            if len(files[path]) != entry.size or digest(files[path]) != entry.sha256:
                raise ArchiveFailure("ARCHIVE_HASH_MISMATCH")
        workspace = WorkspaceV6.model_validate(parse_json(files.get("workspace.json")))
        if workspace.project_id != manifest.project_id:
            raise ArchiveFailure("ARCHIVE_ID_MISMATCH")
        owner = workspace.project or workspace.pre_draft
        originals, images = {}, {}
        source_paths = {source.byte_ref for source in owner.sources}
        if source_paths != {e.path for e in entries.values() if e.role == "source_original"}:
            raise ArchiveFailure("ARCHIVE_SOURCE_MISMATCH")
        for source in owner.sources:
            if digest(files[source.byte_ref]) != source.byte_sha256:
                raise ArchiveFailure("ARCHIVE_SOURCE_MISMATCH")
            originals[source.id] = files[source.byte_ref]
        expected_images = set()
        if workspace.project:
            if workspace.project.template != require_rich_template().manifest:
                raise ArchiveFailure("ARCHIVE_TEMPLATE_INVALID")
            referenced = referenced_assets(workspace.project)
            if len(referenced) != len(workspace.project.assets):
                raise ArchiveFailure("ARCHIVE_IMAGE_MISMATCH")
            for asset in referenced:
                entry = entries.get(asset.path)
                if entry is None or entry.role != "user_image":
                    raise ArchiveFailure("ARCHIVE_IMAGE_MISMATCH")
                verify_image_bytes(asset, files[asset.path])
                expected_images.add(asset.path)
                images[asset.id] = files[asset.path]
            render_entries = [e for e in entries.values() if e.role == "render"]
            if render_entries and not any(r.docx_path == render_entries[0].path and r.docx_sha256 == render_entries[0].sha256
                                          and r.docx_size == render_entries[0].size for r in workspace.project.renders):
                raise ArchiveFailure("ARCHIVE_RENDER_INVALID")
            workspace.project.project_id = project_id
            # Hashes alone cannot authenticate a foreign renderer's content/cache claim.
            workspace.project.renders = []
        elif any(e.role == "render" for e in entries.values()):
            raise ArchiveFailure("ARCHIVE_RENDER_INVALID")
        if expected_images != {e.path for e in entries.values() if e.role == "user_image"}:
            raise ArchiveFailure("ARCHIVE_IMAGE_MISMATCH")
        workspace.project_id = project_id
        workspace.mutation_replay = []
        for operation in owner.operations:
            if operation.status in {"queued", "running"}:
                operation.status, operation.error_code = "interrupted", "OPERATION_INTERRUPTED"
        inert_sync_history(workspace)
        return WorkspaceV6.model_validate(workspace.model_dump(by_alias=True)), originals, {}, images
    except ArchiveFailure:
        raise
    except ImageFailure:
        raise ArchiveFailure("ARCHIVE_IMAGE_MISMATCH") from None
    except RenderFailure:
        raise ArchiveFailure("ARCHIVE_TEMPLATE_INVALID") from None
    except (ValidationError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise ArchiveFailure("ARCHIVE_WORKSPACE_INVALID") from None
