"""Version 6 snapshots and owned images; old projects remain unsupported."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
import os
import re

from .models.rich_workspace import WorkspaceV6
from .models.template_workspace import WorkspaceV7
from .project_store import ProjectStore, ProjectStoreFailure, owned_file, strict_json
from .project_limits import project_file_bytes
from .rich_limits import DOCX_BYTES, WORKSPACE_BYTES
from .rich_limits import ImageReferences, retained_image_bytes
from .rich_images import ImageFailure, verify_image_bytes
from .storage import StorageFailure, atomic_write, locked_root, private_directory


def rich_snapshot_bytes(workspace: WorkspaceV6) -> bytes:
    if workspace.schema_version == 7:
        raw = json.dumps(workspace.model_dump(mode='json', by_alias=True), sort_keys=True,
            ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    else:
        raw = workspace.model_dump_json(by_alias=True).encode("utf-8")
    if len(raw) > WORKSPACE_BYTES:
        raise ProjectStoreFailure("PROJECT_TOO_LARGE")
    return raw


def decode_rich_snapshot(raw: bytes) -> WorkspaceV6:
    return decode_rich_data(strict_json(raw))


def decode_rich_data(data) -> WorkspaceV6:
    if not isinstance(data, dict) or type(data.get("schemaVersion")) is not int:
        raise ProjectStoreFailure("PROJECT_LOAD_FAILED")
    if data["schemaVersion"] == 6: return WorkspaceV6.model_validate(data)
    if data["schemaVersion"] == 7: return WorkspaceV7.model_validate(data)
    raise ProjectStoreFailure("PROJECT_VERSION_UNSUPPORTED")


def stored_owners(data):
    return [owner for owner in (data.get("project"), data.get("preDraft")) if isinstance(owner, dict)] if isinstance(data, dict) else []


def inline_history(data) -> bool:
    """A version 7 file written before D104 keeps import records or asset bytes in the workspace JSON."""
    if not isinstance(data, dict) or data.get("schemaVersion") != 7:
        return False
    project = data.get("project")
    return (isinstance(project, dict) and "templateOperations" in project) or any(
        isinstance(asset, dict) and "bytesBase64" in asset
        for owner in stored_owners(data) for asset in ((owner.get("templatePackage") or {}).get("assets") or []))


def history_blobs(workspace):
    """Content-addressed files for a project's loaded import records and every captured asset (D104)."""
    from .models.template_workspace import history_bytes
    blobs = []
    owner = workspace.project or workspace.pre_draft if workspace.schema_version == 7 else None
    if owner is None:
        return blobs
    if workspace.project is not None:
        for operation in workspace.project.template_operations:
            raw = history_bytes(operation)
            digest = hashlib.sha256(raw).hexdigest()
            blobs.append(("history", digest, raw, digest))
    if owner.template_package is not None:
        for asset in owner.template_package.assets:
            blobs.append(("template-assets", asset.sha256, base64.b64decode(asset.bytes_base64, validate=True), asset.sha256))
    return blobs


@dataclass(frozen=True)
class PreparedRichSave:
    workspace: WorkspaceV6
    raw: bytes
    blobs: tuple
    images: tuple
    history: tuple = field(default=())


def changed_operations(previous, candidate, history=(), load=None):
    """Pairs of (retained record, its new version) for every import record whose content may have changed. A project
    names its records by history file; one whose file is unchanged needs no comparison (D104)."""
    before_owner, after_owner = previous.project or previous.pre_draft, candidate.project or candidate.pre_draft
    before_refs = {ref.operation_id: ref.sha256 for ref in getattr(before_owner, "import_history", [])}
    after_refs = {ref.operation_id: ref.sha256 for ref in getattr(after_owner, "import_history", [])}
    before_ops = {value.id: value for value in before_owner.template_operations}
    after_ops = {value.id: value for value in (history or after_owner.template_operations)}
    pairs = []
    for identifier in [*before_ops, *[key for key in before_refs if key not in before_ops]]:
        if identifier not in after_ops and identifier not in after_refs:
            raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
        if identifier in before_refs and after_refs.get(identifier) == before_refs[identifier]:
            continue
        retained = before_ops.get(identifier)
        if retained is None:
            if load is None:
                raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
            retained = load(identifier, before_refs[identifier])
        current = after_ops.get(identifier)
        if current is None:
            raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
        pairs.append((retained, current))
    return pairs


