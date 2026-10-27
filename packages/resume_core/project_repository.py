"""Projects live in memory in the service process (D109).

The disk keeps one `workspace.json` per project, written atomically, the content-addressed sources, renders, images,
import history and template assets, and the `history.jsonl` undo journal. One lock per open project serializes every
write; a commit checks the base revision, applies a retried `clientMutationId` once (the file carries the last 200
ids), validates, writes the file and only then changes memory. The journal line follows; a failure there is a logged
gap, because the committed state is the file.
"""

from __future__ import annotations

import base64
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field, replace as replaced
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import threading

from .models.rich_workspace import RichMutationReplay
from .models.template_workspace import WorkspaceV7
from .project_journal import JournalStale, ProjectJournal, apply as apply_payloads, snapshot
from .project_limits import project_file_bytes
from .project_store import ProjectStore, ProjectStoreFailure, owned_file, strict_json
from .rich_limits import DOCX_BYTES, WORKSPACE_BYTES
from .storage import StorageFailure, atomic_write, locked_root, private_directory

REPLAY_WINDOW = 200
CLIPBOARD_CAPTURES = 20
OPEN_SESSIONS = 3
REPLACED_TOKENS = 16
LOG = logging.getLogger(__name__)
BLOB_KINDS = {'sources': '.bin', 'history': '.bin', 'template-assets': '.bin', 'renders': '.docx'}


class RepositoryFailure(Exception):
    """A refused repository operation; `code` is a public error code, `details` go into the reply body."""

    def __init__(self, code, **details):
        self.code = code
        self.details = details
        super().__init__(code)


def verifying():
    return os.environ.get('FOLDCV_VERIFY') == '1'


