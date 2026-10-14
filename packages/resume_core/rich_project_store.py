"""Version 6 snapshots and owned images; old projects remain unsupported."""

from __future__ import annotations

import hashlib
import re

from .models.rich_workspace import WorkspaceV6
from .project_store import ProjectStore, ProjectStoreFailure, owned_file, strict_json
from .rich_limits import DOCX_BYTES, WORKSPACE_BYTES
from .rich_limits import ImageReferences, retained_image_bytes
from .rich_images import ImageFailure, verify_image_bytes
from .storage import StorageFailure, atomic_write, locked_root, private_directory


def rich_snapshot_bytes(workspace: WorkspaceV6) -> bytes:
    raw = workspace.model_dump_json(by_alias=True).encode("utf-8")
    if len(raw) > WORKSPACE_BYTES:
        raise ProjectStoreFailure("PROJECT_TOO_LARGE")
    return raw


def decode_rich_snapshot(raw: bytes) -> WorkspaceV6:
    data = strict_json(raw)
    if not isinstance(data, dict) or type(data.get("schemaVersion")) is not int:
        raise ProjectStoreFailure("PROJECT_LOAD_FAILED")
    if data["schemaVersion"] != 6:
        raise ProjectStoreFailure("PROJECT_VERSION_UNSUPPORTED")
    return WorkspaceV6.model_validate(data)