def retain_template_state(previous, candidate, history=(), load=None):
    if previous.schema_version != 7:
        if candidate.schema_version == 7:
            raise ProjectStoreFailure('PROJECT_VERSION_UNSUPPORTED')
        return
    if candidate.schema_version != 7:
        raise ProjectStoreFailure('PROJECT_VERSION_UNSUPPORTED')
    if previous.project is not None and candidate.project is None:
        raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
    before, after = previous.project or previous.pre_draft, candidate.project or candidate.pre_draft
    if before.template_package is not None and before.template_package != after.template_package:
        raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
    retained = {(source.id, source.revision): source for source in after.sources}
    for source in before.sources:
        current = retained.get((source.id, source.revision))
        if current is None or (source.byte_sha256, source.byte_ref, source.original_name) != (
                current.byte_sha256, current.byte_ref, current.original_name):
            raise ProjectStoreFailure('SOURCE_BYTES_MISMATCH')
        old_units = [unit.model_dump(exclude={'disposition', 'represented_fact_ids'}) for unit in source.units]
        new_units = [unit.model_dump(exclude={'disposition', 'represented_fact_ids'}) for unit in current.units]
        if source.parser != 'pending' and (source.parser, source.parser_version, old_units) != (
                current.parser, current.parser_version, new_units):
            raise ProjectStoreFailure('SOURCE_BYTES_MISMATCH')
    if previous.project is not None:
        evidence = {value.id: value for value in candidate.project.evidence_records}
        if any(evidence.get(value.id) != value for value in previous.project.evidence_records):
            raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
        if previous.project.export_inputs != candidate.project.export_inputs[:len(previous.project.export_inputs)]:
            raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
        from .template_retention import retain_exports
        retain_exports(previous.project.exports, candidate.project.exports)
    observations = {value.id: value for value in after.facts.observations}
    identities = {value.record_id: value for value in after.facts.builtin_identities}
    scopes = {value.id: value for value in after.facts.manual_scopes}
    if (any(identities.get(value.record_id) != value for value in before.facts.builtin_identities)
            or any(scopes.get(value.id) != value for value in before.facts.manual_scopes)):
        raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
    for observation in before.facts.observations:
        current = observations.get(observation.id)
        if current is None or observation.model_dump(exclude={'admission', 'receipt_ids'}) != current.model_dump(
                exclude={'admission', 'receipt_ids'}) or not set(observation.receipt_ids) <= set(current.receipt_ids):
            raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
    for operation, current in changed_operations(previous, candidate, history, load):
        if current is None or operation.capture != current.capture or any(
                getattr(operation, key) is not None and getattr(operation, key) != getattr(current, key)
                for key in ('admitted_at', 'expires_at')):
            raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
        allocations = {(value.task_id, value.discovery_attempt_id, value.key): value for value in current.allocations}
        if any(allocations.get((value.task_id, value.discovery_attempt_id, value.key)) != value for value in operation.allocations):
            raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
        from .template_retention import retain_operation
        retain_operation(operation, current)


