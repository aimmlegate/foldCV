"""Local catalog state, independent of portable workspace versions."""

from contextlib import contextmanager
from datetime import datetime, timezone
import logging
import os
import threading

from pydantic import Field

from . import host
from .models.contracts import Wire
from .project_store import ProjectStoreFailure, owned_file, strict_json
from .storage import StorageFailure, atomic_write, locked_root

LOG = logging.getLogger(__name__)


class CatalogEntry(Wire):
    last_opened_at: str | None = None
    archived: bool = False
    read_only: bool = False
    access_revision: int = Field(default=1, ge=1)


class CatalogState(Wire):
    schema_version: int = Field(default=1, ge=1, le=1)
    entries: dict[str, CatalogEntry] = Field(default_factory=dict)
    actions: dict[str, str] = Field(default_factory=dict)


class AccessChanged(Exception):
    pass


class ProjectCatalog:
    def __init__(self, storage):
        self.storage, self.root = storage, storage.root
        self.path = self.root / "catalog.json"
        self.mutex, self.local = threading.RLock(), threading.local()

    @contextmanager
    def _lock(self):
        with self.mutex:
            if getattr(self.local, "held", False):
                yield
                return
            with locked_root(self.root, ".catalog.lock"):
                self.local.held = True
                try:
                    yield
                finally:
                    self.local.held = False

    def _read(self):
        if not self.path.exists() and not self.path.is_symlink():
            return CatalogState()
        try:
            owned_file(self.path, 4 * 1024 * 1024)
            return CatalogState.model_validate(strict_json(self.path.read_bytes()))
        except (StorageFailure, OSError, ValueError, RecursionError) as error:
            # Only recency and flags live here: a damaged file costs those, never the projects.
            LOG.warning('catalog unreadable, treated as empty: %s', type(error).__name__)
            return CatalogState()

    def _write(self, raw):
        try:
            atomic_write(self.path, raw)
        except (StorageFailure, OSError):
            raise ProjectStoreFailure("PROJECT_SAVE_FAILED") from None

    def _owned(self, identifier):
        entry = next((entry for entry in self.storage.registry().entries if entry.project_id == identifier), None)
        if entry is None or entry.tombstoned:
            raise ProjectStoreFailure("PROJECT_NOT_FOUND")
        self.storage._directory(identifier)

    def entries(self):
        with self._lock():
            return self._read().entries

    def get(self, identifier):
        return self.entries().get(identifier, CatalogEntry())

    def update(self, identifier, *, opened=False, archived=None, read_only=None, expected_revision=None):
        with self._lock():
            self._owned(identifier)
            state = self._read()
            entry = state.entries.setdefault(identifier, CatalogEntry())
            if expected_revision is not None and entry.access_revision != expected_revision:
                raise AccessChanged()
            if opened:
                entry.last_opened_at = datetime.now(timezone.utc).isoformat()
            if archived is not None:
                entry.archived = archived
            if read_only is not None and entry.read_only != read_only:
                entry.read_only = read_only
                entry.access_revision += 1
            self._write(state.model_dump_json(by_alias=True).encode())
            return entry.model_copy(deep=True)

    @contextmanager
    def authority(self, identifier, revision):
        # Hold authority through the durable commit so toggles cannot race publication.
        with self._lock():
            entry = self._read().entries.get(identifier, CatalogEntry())
            if entry.read_only or entry.access_revision != revision:
                raise AccessChanged()
            yield

    def require_write(self, identifier, revision):
        with self.authority(identifier, revision):
            pass

    def actions(self, *, synchronize=False):
        import json
        with self._lock():
            state = self._read()
            if synchronize and self.path.exists():
                with self.path.open("rb") as stream:
                    os.fsync(stream.fileno())
                host.sync_directory(self.root)
            return {key: json.loads(value) for key, value in state.actions.items()}

    def record_action(self, key, value):
        import json
        with self._lock():
            state = self._read()
            if key not in state.actions and len(state.actions) >= 500:
                raise ProjectStoreFailure("PROJECT_TOO_LARGE")
            state.actions[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            raw = state.model_dump_json(by_alias=True).encode()
            if len(raw) > 4 * 1024 * 1024:
                raise ProjectStoreFailure("PROJECT_TOO_LARGE")
            self._write(raw)

    def reserve_action(self, key, value):
        # The reservation also holds space for a terminal result at the byte limit.
        self.record_action(key, {**value, "receiptReserve": " " * 1024})

    def archive_action(self, identifier, archived, key, value):
        import json
        with self._lock():
            self._owned(identifier)
            state = self._read()
            if key not in state.actions and len(state.actions) >= 500:
                raise ProjectStoreFailure("PROJECT_TOO_LARGE")
            state.entries.setdefault(identifier, CatalogEntry()).archived = archived
            state.actions[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            raw = state.model_dump_json(by_alias=True).encode()
            if len(raw) > 4 * 1024 * 1024:
                raise ProjectStoreFailure("PROJECT_TOO_LARGE")
            self._write(raw)
