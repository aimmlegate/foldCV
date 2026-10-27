"""One private project snapshot store, separate from credentials and exports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from pydantic import ValidationError

from .models.registry import Registry, RegistryEntry
from .storage import StorageFailure, atomic_write, data_root, locked_root, private_directory, private_file


MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class ProjectStoreFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    def invalid(_value):
        raise ValueError("invalid constant")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def owned_file(path, limit=MAX_SNAPSHOT_BYTES):
    if any(parent.is_symlink() for parent in path.parents):
        raise StorageFailure("UNSAFE_STORAGE")
    private_file(path)
    if path.stat().st_nlink != 1 or path.stat().st_size > limit:
        raise StorageFailure("UNSAFE_STORAGE")


class ProjectStore:
    # The V5 workspace model of the legacy GUI store; only its save and _load read it.
    workspace_model = None

    def __init__(self, root: Path | None = None):
        self.root = data_root(root)
        self.projects = self.root / "projects"
        self.registry_path = self.root / "registry.json"
        self.expected = {}

    def _directory(self, id, create=False):
        if SAFE_ID.fullmatch(id) is None:
            raise StorageFailure("UNSAFE_STORAGE")
        private_directory(self.projects)
        directory = self.projects / id
        if directory.is_symlink():
            raise StorageFailure("UNSAFE_STORAGE")
        marker = directory / ".project-identity.json"
        if create:
            if directory.exists() and not marker.exists() and any(directory.iterdir()):
                raise StorageFailure("UNSAFE_STORAGE")
            private_directory(directory)
            if not marker.exists():
                atomic_write(marker, encoded({"version": 1, "projectId": id}))
        else:
            if not directory.exists():
                raise ProjectStoreFailure("PROJECT_NOT_FOUND")
            private_directory(directory)
        owned_file(marker, 4096)
        if strict_json(marker.read_bytes()) != {"version": 1, "projectId": id}:
            raise StorageFailure("UNSAFE_STORAGE")
        return directory

    def _registry(self):
        private_directory(self.projects)
        if not self.registry_path.exists():
            if any(self.projects.iterdir()):
                raise StorageFailure("UNSAFE_STORAGE")
            registry = Registry(schemaVersion=1, entries=[])
            atomic_write(self.registry_path, encoded(registry.model_dump(mode="json", by_alias=True)))
            return registry
        owned_file(self.registry_path, 4 * 1024 * 1024)
        registry = Registry.model_validate(strict_json(self.registry_path.read_bytes()))
        ids = [entry.project_id for entry in registry.entries]
        if len(ids) != len(set(ids)) or any(SAFE_ID.fullmatch(id) is None for id in ids):
            raise StorageFailure("UNSAFE_STORAGE")
        return registry

    def _write_registry(self, registry):
        atomic_write(self.registry_path, encoded(registry.model_dump(mode="json", by_alias=True)))

    def _upsert(self, registry, workspace):
        current = next((entry for entry in registry.entries if entry.project_id == workspace.project_id), None)
        if current and current.tombstoned:
            raise ProjectStoreFailure("PROJECT_DELETED")
        value = RegistryEntry(projectId=workspace.project_id, title=workspace.title, updatedAt=workspace.updated_at,
            tombstoned=False, cleanupStatus="none")
        if current:
            registry.entries[registry.entries.index(current)] = value
        else:
            registry.entries.append(value)

    def _blob(self, directory, kind, id):
        return directory / kind / (hashlib.sha256(id.encode("utf-8")).hexdigest() + (".docx" if kind == "renders" else ".bin"))

    def save(self, workspace, originals, artifacts):
        try:
            with locked_root(self.root, ".projects.lock"):
                registry = self._registry()
                self._upsert(registry, workspace)
                directory = self._directory(workspace.project_id, create=True)
                target = directory / "workspace.json"
                if target.exists():
                    owned_file(target)
                    raw = target.read_bytes()
                    existing = self.workspace_model.model_validate(strict_json(raw))
                    if (hashlib.sha256(raw).hexdigest() != self.expected.get(workspace.project_id)
                        or existing.project_revision > workspace.project_revision
                        or existing.document_revision > workspace.document_revision):
                        raise ProjectStoreFailure("PROJECT_REVISION_CHANGED")
                owner = workspace.project or workspace.pre_draft
                for source in owner.sources:
                    content = originals.get((workspace.project_id, source.id))
                    if content is None or hashlib.sha256(content).hexdigest() != source.byte_sha256:
                        raise ProjectStoreFailure("SOURCE_BYTES_MISMATCH")
                    target = self._blob(directory, "sources", source.id)
                    if target.exists():
                        owned_file(target, 32 * 1024 * 1024)
                        if hashlib.sha256(target.read_bytes()).hexdigest() != source.byte_sha256:
                            raise ProjectStoreFailure("SOURCE_BYTES_MISMATCH")
                    else:
                        atomic_write(target, content)
                for snapshot in owner.renders:
                    content = artifacts.get((workspace.project_id, snapshot.id))
                    if content is None:
                        continue
                    if hashlib.sha256(content).hexdigest() != snapshot.docx.sha256 or len(content) != snapshot.docx.size:
                        raise ProjectStoreFailure("ARTIFACT_BYTES_MISMATCH")
                    target = self._blob(directory, "renders", snapshot.id)
                    if target.exists():
                        owned_file(target, 8 * 1024 * 1024)
                        if hashlib.sha256(target.read_bytes()).hexdigest() == snapshot.docx.sha256:
                            continue
                    atomic_write(target, content)
                snapshot = encoded(workspace.model_dump(mode="json", by_alias=True))
                if len(snapshot) > MAX_SNAPSHOT_BYTES:
                    raise ProjectStoreFailure("PROJECT_TOO_LARGE")
                from .archive_zip import ArchiveFailure, json_bytes
                try:
                    json_bytes(workspace.model_dump(mode="json", by_alias=True))
                except ArchiveFailure:
                    raise ProjectStoreFailure("PROJECT_TOO_LARGE") from None
                target = directory / "workspace.json"
                if target.exists(): owned_file(target)
                atomic_write(target, snapshot)
                self.expected[workspace.project_id] = hashlib.sha256(snapshot).hexdigest()
                self._write_registry(registry)
        except ProjectStoreFailure:
            raise
        except StorageFailure:
            raise ProjectStoreFailure("PROJECT_UNSAFE_STORAGE") from None
        except (OSError, UnicodeError, ValueError, RecursionError):
            raise ProjectStoreFailure("PROJECT_SAVE_FAILED") from None

    def _load(self, id):
        directory = self._directory(id)
        path = directory / "workspace.json"
        owned_file(path)
        raw = path.read_bytes()
        workspace = self.workspace_model.model_validate(strict_json(raw))
        self.expected[id] = hashlib.sha256(raw).hexdigest()
        if workspace.project_id != id:
            raise StorageFailure("UNSAFE_STORAGE")
        owner = workspace.project or workspace.pre_draft
        originals, artifacts = {}, {}
        for source in owner.sources:
            path = self._blob(directory, "sources", source.id)
            owned_file(path, 32 * 1024 * 1024)
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != source.byte_sha256:
                raise ProjectStoreFailure("SOURCE_BYTES_MISMATCH")
            originals[(id, source.id)] = content
        for snapshot in owner.renders:
            path = self._blob(directory, "renders", snapshot.id)
            try:
                owned_file(path, 8 * 1024 * 1024)
                content = path.read_bytes()
                if hashlib.sha256(content).hexdigest() != snapshot.docx.sha256 or len(content) != snapshot.docx.size:
                    raise StorageFailure("UNSAFE_STORAGE")
                artifacts[(id, snapshot.id)] = content
            except (OSError, StorageFailure):
                snapshot.artifact_available = False
        return workspace, originals, artifacts

    def load_all(self):
        loaded, errors = {}, {}
        try:
            with locked_root(self.root, ".projects.lock"):
                registry = self._registry()
                tombstones = {entry.project_id for entry in registry.entries if entry.tombstoned}
                ids = {entry.project_id for entry in registry.entries if not entry.tombstoned}
                # Recover a committed snapshot whose registry update failed; never resurrect a tombstone.
                ids.update(path.name for path in self.projects.iterdir() if SAFE_ID.fullmatch(path.name) and path.name not in tombstones)
                for id in sorted(ids):
                    try:
                        item = self._load(id)
                        loaded[id] = item
                        self._upsert(registry, item[0])
                    except ProjectStoreFailure as error:
                        errors[id] = error.code
                    except (StorageFailure, OSError, ValueError, ValidationError, RecursionError):
                        errors[id] = "PROJECT_LOAD_FAILED"
                self._write_registry(registry)
                return loaded, errors, registry
        except ProjectStoreFailure:
            raise
        except (StorageFailure, OSError, ValueError, ValidationError, RecursionError):
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED") from None

    def registry(self):
        try:
            with locked_root(self.root, ".projects.lock"):
                return self._registry()
        except (StorageFailure, OSError, ValueError, ValidationError):
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED") from None

    def tombstone(self, id):
        try:
            with locked_root(self.root, ".projects.lock"):
                registry = self._registry()
                entry = next((item for item in registry.entries if item.project_id == id), None)
                if entry is None: raise ProjectStoreFailure("PROJECT_NOT_FOUND")
                if not entry.tombstoned:
                    self._directory(id)
                    entry.tombstoned, entry.cleanup_status = True, "pending"
                    self._write_registry(registry)
                self.expected.pop(id, None)
                return entry.model_copy(deep=True)
        except ProjectStoreFailure:
            raise
        except (StorageFailure, OSError, ValueError, ValidationError):
            raise ProjectStoreFailure("PROJECT_DELETE_FAILED") from None

    def cleanup_deleted(self, id):
        try:
            with locked_root(self.root, ".projects.lock"):
                registry = self._registry()
                entry = next((item for item in registry.entries if item.project_id == id), None)
                if entry is None or not entry.tombstoned: raise ProjectStoreFailure("PROJECT_NOT_DELETED")
                directory = self.projects / id
                try:
                    if directory.exists() or directory.is_symlink():
                        marker = directory / ".project-identity.json"
                        if not marker.exists() and not directory.is_symlink() and directory.is_dir() and not any(directory.iterdir()):
                            # A prior cleanup can remove the identity before an empty-directory removal fails.
                            private_directory(directory)
                            directory.rmdir()
                        else:
                            directory = self._directory(id)
                            files, folders = [], []
                            for path in directory.iterdir():
                                if path.name in {"workspace.json", ".project-identity.json"}:
                                    owned_file(path);files.append(path)
                                elif path.name in {"sources", "renders"}:
                                    private_directory(path)
                                    suffix = "bin" if path.name == "sources" else "docx"
                                    for blob in path.iterdir():
                                        if re.fullmatch(r"[0-9a-f]{64}\." + suffix, blob.name) is None:
                                            raise StorageFailure("UNSAFE_STORAGE")
                                        owned_file(blob, 32 * 1024 * 1024);files.append(blob)
                                    folders.append(path)
                                else: raise StorageFailure("UNSAFE_STORAGE")
                            for path in files:
                                if path != marker: path.unlink()
                            for path in folders: path.rmdir()
                            marker.unlink()
                            directory.rmdir()
                    entry.cleanup_status = "complete"
                except (StorageFailure, OSError, ValueError):
                    entry.cleanup_status = "failed"
                self._write_registry(registry)
                return entry.model_copy(deep=True)
        except ProjectStoreFailure:
            raise
        except (StorageFailure, OSError, ValueError, ValidationError):
            raise ProjectStoreFailure("PROJECT_DELETE_FAILED") from None