class RichProjectStore(ProjectStore):
    def _decode(self, directory, raw, *, history=False):
        """The workspace of a project file; asset bytes come from the project's asset files and import records from its
        history files, and only when asked for (D104)."""
        from .templates.models import asset_text, remember_asset
        data = strict_json(raw)
        for owner in stored_owners(data):
            for asset in ((owner.get("templatePackage") or {}).get("assets") or []):
                digest = asset.get("sha256") if isinstance(asset, dict) else None
                if isinstance(digest, str) and "bytesBase64" not in asset and asset_text(digest) is None:
                    path = self._blob(directory, "template-assets", digest)
                    owned_file(path, 20 * 1024 * 1024)
                    remember_asset(digest, base64.b64encode(path.read_bytes()).decode("ascii"))
        project = data.get("project") if isinstance(data, dict) else None
        if history and isinstance(project, dict) and project.get("importHistory") and "templateOperations" not in project:
            project["templateOperations"] = [strict_json(self._history(directory, ref.get("sha256")))
                for ref in project["importHistory"] if isinstance(ref, dict)]
        return decode_rich_data(data)

    def _history(self, directory, digest):
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED")
        path = self._blob(directory, "history", digest)
        owned_file(path, WORKSPACE_BYTES)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED")
        from .models.template_workspace import remember_history
        remember_history(digest, raw)
        return raw

    def load_history(self, workspace):
        """The same workspace with its project's import records loaded, for imports, publication and archives."""
        project = workspace.project if workspace.schema_version == 7 else None
        if project is None or project.history_loaded:
            return workspace
        try:
            directory = self._directory(workspace.project_id)
            records = [strict_json(self._history(directory, ref.sha256)) for ref in project.import_history]
            data = workspace.model_dump(mode="json", by_alias=True)
            data["project"]["templateOperations"] = records
            return decode_rich_data(data)
        except ProjectStoreFailure:
            raise
        except (StorageFailure, OSError, ValueError):
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED") from None

    def externalize_history(self):
        """Move import records and asset bytes of files written before D104 into their own files, once, before any
        service reads a project. Each editor state keeps working: its recorded file hash moves to the new bytes."""
        try:
            with locked_root(self.root, ".projects.lock"):
                if not self.projects.exists():
                    return []
                moved = []
                for directory in sorted(self.projects.iterdir()):
                    target = directory / "workspace.json"
                    if not target.is_file() or target.is_symlink():
                        continue
                    owned_file(target)
                    raw = target.read_bytes()
                    if not inline_history(strict_json(raw)):
                        continue
                    workspace = self._decode(directory, raw)
                    for kind, identifier, blob, checksum in history_blobs(workspace):
                        path = self._blob(directory, kind, identifier)
                        if not path.exists():
                            atomic_write(path, blob)
                    slim = rich_snapshot_bytes(workspace)
                    self._rebase_background(workspace.project_id, hashlib.sha256(raw).hexdigest(), hashlib.sha256(slim).hexdigest())
                    atomic_write(target, slim)
                    moved.append(workspace.project_id)
                return moved
        except ProjectStoreFailure:
            raise
        except (StorageFailure, OSError, ValueError):
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED") from None

    def _rebase_background(self, project, before, after):
        folder = self.root / "background" / "projects" / project
        state_path = folder / "state.json"
        if not state_path.exists():
            return
        background = self.root / "background"
        with locked_root(background, ".jobs.lock"):
            from .background_limits import LIMITS
            owned_file(state_path, LIMITS.sidecar_project_bytes)
            state = strict_json(state_path.read_bytes())
            settled = all(intent.get("phase") in {"receipt_stored", "reconciled"}
                for intent in [*state.get("intents", []), *state.get("manualIntents", [])])
            if not settled:
                # An unfinished save names the old bytes; that editor state starts again instead.
                spare = self.root / "migrated-d104" / project
                private_directory(spare.parent)
                os.replace(folder, spare)
                return
            history, writer = state.get("history"), state.get("writer")
            if isinstance(history, dict) and history.get("workspaceSha256") == before:
                history["workspaceSha256"] = after
            if isinstance(writer, dict) and writer.get("acknowledgedSha256") == before:
                writer["acknowledgedSha256"] = after
            atomic_write(state_path, json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    def _observe(self, phase, identifier):
        observer = getattr(self, "background_observer", None)
        if observer is not None:
            observer(phase, identifier)

    def reclaim_images(self, workspace):
        try:
            with locked_root(self.root, ".projects.lock"):
                marker = self.root / "background" / "projects" / workspace.project_id / "history-activation.json"
                if marker.exists() or marker.is_symlink():
                    return
                directory = self._directory(workspace.project_id)
                target = directory / "workspace.json"
                owned_file(target)
                raw = target.read_bytes()
                current = self._decode(directory, raw)
                if hashlib.sha256(raw).hexdigest() != self.expected.get(workspace.project_id):
                    return
                folder = directory / "images"
                if not folder.exists():
                    return
                private_directory(folder)
                keep = {asset.path for asset in current.project.assets} if current.project else set()
                for path in folder.iterdir():
                    if re.fullmatch(r"[0-9a-f]{64}\.(?:png|jpg)", path.name) is None:
                        raise StorageFailure("UNSAFE_STORAGE")
                    owned_file(path, 20 * 1024 * 1024)
                for path in folder.iterdir():
                    if "images/" + path.name not in keep:
                        path.unlink()
        except (ProjectStoreFailure, StorageFailure, OSError):
            return

    def save(self, workspace, originals, artifacts, images=None, *, before_workspace=None, after_workspace=None):
        prepared = self.prepare_save(workspace, originals, artifacts, images)
        try:
            with locked_root(self.root, ".projects.lock"):
                marker = self.root / "background" / "projects" / workspace.project_id / "history-activation.json"
                if marker.exists() or marker.is_symlink():
                    raise ProjectStoreFailure("PROJECT_COORDINATOR_REQUIRED")
                sidecar = marker.with_name("state.json")
                if sidecar.exists() or sidecar.is_symlink():
                    try:
                        from .background_limits import LIMITS
                        owned_file(sidecar, LIMITS.sidecar_project_bytes)
                        state = strict_json(sidecar.read_bytes())
                        if not isinstance(state, dict) or state.get("historyNamespace") is not None or state.get("history") is not None or state.get("generations"):
                            raise ValueError("coordinated history exists")
                    except (OSError, StorageFailure, ValueError):
                        raise ProjectStoreFailure("PROJECT_COORDINATOR_REQUIRED") from None
                self._commit_prepared_unlocked(prepared, before_workspace=before_workspace, after_workspace=after_workspace)
        except ProjectStoreFailure:
            raise
        except StorageFailure:
            raise ProjectStoreFailure("PROJECT_UNSAFE_STORAGE") from None
        except (OSError, ValueError):
            raise ProjectStoreFailure("PROJECT_SAVE_FAILED") from None

    def prepare_save(self, workspace, originals, artifacts, images=None):
        images = images or {}
        try:
            # Records and assets go to their own files; the workspace JSON and its hash only name them (D104).
            external = history_blobs(workspace)
            history = tuple(workspace.project.template_operations) if workspace.schema_version == 7 and workspace.project else ()
            workspace = decode_rich_snapshot(rich_snapshot_bytes(workspace))
            raw = rich_snapshot_bytes(workspace)
            if len(raw) > project_file_bytes():
                raise ProjectStoreFailure("PROJECT_TOO_LARGE")
            owner = workspace.project or workspace.pre_draft
            from .rich_archive import archive_payload
            from .gui_archive_zip import ArchiveFailure
            try:
                archive_payload(workspace, {key[1]: blob for key, blob in originals.items() if key[0] == workspace.project_id},
                    {key[1]: blob for key, blob in images.items() if key[0] == workspace.project_id}, history=False)
            except ArchiveFailure as error:
                raise ProjectStoreFailure(error.code) from None
            prepared = []
            for source in owner.sources:
                blob = originals.get((workspace.project_id, source.id))
                if blob is None or len(blob) > 32 * 1024 * 1024 or hashlib.sha256(blob).hexdigest() != source.byte_sha256:
                    raise ProjectStoreFailure("SOURCE_BYTES_MISMATCH")
                prepared.append(("sources", source.id, blob, source.byte_sha256))
            prepared.extend(external)
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
            retained = tuple((asset, images[(workspace.project_id, asset.id)]) for asset in workspace.project.assets) if workspace.project else ()
            return PreparedRichSave(workspace, raw, tuple(prepared), retained, history)
        except ProjectStoreFailure:
            raise
        except ImageFailure as error:
            raise ProjectStoreFailure(error.code) from None
        except StorageFailure:
            raise ProjectStoreFailure("PROJECT_UNSAFE_STORAGE") from None
        except (OSError, UnicodeError, ValueError, RecursionError):
            raise ProjectStoreFailure("PROJECT_SAVE_FAILED") from None

    def _commit_prepared_unlocked(self, prepared, *, before_workspace=None, after_workspace=None, workspace_replaced=None):
        """Commit validated bytes under an existing canonical lifecycle guard."""
        workspace, raw = prepared.workspace, prepared.raw
        try:
            if rich_snapshot_bytes(workspace) != raw:
                raise ProjectStoreFailure("PROJECT_SAVE_FAILED")
            registry = self._registry()
            self._upsert(registry, workspace)
            directory = self._directory(workspace.project_id, create=True)
            target = directory / "workspace.json"
            if target.exists():
                owned_file(target)
                old_raw = target.read_bytes()
                existing = self._decode(directory, old_raw)
                if hashlib.sha256(old_raw).hexdigest() != self.expected.get(workspace.project_id) or (
                    existing.project_revision > workspace.project_revision or existing.document_revision > workspace.document_revision
                ):
                    raise ProjectStoreFailure("PROJECT_REVISION_CHANGED")
                from .models.template_import import ImportOperation
                retain_template_state(existing, workspace, prepared.history,
                    lambda _identifier, digest: ImportOperation.model_validate(strict_json(self._history(directory, digest))))
            if workspace.schema_version == 7 and workspace.project is not None:
                staged = {identifier for kind, identifier, _blob, _checksum in prepared.blobs if kind == "history"}
                for ref in workspace.project.import_history:
                    if ref.sha256 not in staged and not self._blob(directory, "history", ref.sha256).exists():
                        raise ProjectStoreFailure("PROJECT_SAVE_FAILED")
            self._observe("before_assets_staged", workspace.project_id)
            from .models.template_workspace import remember_history
            for kind, identifier, blob, checksum in prepared.blobs:
                if kind == "history":
                    remember_history(checksum, blob)
                path = self._blob(directory, kind, identifier)
                if path.exists():
                    owned_file(path, DOCX_BYTES if kind == "renders" else 32 * 1024 * 1024)
                    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                        raise ProjectStoreFailure("ARTIFACT_BYTES_MISMATCH" if kind == "renders" else "SOURCE_BYTES_MISMATCH")
                else:
                    atomic_write(path, blob)
            if workspace.project:
                private_directory(directory / "images")
                for asset, blob in prepared.images:
                    path = directory / asset.path
                    if path.exists():
                        owned_file(path, 20 * 1024 * 1024)
                        verify_image_bytes(asset, path.read_bytes())
                    else:
                        atomic_write(path, blob)
            self._observe("assets_staged", workspace.project_id)
            if before_workspace is not None:
                before_workspace()
            atomic_write(target, raw, **({"after_replace": workspace_replaced} if workspace_replaced else {}))
            self.expected[workspace.project_id] = hashlib.sha256(raw).hexdigest()
            if after_workspace is not None:
                after_workspace(self.expected[workspace.project_id])
            self._write_registry(registry)
        except ProjectStoreFailure:
            raise
        except ImageFailure as error:
            raise ProjectStoreFailure(error.code) from None
        except StorageFailure:
            raise ProjectStoreFailure("PROJECT_UNSAFE_STORAGE") from None
        except (OSError, UnicodeError, ValueError, RecursionError):
            raise ProjectStoreFailure("PROJECT_SAVE_FAILED") from None

    def read_committed(self, identifier, *, synchronize=False, history=False):
        try:
            with locked_root(self.root, ".projects.lock"):
                return self._read_committed_unlocked(identifier, synchronize=synchronize, history=history)
        except ProjectStoreFailure:
            raise
        except (StorageFailure, OSError, ValueError):
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED") from None

    def _read_committed_unlocked(self, identifier, *, synchronize=False, history=False):
        """Read under an existing canonical lifecycle guard without reentering it."""
        try:
            entry = next((entry for entry in self._registry().entries if entry.project_id == identifier), None)
            if entry is None or entry.tombstoned:
                raise ProjectStoreFailure("PROJECT_DELETED")
            return self._read_owned_snapshot_unlocked(identifier, synchronize=synchronize, history=history)
        except ProjectStoreFailure:
            raise
        except (StorageFailure, OSError, ValueError):
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED") from None

    def committed_key(self, identifier):
        """The identity of a live project's saved file (inode, size, times), with the same registry and ownership
        checks as a read; equal keys mean the same bytes, since every save replaces the file."""
        with locked_root(self.root, ".projects.lock"):
            return self._committed_key_unlocked(identifier)

    def _committed_key_unlocked(self, identifier):
        """committed_key under an existing canonical lifecycle guard."""
        try:
            entry = next((entry for entry in self._registry().entries if entry.project_id == identifier), None)
            if entry is None or entry.tombstoned:
                raise ProjectStoreFailure("PROJECT_DELETED")
            path = self._directory(identifier) / "workspace.json"
            owned_file(path, WORKSPACE_BYTES)
            status = os.stat(path, follow_symlinks=False)
            return (status.st_ino, status.st_size, status.st_mtime_ns, status.st_ctime_ns)
        except ProjectStoreFailure:
            raise
        except (StorageFailure, OSError, ValueError):
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED") from None

    def project_directory(self, identifier):
        """The folder of a stored or deleted project; template import sidecars live in its imports folder."""
        return self._directory(identifier)

    def _read_template_cleanup_unlocked(self, identifier, operation_id, *, with_revision=False):
        """Read only durable owner evidence while the caller holds the deleted guard."""
        entry = next((item for item in self._registry().entries if item.project_id == identifier), None)
        if entry is None or not entry.tombstoned:
            raise ProjectStoreFailure('PROJECT_NOT_DELETED')
        workspace, _checksum = self._read_owned_snapshot_unlocked(identifier, history=True)
        if workspace.schema_version != 7:
            raise ProjectStoreFailure('PROJECT_VERSION_UNSUPPORTED')
        operation = next((item for item in (workspace.project or workspace.pre_draft).template_operations
            if item.id == operation_id), None)
        if operation is None:
            raise ProjectStoreFailure('PROJECT_LOAD_FAILED')
        return (operation, workspace.project_revision) if with_revision else operation

    def _read_owned_snapshot_unlocked(self, identifier, *, synchronize=False, history=False):
        try:
            directory = self._directory(identifier)
            path = directory / "workspace.json"
            owned_file(path, WORKSPACE_BYTES)
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                if before.st_nlink != 1 or before.st_uid != os.getuid() or before.st_mode & 0o077:
                    raise StorageFailure("UNSAFE_STORAGE")
                raw = stream.read(WORKSPACE_BYTES + 1)
                after = os.fstat(stream.fileno())
                if len(raw) > WORKSPACE_BYTES or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink) != (
                        after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink):
                    raise StorageFailure("UNSAFE_STORAGE")
                workspace = self._decode(directory, raw, history=history)
                if workspace.project_id != identifier:
                    raise StorageFailure("UNSAFE_STORAGE")
                if synchronize:
                    # Confirm existing bytes; never reapply or replace an uncertain command.
                    os.fsync(stream.fileno())
                    folder = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(folder)
                    finally:
                        os.close(folder)
            return workspace, hashlib.sha256(raw).hexdigest()
        except ProjectStoreFailure:
            raise
        except (StorageFailure, OSError, ValueError):
            raise ProjectStoreFailure("PROJECT_LOAD_FAILED") from None

    def _load(self, id):
        directory = self._directory(id)
        target = directory / "workspace.json"
        owned_file(target)
        raw = target.read_bytes()
        workspace = self._decode(directory, raw)
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
        try:
            return self._cleanup_deleted(id)
        except ProjectStoreFailure:
            raise
        except (StorageFailure, OSError, ValueError):
            raise ProjectStoreFailure("PROJECT_DELETE_FAILED") from None

    def _cleanup_deleted(self, id):
        with locked_root(self.root, ".projects.lock"):
            registry = self._registry()
            entry = next((item for item in registry.entries if item.project_id == id), None)
            if entry is None or not entry.tombstoned:
                raise ProjectStoreFailure("PROJECT_NOT_DELETED")
            directory = self.projects / id
            sidecar = self.root / 'background' / 'projects' / id / 'state.json'
            if sidecar.exists() or sidecar.is_symlink():
                from .background_limits import LIMITS
                from .models.background import BackgroundSidecarV1
                with locked_root(self.root / 'background', '.jobs.lock'):
                    owned_file(sidecar, LIMITS.sidecar_project_bytes)
                    state = BackgroundSidecarV1.model_validate(strict_json(sidecar.read_bytes()))
                    latest = {value.operation_id: value for value in state.template_authorizations}
                    if state.project_id != id or any(value.deleted_cleanup is None or not value.deleted_cleanup.complete
                            for value in latest.values()):
                        raise ProjectStoreFailure('PROJECT_DELETE_FAILED')
            try:
                self._observe("before_tombstone_cleanup", id)
                if not directory.exists() and not directory.is_symlink():
                    entry.cleanup_status = "complete"
                    self._write_registry(registry)
                    return entry.model_copy(deep=True)
                marker = directory / ".project-identity.json"
                if (not marker.exists() and not directory.is_symlink() and directory.is_dir()
                        and not any(directory.iterdir())):
                    private_directory(directory)
                    directory.rmdir()
                    entry.cleanup_status = "complete"
                    self._write_registry(registry)
                    return entry.model_copy(deep=True)
                directory = self._directory(id)
                files, folders = [], []
                for path in directory.iterdir():
                    if path.name in {"workspace.json", ".project-identity.json"}:
                        owned_file(path); files.append(path)
                    elif path.name in {"sources", "renders", "images", "history", "template-assets"}:
                        private_directory(path)
                        suffix = {"sources": "bin", "renders": "(?:docx|foldcv)", "images": "(?:png|jpg)",
                            "history": "bin", "template-assets": "bin"}[path.name]
                        for blob in path.iterdir():
                            if re.fullmatch(r"[0-9a-f]{64}\." + suffix, blob.name) is None:
                                raise StorageFailure("UNSAFE_STORAGE")
                            owned_file(blob, DOCX_BYTES); files.append(blob)
                        folders.append(path)
                    elif path.name == "imports":
                        # Sidecars of running template imports: one whole operation each (S7e).
                        private_directory(path)
                        for blob in path.iterdir():
                            if re.fullmatch(r"[A-Za-z0-9_-]{1,128}\.json(?:\.tmp)?", blob.name) is None:
                                raise StorageFailure("UNSAFE_STORAGE")
                            owned_file(blob, WORKSPACE_BYTES); files.append(blob)
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
            self._observe("tombstone_cleanup", id)
            return entry.model_copy(deep=True)