class RichProjectStore(ProjectStore):
    def save(self, workspace, originals, artifacts, images=None):
        images = images or {}
        try:
            raw = rich_snapshot_bytes(WorkspaceV6.model_validate(workspace.model_dump(by_alias=True)))
            owner = workspace.project or workspace.pre_draft
            from .rich_archive import archive_payload
            from .gui_archive_zip import ArchiveFailure
            try:
                archive_payload(workspace, {key[1]: blob for key, blob in originals.items() if key[0] == workspace.project_id},
                    {key[1]: blob for key, blob in images.items() if key[0] == workspace.project_id})
            except ArchiveFailure as error:
                raise ProjectStoreFailure(error.code) from None
            prepared = []
            for source in owner.sources:
                blob = originals.get((workspace.project_id, source.id))
                if blob is None or len(blob) > 32 * 1024 * 1024 or hashlib.sha256(blob).hexdigest() != source.byte_sha256:
                    raise ProjectStoreFailure("SOURCE_BYTES_MISMATCH")
                prepared.append(("sources", source.id, blob, source.byte_sha256))
            if workspace.project:
                try:
                    retained_image_bytes(workspace.project.assets, ImageReferences(durable=tuple(asset.id for asset in workspace.project.assets)))
                except ValueError:
                    raise ProjectStoreFailure("IMAGE_RETAINED_LIMIT") from None
                for asset in workspace.project.assets:
                    blob = images.get((workspace.project_id, asset.id))
                    if blob is None:
                        raise ProjectStoreFailure("IMAGE_BYTES_MISMATCH")
                    verify_image_bytes(asset, blob)
                for render in workspace.project.renders:
                    blob = artifacts.get((workspace.project_id, render.id))
                    if blob is not None:
                        if len(blob) > DOCX_BYTES or len(blob) != render.docx_size or hashlib.sha256(blob).hexdigest() != render.docx_sha256:
                            raise ProjectStoreFailure("ARTIFACT_BYTES_MISMATCH")
                        prepared.append(("renders", render.id, blob, render.docx_sha256))
            with locked_root(self.root, ".projects.lock"):
                registry = self._registry()
                self._upsert(registry, workspace)
                directory = self._directory(workspace.project_id, create=True)
                target = directory / "workspace.json"
                if target.exists():
                    owned_file(target)
                    old_raw = target.read_bytes()
                    existing = decode_rich_snapshot(old_raw)
                    if hashlib.sha256(old_raw).hexdigest() != self.expected.get(workspace.project_id) or (
                        existing.project_revision > workspace.project_revision or existing.document_revision > workspace.document_revision
                    ):
                        raise ProjectStoreFailure("PROJECT_REVISION_CHANGED")
                for kind, identifier, blob, checksum in prepared:
                    path = self._blob(directory, kind, identifier)
                    if path.exists():
                        owned_file(path, DOCX_BYTES if kind == "renders" else 32 * 1024 * 1024)
                        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                            raise ProjectStoreFailure("ARTIFACT_BYTES_MISMATCH" if kind == "renders" else "SOURCE_BYTES_MISMATCH")
                    else:
                        atomic_write(path, blob)
                if workspace.project:
                    private_directory(directory / "images")
                    for asset in workspace.project.assets:
                        path = directory / asset.path
                        blob = images[(workspace.project_id, asset.id)]
                        if path.exists():
                            owned_file(path, 20 * 1024 * 1024)
                            verify_image_bytes(asset, path.read_bytes())
                        else:
                            atomic_write(path, blob)
                atomic_write(target, raw)
                self.expected[workspace.project_id] = hashlib.sha256(raw).hexdigest()
                self._write_registry(registry)
        except ProjectStoreFailure:
            raise
        except ImageFailure as error:
            raise ProjectStoreFailure(error.code) from None
        except StorageFailure:
            raise ProjectStoreFailure("PROJECT_UNSAFE_STORAGE") from None
        except (OSError, UnicodeError, ValueError, RecursionError):
            raise ProjectStoreFailure("PROJECT_SAVE_FAILED") from None

    def _load(self, id):
        directory = self._directory(id)
        target = directory / "workspace.json"
        owned_file(target)
        raw = target.read_bytes()
        workspace = decode_rich_snapshot(raw)
        if len(raw) > WORKSPACE_BYTES or workspace.project_id != id:
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED")
        owner = workspace.project or workspace.pre_draft
        originals, artifacts, images = {}, {}, {}
        for source in owner.sources:
            path = self._blob(directory, "sources", source.id)
            owned_file(path, 32 * 1024 * 1024)
            blob = path.read_bytes()
            if hashlib.sha256(blob).hexdigest() != source.byte_sha256:
                raise ProjectStoreFailure("SOURCE_BYTES_MISMATCH")
            originals[(id, source.id)] = blob
        if workspace.project:
            for asset in workspace.project.assets:
                path = directory / asset.path
                owned_file(path, 20 * 1024 * 1024)
                blob = path.read_bytes()
                try:
                    verify_image_bytes(asset, blob)
                except ImageFailure as error:
                    raise ProjectStoreFailure(error.code) from None
                images[(id, asset.id)] = blob
            available = []
            for render in workspace.project.renders:
                try:
                    path = self._blob(directory, "renders", render.id)
                    owned_file(path, DOCX_BYTES)
                    blob = path.read_bytes()
                    if len(blob) != render.docx_size or hashlib.sha256(blob).hexdigest() != render.docx_sha256:
                        continue
                    artifacts[(id, render.id)] = blob
                    available.append(render)
                except (OSError, StorageFailure):
                    continue
            workspace.project.renders = available
        self.expected[id] = hashlib.sha256(raw).hexdigest()
        return workspace, originals, artifacts, images

    def cleanup_deleted(self, id):
        with locked_root(self.root, ".projects.lock"):
            registry = self._registry()
            entry = next((item for item in registry.entries if item.project_id == id), None)
            if entry is None or not entry.tombstoned:
                raise ProjectStoreFailure("PROJECT_NOT_DELETED")
            directory = self._directory(id)
            target = directory / "workspace.json"
            owned_file(target)
            # Unsupported files are never eligible for rich cleanup, even after a list action.
            decode_rich_snapshot(target.read_bytes())
            try:
                files, folders = [], []
                for path in directory.iterdir():
                    if path.name in {"workspace.json", ".project-identity.json"}:
                        owned_file(path); files.append(path)
                    elif path.name in {"sources", "renders", "images"}:
                        private_directory(path)
                        suffix = {"sources": "bin", "renders": "docx", "images": "(?:png|jpg)"}[path.name]
                        for blob in path.iterdir():
                            if re.fullmatch(r"[0-9a-f]{64}\." + suffix, blob.name) is None:
                                raise StorageFailure("UNSAFE_STORAGE")
                            owned_file(blob, DOCX_BYTES); files.append(blob)
                        folders.append(path)
                    else:
                        raise StorageFailure("UNSAFE_STORAGE")
                marker = directory / ".project-identity.json"
                for path in files:
                    if path != marker:
                        path.unlink()
                for path in folders:
                    path.rmdir()
                marker.unlink(); directory.rmdir()
                entry.cleanup_status = "complete"
            except (OSError, StorageFailure):
                entry.cleanup_status = "failed"
            self._write_registry(registry)
            return entry.model_copy(deep=True)