def rich_snapshot_bytes(workspace) -> bytes:
    """The exact bytes of a project file: V7 as sorted compact JSON, V6 as its model dump."""
    if workspace.schema_version == 7:
        raw = json.dumps(workspace.model_dump(mode='json', by_alias=True), sort_keys=True,
            ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    else:
        raw = workspace.model_dump_json(by_alias=True).encode('utf-8')
    if len(raw) > WORKSPACE_BYTES:
        raise ProjectStoreFailure('PROJECT_TOO_LARGE')
    return raw


def stored_owners(data):
    return [owner for owner in (data.get('project'), data.get('preDraft')) if isinstance(owner, dict)] if isinstance(data, dict) else []


def inline_history(data) -> bool:
    """A version 7 file written before D104 keeps import records or asset bytes in the workspace JSON."""
    if not isinstance(data, dict) or data.get('schemaVersion') != 7:
        return False
    project = data.get('project')
    return (isinstance(project, dict) and 'templateOperations' in project) or any(
        isinstance(asset, dict) and 'bytesBase64' in asset
        for owner in stored_owners(data) for asset in ((owner.get('templatePackage') or {}).get('assets') or []))


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
            blobs.append(('history', digest, raw, digest))
    if owner.template_package is not None:
        for asset in owner.template_package.assets:
            blobs.append(('template-assets', asset.sha256, base64.b64decode(asset.bytes_base64, validate=True), asset.sha256))
    return blobs


def blob_path(directory, kind, identifier):
    if kind == 'images':
        if re.fullmatch(r'images/[0-9a-f]{64}\.(?:png|jpg)', identifier) is None:
            raise StorageFailure('UNSAFE_STORAGE')
        return directory / identifier
    return directory / kind / (hashlib.sha256(identifier.encode('utf-8')).hexdigest() + BLOB_KINDS[kind])


def read_history_file(directory, digest):
    from .models.template_workspace import remember_history
    if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
        raise ProjectStoreFailure('PROJECT_LOAD_FAILED')
    path = blob_path(directory, 'history', digest)
    owned_file(path, WORKSPACE_BYTES)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ProjectStoreFailure('PROJECT_LOAD_FAILED')
    remember_history(digest, raw)
    return raw


def load_stored_data(directory, raw, *, history=False):
    """The JSON of a project file with its asset bytes remembered from the project's asset files and, when asked for,
    its import records read from its history files (D104)."""
    from .templates.models import asset_text, remember_asset
    data = strict_json(raw)
    for owner in stored_owners(data):
        for asset in ((owner.get('templatePackage') or {}).get('assets') or []):
            digest = asset.get('sha256') if isinstance(asset, dict) else None
            if isinstance(digest, str) and 'bytesBase64' not in asset and asset_text(digest) is None:
                path = blob_path(directory, 'template-assets', digest)
                owned_file(path, 20 * 1024 * 1024)
                remember_asset(digest, base64.b64encode(path.read_bytes()).decode('ascii'))
    project = data.get('project') if isinstance(data, dict) else None
    if history and isinstance(project, dict) and project.get('importHistory') and 'templateOperations' not in project:
        project['templateOperations'] = [strict_json(read_history_file(directory, ref.get('sha256')))
            for ref in project['importHistory'] if isinstance(ref, dict)]
    return data


def decode_project(directory, raw, *, history=False):
    data = load_stored_data(directory, raw, history=history)
    if not isinstance(data, dict) or type(data.get('schemaVersion')) is not int:
        raise ProjectStoreFailure('PROJECT_LOAD_FAILED')
    if data['schemaVersion'] != 7:
        raise ProjectStoreFailure('PROJECT_VERSION_UNSUPPORTED')
    return WorkspaceV7.model_validate(data)


def externalize_history(store, *, moved=None):
    """Move import records and asset bytes of files written before D104 into their own files, once, before any read.
    `moved(project, old_sha, new_sha)` lets an older service rebase state it keeps by file hash."""
    with locked_root(store.root, '.projects.lock'):
        if not store.projects.exists():
            return []
        result = []
        for directory in sorted(store.projects.iterdir()):
            target = directory / 'workspace.json'
            if not target.is_file() or target.is_symlink():
                continue
            owned_file(target)
            raw = target.read_bytes()
            try:
                if not inline_history(strict_json(raw)):
                    continue
                workspace = WorkspaceV7.model_validate(load_stored_data(directory, raw))
            except (ValueError, RecursionError):
                # An unreadable file stays as it is; opening that project reports it, the service still starts.
                continue
            for kind, identifier, blob, _checksum in history_blobs(workspace):
                path = blob_path(directory, kind, identifier)
                if not path.exists():
                    atomic_write(path, blob)
            slim = rich_snapshot_bytes(workspace)
            if moved is not None:
                moved(workspace.project_id, hashlib.sha256(raw).hexdigest(), hashlib.sha256(slim).hexdigest())
            atomic_write(target, slim)
            result.append(workspace.project_id)
        return result


@dataclass(frozen=True)
class EditOutcome:
    """What one commit did; a retried id gets the stored outcome back with `replayed`."""
    client_mutation_id: str
    request_sha256: str
    revision: int
    kind: str
    action_id: str | None = None
    details: dict = field(default_factory=dict)
    replayed: bool = False


@dataclass
class ProjectSession:
    project_id: str
    workspace: WorkspaceV7
    directory: Path
    journal: ProjectJournal
    lock: threading.RLock = field(default_factory=threading.RLock)
    editor_token: str | None = None
    replaced_tokens: list = field(default_factory=list)
    replays: OrderedDict = field(default_factory=OrderedDict)
    occupied_ids: set = field(default_factory=set)
    clipboard: OrderedDict = field(default_factory=OrderedDict)
    title: str = ''
    updated_at: str = ''
    file_key: tuple | None = None
    pins: int = 0
    registry_dirty: bool = False

    @property
    def revision(self):
        return self.workspace.project_revision

    def open_editor(self):
        """A fresh editor token; the previous one is now replaced (one active page per project, no takeover)."""
        with self.lock:
            if self.editor_token is not None:
                self.replaced_tokens = [*self.replaced_tokens, self.editor_token][-REPLACED_TOKENS:]
            self.editor_token = 'editor_' + secrets.token_urlsafe(24)
            return self.editor_token

    def require_editor(self, token):
        if token is not None and secrets.compare_digest(token, self.editor_token or ''):
            return
        if token is not None and any(secrets.compare_digest(token, value) for value in self.replaced_tokens):
            raise RepositoryFailure('EDITOR_REPLACED')
        raise RepositoryFailure('EDITOR_TOKEN_UNKNOWN')

    def remember_capture(self, identifier, value):
        self.clipboard[identifier] = value
        self.clipboard.move_to_end(identifier)
        while len(self.clipboard) > CLIPBOARD_CAPTURES:
            self.clipboard.popitem(last=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _key(path):
    status = os.stat(path, follow_symlinks=False)
    return (status.st_ino, status.st_size, status.st_mtime_ns)


class ProjectRepository:
    def __init__(self, root=None, *, clock=_now, open_limit=OPEN_SESSIONS):
        self.store = ProjectStore(root)
        self.root = self.store.root
        self.clock = clock
        self.open_limit = open_limit
        self.sessions: OrderedDict[str, ProjectSession] = OrderedDict()
        self.mutex = threading.RLock()
        # Registered by the import task (2.7): fold a current operation sidecar into every commit, discard it after.
        self.fold_hooks, self.committed_hooks = [], []
        self.started = False

    # Lifecycle and reads

    def start(self, *, moved=None):
        """Run the D104/D105 externalize pass once, before any project is opened."""
        if not self.started:
            try:
                externalize_history(self.store, moved=moved)
            except ProjectStoreFailure as error:
                raise RepositoryFailure(error.code) from None
            except (StorageFailure, OSError, ValueError):
                raise RepositoryFailure('PROJECT_LOAD_FAILED') from None
            self.started = True

    def _directory(self, project_id, create=False):
        try:
            return self.store._directory(project_id, create=create)
        except ProjectStoreFailure as error:
            raise RepositoryFailure(error.code) from None
        except StorageFailure:
            raise RepositoryFailure('PROJECT_UNSAFE_STORAGE') from None

    def _registry_entry(self, project_id):
        registry = self.store.registry()
        return next((entry for entry in registry.entries if entry.project_id == project_id), None)

    def listing(self):
        """Registry entries with the title and time of open sessions laid over them."""
        try:
            entries = [entry for entry in self.store.registry().entries if not entry.tombstoned]
        except ProjectStoreFailure as error:
            raise RepositoryFailure(error.code) from None
        with self.mutex:
            live = {identifier: (session.title, session.updated_at) for identifier, session in self.sessions.items()}
        result = []
        for entry in entries:
            if entry.project_id in live:
                title, updated = live[entry.project_id]
                entry = entry.model_copy(update={'title': title, 'updated_at': updated})
            result.append(entry)
        return result

    def open(self, project_id):
        with self.mutex:
            session = self.sessions.get(project_id)
            if session is not None:
                self.sessions.move_to_end(project_id)
                return session
        session = self._load(project_id)
        with self.mutex:
            existing = self.sessions.get(project_id)
            if existing is not None:
                return existing
            self.sessions[project_id] = session
            self._evict(keep=project_id)
            return session

    def _load(self, project_id):
        entry = self._registry_entry(project_id)
        if entry is None or entry.tombstoned:
            raise RepositoryFailure('PROJECT_DELETED' if entry is not None else 'PROJECT_NOT_FOUND')
        directory = self._directory(project_id)
        workspace, key = self._read_file(directory, project_id)
        journal = ProjectJournal.load(directory / 'history.jsonl')
        session = ProjectSession(project_id=project_id, workspace=workspace, directory=directory, journal=journal,
            title=workspace.title, updated_at=workspace.updated_at, file_key=key)
        self._seed(session)
        return session

    def _read_file(self, directory, project_id):
        path = directory / 'workspace.json'
        try:
            owned_file(path, WORKSPACE_BYTES)
            descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(descriptor, 'rb') as stream:
                before = os.fstat(stream.fileno())
                if before.st_nlink != 1 or before.st_uid != os.getuid() or before.st_mode & 0o077:
                    raise StorageFailure('UNSAFE_STORAGE')
                raw = stream.read(WORKSPACE_BYTES + 1)
                after = os.fstat(stream.fileno())
            if len(raw) > WORKSPACE_BYTES or (before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_ino, after.st_size, after.st_mtime_ns):
                raise StorageFailure('UNSAFE_STORAGE')
            workspace = decode_project(directory, raw)
        except ProjectStoreFailure as error:
            raise RepositoryFailure(error.code) from None
        except StorageFailure:
            raise RepositoryFailure('PROJECT_UNSAFE_STORAGE') from None
        except (OSError, ValueError, RecursionError):
            raise RepositoryFailure('PROJECT_LOAD_FAILED') from None
        if workspace.project_id != project_id:
            raise RepositoryFailure('PROJECT_UNSAFE_STORAGE')
        return workspace, (before.st_ino, before.st_size, before.st_mtime_ns)

    def _seed(self, session):
        from .template_preparation_ids import existing_ids
        session.replays = OrderedDict((row.client_mutation_id, EditOutcome(row.client_mutation_id, row.request_sha256,
            row.resulting_revision, 'edit', replayed=True)) for row in session.workspace.mutation_replay[-REPLAY_WINDOW:])
        session.occupied_ids = existing_ids(session.workspace)

    def _evict(self, *, keep):
        """Close least recently used sessions above the limit; a session with a held lock or a pin stays open."""
        for identifier, session in list(self.sessions.items()):
            if len(self.sessions) <= self.open_limit:
                return
            if identifier == keep or session.pins or not session.lock.acquire(blocking=False):
                continue
            try:
                self._close(session)
                self.sessions.pop(identifier, None)
            finally:
                session.lock.release()

    def close(self, project_id):
        with self.mutex:
            session = self.sessions.pop(project_id, None)
        if session is not None:
            with session.lock:
                self._close(session)

    def _close(self, session):
        if session.registry_dirty:
            self._write_registry_entry(session.workspace)
            session.registry_dirty = False
        session.journal.compact()
        try:
            self.sweep_assets(session.project_id, session=session)
        except RepositoryFailure:
            LOG.warning('asset sweep failed on close')

    def read(self, project_id):
        """The committed workspace; shared read-only, callers change copies only."""
        session = self.open(project_id)
        with session.lock:
            self._refresh_if_changed(session)
            return session.workspace

    @contextmanager
    def pinned(self, project_id):
        """Keep a project open while background work (import, export, assistant run) uses it."""
        session = self.open(project_id)
        with session.lock:
            session.pins += 1
        try:
            yield session
        finally:
            with session.lock:
                session.pins -= 1

    def _refresh_if_changed(self, session):
        """Adopt a file written outside this repository (an older service during the switch) instead of overwriting it."""
        try:
            key = _key(session.directory / 'workspace.json')
        except FileNotFoundError:
            raise RepositoryFailure('PROJECT_DELETED') from None
        if key == session.file_key:
            return
        LOG.warning('project file changed outside the repository; reloading')
        workspace, key = self._read_file(session.directory, session.project_id)
        session.workspace, session.file_key = workspace, key
        session.title, session.updated_at = workspace.title, workspace.updated_at
        self._seed(session)
        session.journal.barrier(revision_after=workspace.project_revision, reason='external_write')

    # Commits

    def mutate(self, project_id, *, base_revision, client_mutation_id, request_sha256, action_id, kind, build):
        """Commit `build(committed)` as one edit, undo or redo; see the module docstring for the protocol."""
        if kind not in {'edit', 'undo', 'redo'}:
            raise ValueError('unknown mutation kind')
        session = self.open(project_id)
        with session.lock:
            self._refresh_if_changed(session)
            stored = session.replays.get(client_mutation_id)
            if stored is not None:
                if stored.request_sha256 != request_sha256:
                    raise RepositoryFailure('MUTATION_ID_REUSED')
                return replaced(stored, replayed=True)
            self._require_revision(session, base_revision)
            before = session.workspace
            digest = _digest(before) if verifying() else None
            built = build(before)
            after, details = built if isinstance(built, tuple) else (built, {})
            if digest is not None and _digest(before) != digest:
                raise RuntimeError('build changed the committed workspace')
            if after is None:
                # No change: nothing is written and the id is not consumed.
                return EditOutcome(client_mutation_id, request_sha256, session.revision, kind, action_id, dict(details))
            return self._commit(session, after, client_mutation_id=client_mutation_id, request_sha256=request_sha256,
                action_id=action_id, kind=kind, details=dict(details))

    def replace(self, project_id, *, base_revision, workspace, blobs=(), action_id=None, reason='replace',
            client_mutation_id=None, request_sha256=None):
        """Commit a workspace computed outside the lock from `base_revision` (import publication, export record,
        metadata). Blobs are written first; undoable changes end the undo history with a barrier."""
        session = self.open(project_id)
        with session.lock:
            self._refresh_if_changed(session)
            if client_mutation_id is not None:
                stored = session.replays.get(client_mutation_id)
                if stored is not None:
                    if stored.request_sha256 != request_sha256:
                        raise RepositoryFailure('MUTATION_ID_REUSED')
                    return replaced(stored, replayed=True)
            self._require_revision(session, base_revision)
            return self._commit(session, workspace, client_mutation_id=client_mutation_id, request_sha256=request_sha256,
                action_id=action_id, kind='replace', details={}, blobs=tuple(blobs), reason=reason)

    def history(self, project_id, *, direction, base_revision, client_mutation_id, request_sha256, expected_action_id=None):
        """Undo or redo the top action through `mutate`: revision-checked, validated, saved and journaled."""
        session = self.open(project_id)
        with session.lock:
            stored = session.replays.get(client_mutation_id)
            if stored is not None:
                return self.mutate(project_id, base_revision=base_revision, client_mutation_id=client_mutation_id,
                    request_sha256=request_sha256, action_id=stored.action_id, kind=direction, build=lambda _workspace: None)
            top = session.journal.top(direction)
            if top is None or expected_action_id is not None and top.action_id != expected_action_id:
                raise RepositoryFailure('HISTORY_STALE', history=session.journal.state())
            def build(workspace):
                try:
                    action, payloads = session.journal.target(direction, snapshot(workspace))
                    rebuilt = apply_payloads(workspace, payloads)
                except JournalStale:
                    session.journal.barrier(revision_after=workspace.project_revision, reason='stale')
                    raise RepositoryFailure('HISTORY_STALE', history=session.journal.state()) from None
                return _advance(rebuilt, workspace, document=True), {'action': action}
            return self.mutate(project_id, base_revision=base_revision, client_mutation_id=client_mutation_id,
                request_sha256=request_sha256, action_id=top.action_id, kind=direction, build=build)

    def _require_revision(self, session, base_revision):
        if base_revision != session.revision:
            raise RepositoryFailure('REVISION_CONFLICT', revision=session.revision,
                appliedClientMutationIds=list(session.replays))

    def _commit(self, session, after, *, client_mutation_id, request_sha256, action_id, kind, details, blobs=(),
            reason=None):
        from .models.template_workspace import validated_with_history
        before = session.workspace
        if after.project_id != session.project_id or after.schema_version != 7:
            raise RepositoryFailure('JOB_SCOPE_INVALID')
        after = _advance(after, before)
        for fold in self.fold_hooks:
            after = fold(session, after) or after
        if after is before:
            raise RuntimeError('a commit needs a new workspace object')
        after.updated_at = self.clock()
        replay = list(before.mutation_replay)
        if client_mutation_id is not None:
            replay.append(RichMutationReplay(clientMutationId=client_mutation_id, requestSha256=request_sha256,
                resultingRevision=after.project_revision))
        after.mutation_replay = replay[-REPLAY_WINDOW:]
        try:
            after = validated_with_history(after)
        except ValueError:
            raise RepositoryFailure('PROJECT_SAVE_FAILED') from None
        try:
            raw = rich_snapshot_bytes(after)
        except ProjectStoreFailure as error:
            raise RepositoryFailure(error.code) from None
        if len(raw) > project_file_bytes():
            raise RepositoryFailure('PROJECT_TOO_LARGE')
        loaded = bool(after.project is not None and after.project.template_operations)
        try:
            with locked_root(self.root, '.projects.lock'):
                self._write_blobs(session.directory, [*history_blobs(after), *blobs] if loaded or blobs else ())
                target = session.directory / 'workspace.json'
                atomic_write(target, raw)
                key = _key(target)
        except RepositoryFailure:
            raise
        except ProjectStoreFailure as error:
            raise RepositoryFailure(error.code) from None
        except StorageFailure:
            raise RepositoryFailure('PROJECT_UNSAFE_STORAGE') from None
        except OSError:
            raise RepositoryFailure('PROJECT_SAVE_FAILED') from None
        if loaded:
            # Memory keeps the slim project a reopen would read; the records live in their history files.
            after = decode_project(session.directory, raw)
        elif verifying():
            if decode_project(session.directory, raw) != after:
                raise RuntimeError('written bytes decode to a different workspace')
        from .template_preparation_ids import existing_ids
        session.workspace, session.file_key = after, key
        session.occupied_ids |= existing_ids(after) if kind != 'edit' else _created(details)
        session.registry_dirty = True
        session.title, session.updated_at = after.title, after.updated_at
        outcome = EditOutcome(client_mutation_id or '', request_sha256 or '', after.project_revision, kind, action_id,
            {key: value for key, value in details.items() if key != 'action'})
        if client_mutation_id is not None:
            session.replays[client_mutation_id] = outcome
            while len(session.replays) > REPLAY_WINDOW:
                session.replays.popitem(last=False)
        for committed in self.committed_hooks:
            committed(session)
        self._journal(session, before, after, kind=kind, action_id=action_id, client_mutation_id=client_mutation_id,
            details=details, reason=reason)
        return outcome

    def _journal(self, session, before, after, *, kind, action_id, client_mutation_id, details, reason):
        try:
            if kind == 'edit':
                session.journal.record_edit(action_id=action_id, client_mutation_id=client_mutation_id,
                    revision_before=before.project_revision, revision_after=after.project_revision,
                    before=snapshot(before), after=snapshot(after))
            elif kind in {'undo', 'redo'}:
                session.journal.record_history(direction=kind, action=details['action'],
                    client_mutation_id=client_mutation_id, revision_before=before.project_revision,
                    revision_after=after.project_revision)
            elif snapshot(before) != snapshot(after):
                session.journal.barrier(revision_after=after.project_revision, reason=reason or 'replace')
        except Exception:
            # The committed state is the file; history restarts empty rather than failing the request.
            LOG.exception('journal gap')
            session.journal.undo, session.journal.redo, session.journal.open_seq = [], [], None

    def _write_blobs(self, directory, blobs):
        """Content-addressed files: written when missing, verified by hash when present."""
        from .models.template_workspace import remember_history
        for kind, identifier, blob, checksum in blobs:
            path = blob_path(directory, kind, identifier)
            if kind == 'history':
                remember_history(checksum, blob)
            if path.exists() or path.is_symlink():
                owned_file(path, DOCX_BYTES if kind == 'renders' else 32 * 1024 * 1024)
                if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                    raise RepositoryFailure('ARTIFACT_BYTES_MISMATCH' if kind == 'renders' else 'SOURCE_BYTES_MISMATCH')
            else:
                if hashlib.sha256(blob).hexdigest() != checksum:
                    raise RepositoryFailure('SOURCE_BYTES_MISMATCH')
                atomic_write(path, blob)

    # Projects as a whole

    def create(self, workspace, blobs=()):
        """Store a new project: blobs, workspace file, registry entry."""
        if workspace.schema_version != 7:
            raise RepositoryFailure('PROJECT_VERSION_UNSUPPORTED')
        try:
            raw = rich_snapshot_bytes(workspace)
            if len(raw) > project_file_bytes():
                raise RepositoryFailure('PROJECT_TOO_LARGE')
            with locked_root(self.root, '.projects.lock'):
                registry = self.store._registry()
                if any(entry.project_id == workspace.project_id for entry in registry.entries):
                    raise RepositoryFailure('PROJECT_EXISTS')
                directory = self.store._directory(workspace.project_id, create=True)
                if (directory / 'workspace.json').exists():
                    raise RepositoryFailure('PROJECT_EXISTS')
                self._write_blobs(directory, [*history_blobs(workspace), *blobs])
                atomic_write(directory / 'workspace.json', raw)
                self.store._upsert(registry, workspace)
                self.store._write_registry(registry)
        except RepositoryFailure:
            raise
        except ProjectStoreFailure as error:
            raise RepositoryFailure(error.code) from None
        except StorageFailure:
            raise RepositoryFailure('PROJECT_UNSAFE_STORAGE') from None
        except OSError:
            raise RepositoryFailure('PROJECT_SAVE_FAILED') from None
        return self.open(workspace.project_id)

    def _write_registry_entry(self, workspace):
        try:
            with locked_root(self.root, '.projects.lock'):
                registry = self.store._registry()
                self.store._upsert(registry, workspace)
                self.store._write_registry(registry)
        except ProjectStoreFailure as error:
            raise RepositoryFailure(error.code) from None
        except (StorageFailure, OSError):
            raise RepositoryFailure('PROJECT_SAVE_FAILED') from None

    def write_registry(self, project_id):
        """Write the session's title and time to the registry now (rename, archive flags, close)."""
        session = self.open(project_id)
        with session.lock:
            self._write_registry_entry(session.workspace)
            session.registry_dirty = False

    def delete(self, project_id):
        """Tombstone the project, drop its session and remove its files; the registry keeps the tombstone."""
        with self.mutex:
            session = self.sessions.pop(project_id, None)
        if session is not None:
            session.lock.acquire()
        try:
            try:
                entry = self.store.tombstone(project_id)
            except ProjectStoreFailure as error:
                raise RepositoryFailure(error.code) from None
            return self.cleanup_deleted(project_id) or entry
        finally:
            if session is not None:
                session.editor_token, session.replaced_tokens = None, []
                session.lock.release()

    def cleanup_deleted(self, project_id):
        with locked_root(self.root, '.projects.lock'):
            registry = self.store._registry()
            entry = next((item for item in registry.entries if item.project_id == project_id), None)
            if entry is None or not entry.tombstoned:
                raise RepositoryFailure('PROJECT_NOT_DELETED')
            directory = self.store.projects / project_id
            try:
                if directory.exists() or directory.is_symlink():
                    marker = directory / '.project-identity.json'
                    if not marker.exists() and not directory.is_symlink() and directory.is_dir() and not any(directory.iterdir()):
                        # A prior cleanup can remove the identity before an empty-directory removal fails.
                        private_directory(directory)
                        directory.rmdir()
                    else:
                        directory = self.store._directory(project_id)
                        _remove_project_files(directory)
                entry.cleanup_status = 'complete'
            except (OSError, StorageFailure, ProjectStoreFailure):
                entry.cleanup_status = 'failed'
            self.store._write_registry(registry)
            return entry.model_copy(deep=True)

    def sweep_assets(self, project_id, *, session=None):
        """Remove image files that neither the project nor its undo history references."""
        session = session or self.open(project_id)
        folder = session.directory / 'images'
        if not folder.exists():
            return []
        keep = {asset.path for asset in session.workspace.project.assets} if session.workspace.project else set()
        for action in [*session.journal.undo, *session.journal.redo]:
            for side in (action.before, action.after):
                for value in side.values():
                    keep |= set(re.findall(r'images/[0-9a-f]{64}\.(?:png|jpg)', json.dumps(value))) if value else set()
        removed = []
        try:
            private_directory(folder)
            for path in folder.iterdir():
                if re.fullmatch(r'[0-9a-f]{64}\.(?:png|jpg)', path.name) is None:
                    raise StorageFailure('UNSAFE_STORAGE')
                if 'images/' + path.name not in keep:
                    owned_file(path, 20 * 1024 * 1024)
                    path.unlink()
                    removed.append(path.name)
        except (OSError, StorageFailure):
            raise RepositoryFailure('PROJECT_UNSAFE_STORAGE') from None
        return removed


def _remove_project_files(directory):
    marker = directory / '.project-identity.json'
    files, folders = [], []
    for path in directory.iterdir():
        if path.name in {'workspace.json', '.project-identity.json', 'history.jsonl'}:
            owned_file(path, 2 * WORKSPACE_BYTES); files.append(path)
        elif path.name in {'sources', 'renders', 'images', 'history', 'template-assets'}:
            private_directory(path)
            suffix = {'sources': 'bin', 'renders': '(?:docx|foldcv)', 'images': '(?:png|jpg)', 'history': 'bin',
                'template-assets': 'bin'}[path.name]
            for blob in path.iterdir():
                if re.fullmatch(r'[0-9a-f]{64}\.' + suffix, blob.name) is None:
                    raise StorageFailure('UNSAFE_STORAGE')
                owned_file(blob, DOCX_BYTES); files.append(blob)
            folders.append(path)
        elif path.name == 'imports':
            private_directory(path)
            for blob in path.iterdir():
                if re.fullmatch(r'[A-Za-z0-9_-]{1,128}\.json(?:\.tmp)?', blob.name) is None:
                    raise StorageFailure('UNSAFE_STORAGE')
                owned_file(blob, WORKSPACE_BYTES); files.append(blob)
            folders.append(path)
        elif path.name.startswith('.foldcv-write-'):
            files.append(path)
        else:
            raise StorageFailure('UNSAFE_STORAGE')
    for path in files:
        if path != marker:
            path.unlink()
    for path in folders:
        path.rmdir()
    if marker.exists():
        marker.unlink()
    directory.rmdir()


def _digest(workspace):
    from .templates.compiler import canonical
    return hashlib.sha256(canonical(workspace)).hexdigest()


def _created(details):
    return {identifier for slots in (details.get('created_ids') or {}).values() for identifier in slots.values()}


def _advance(after, before, *, document=False):
    """Revisions only move forward: the project revision always, the document revision when the document changed."""
    project_revision = max(after.project_revision, before.project_revision + 1)
    document_revision = after.document_revision
    if document or after.project is not None and before.project is not None and after.project.document != before.project.document:
        document_revision = max(after.document_revision, before.document_revision + 1)
    if (project_revision, document_revision) == (after.project_revision, after.document_revision):
        return after
    after = after.model_copy()
    after.project_revision, after.document_revision = project_revision, document_revision
    if after.project is not None:
        project = after.project.model_copy()
        project.revision = project_revision
        document = project.document.model_copy()
        document.revision = document_revision
        project.document = document
        after.project = project
    return after
