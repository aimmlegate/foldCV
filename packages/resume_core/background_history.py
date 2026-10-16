"""Durable scoped history; content equality cannot erase a relevant intervening write."""

from __future__ import annotations

from .agent_store import AgentFailure, digest
from .background_store import BackgroundFailure, identity
from .models.background import BackgroundHistoryV1, GenerationStamp, HistoryDefinitionV1, JobFailure, ScopeGuardV1
from .project_store import encoded, owned_file, strict_json
from .rich_dependencies import dependency
from .rich_project_store import RichProjectStore, rich_snapshot_bytes
from .storage import StorageFailure, atomic_write

NAMESPACE = "history.namespace"
CLOCK = "history.clock"


def selector_key(selector):
    value = ({"kind": "entity", "type": selector.stamp.kind, "id": selector.stamp.id} if selector.kind == "entity"
        else {"kind": "query", "query": selector.query.model_dump(mode="json", by_alias=True, exclude={"cursor"})})
    return selector.kind + ":" + digest(value)


def scope_kind(selector):
    if selector.kind == "query":
        return "query"
    kind = selector.stamp.kind
    return "structure" if kind in {"ownership", "timeline_order"} else kind if kind in {"source", "rules"} else "entity"


class ScopeHistory:
    def __init__(self, jobs, query_fingerprint, *, observer=lambda _name, _project: None):
        self.jobs, self.query_fingerprint, self.observer = jobs, query_fingerprint, observer
        self.canonical = RichProjectStore(jobs.root)

    def _fence(self, project):
        self.jobs.fences.setdefault(project, "OUTCOME_UNKNOWN")
        raise BackgroundFailure("OUTCOME_UNKNOWN")

    @staticmethod
    def _stamp(state, key):
        matches = [stamp for stamp in state.generations if stamp.key == key]
        if len(matches) != 1:
            raise ValueError("missing or duplicate history stamp")
        return matches[0]

    def _activation(self, state):
        return {"schemaVersion": 1, "projectId": state.project_id, "lineage": state.lineage,
            "namespace": state.history.namespace}

    def _ready(self, state, directory, checksum):
        try:
            if state.history is None or state.history.phase != "ready" or state.history.workspace_sha256 != checksum:
                raise ValueError("history is unavailable for these canonical bytes")
            if state.history_namespace is not None and state.history_namespace != state.history.namespace:
                raise ValueError("history namespace changed")
            path = directory / "history-activation.json"
            owned_file(path, 8192)
            if strict_json(path.read_bytes()) != self._activation(state):
                raise ValueError("history activation mismatch")
            marker, clock = self._stamp(state, NAMESPACE), self._stamp(state, CLOCK)
            if (marker.kind != "rules" or marker.generation != 1 or marker.fingerprint != digest(state.history.namespace)
                    or clock.kind != "rules" or clock.fingerprint != marker.fingerprint):
                raise ValueError("history namespace mismatch")
            expected = {definition.key for definition in state.history.definitions} | {NAMESPACE, CLOCK}
            if {stamp.key for stamp in state.generations} != expected or len(state.generations) != len(expected):
                raise ValueError("history definitions and values differ")
            if any(definition.key != selector_key(definition.selector) or
                    self._stamp(state, definition.key).kind != scope_kind(definition.selector) for definition in state.history.definitions):
                raise ValueError("history selector identity changed")
            if any(stamp.generation > clock.generation for stamp in state.generations):
                raise ValueError("history ordinal rolled backwards")
        except (OSError, StorageFailure, ValueError):
            self._fence(state.project_id)

    def open(self, project):
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            _workspace, checksum = self.canonical._read_committed_unlocked(project)
            path = directory / "history-activation.json"
            if state.history is None:
                if (state.history_namespace is not None or path.exists() or path.is_symlink() or state.generations or state.intents or state.manual_intents or state.inverses
                        or any(job.receipt is not None or job.submission.guards.reads or job.submission.guards.writes for job in state.jobs)
                        or any(proposal.guards.reads or proposal.guards.writes for proposal in state.proposals)):
                    self._fence(project)
                namespace = identity("history")
                state.history = BackgroundHistoryV1(schemaVersion=1, namespace=namespace, phase="initializing",
                    workspaceSha256=checksum, definitions=[])
                state.history_namespace = namespace
                state.generations = [GenerationStamp(kind="rules", key=key, generation=1,
                    fingerprint=digest(namespace)) for key in (NAMESPACE, CLOCK)]
                # Interim proposals have no history authority; retain their immutable payloads.
                for job in state.jobs:
                    if job.publication in {"ready", "waiting_for_sync"}:
                        job.publication = "needs_review"
                        job.publication_error = JobFailure(code="DEPENDENCY_CHANGED")
                        job.event_cursor += 1
                        job.updated_at = self.jobs.clock()
                self.jobs._write(directory, state, self.jobs._all())
                self.observer("history_initializing", project)
            if state.history.phase == "initializing":
                if state.history.definitions:
                    self._fence(project)
                raw = encoded(self._activation(state))
                if path.exists():
                    owned_file(path, 8192)
                    if path.read_bytes() != raw:
                        self._fence(project)
                self.jobs._capacity(state, self.jobs._all(), replacing=(path, len(raw)))
                atomic_write(path, raw)
                self.jobs._sync_namespace(path)
                self.observer("history_activation_durable", project)
                state.history.workspace_sha256, state.history.phase = checksum, "ready"
                self.jobs._write(directory, state, self.jobs._all())
                self.observer("history_ready", project)
            if state.history_namespace is None:
                state.history_namespace = state.history.namespace
                self.jobs._write(directory, state, self.jobs._all())
            self._ready(state, directory, checksum)
            return state.history.model_copy(deep=True)

    def fingerprint(self, workspace, selector, *, missing=False):
        try:
            if selector.kind == "entity":
                return dependency(workspace, selector.stamp.kind, selector.stamp.id).fingerprint
            return self.query_fingerprint(workspace, selector.query)
        except AgentFailure as error:
            if not missing or error.code != "AGENT_NOT_FOUND":
                raise BackgroundFailure("DEPENDENCY_CHANGED") from None
        except ValueError as error:
            if not missing or str(error) != "DEPENDENCY_MISSING":
                raise BackgroundFailure("DEPENDENCY_CHANGED") from None
        return digest({"missing": selector_key(selector)})

    def observe(self, project, reader, *, job_id=None):
        """reader returns a materialized value and dependencies without I/O or waits."""
        self.open(project)
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            workspace, checksum = self.canonical._read_committed_unlocked(project)
            self._ready(state, directory, checksum)
            if any(intent.phase not in {"receipt_stored", "reconciled"} for intent in [*state.intents, *state.manual_intents]):
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            value, selectors = reader(workspace)
            if job_id is not None:
                from .background_assets import pin_snapshot
                from .background_store import job_in
                job = job_in(state, job_id)
                previous = job.asset_pins_sha256
                pin_snapshot(state, self.canonical, workspace, "job", job_id, extend=True)
                if job.asset_pins_sha256 != previous:
                    job.event_cursor += 1
                    job.updated_at = self.jobs.clock()
            guards = self.register(state, workspace, selectors)
            self.jobs._write(directory, state, self.jobs._all())
            self.observer("history_capture_durable", project)
            return value, guards

    def register(self, state, workspace, selectors, *, write=False):
        guards = {NAMESPACE: self._stamp(state, NAMESPACE).model_copy(deep=True)}
        clock = self._stamp(state, CLOCK)
        for selector in selectors:
            key, actual = selector_key(selector), self.fingerprint(workspace, selector, missing=write)
            expected = selector.stamp.fingerprint if selector.kind == "entity" else selector.fingerprint
            if expected is not None and expected != actual:
                raise BackgroundFailure("DEPENDENCY_CHANGED")
            definition = next((item for item in state.history.definitions if item.key == key), None)
            if definition is None:
                clock.generation += 1
                state.history.definitions.append(HistoryDefinitionV1(key=key, selector=selector))
                state.generations.append(GenerationStamp(kind=scope_kind(selector), key=key,
                    generation=clock.generation, fingerprint=actual))
            stamp = self._stamp(state, key)
            if stamp.kind != scope_kind(selector) or stamp.fingerprint != actual:
                self._fence(state.project_id)
            guards[key] = stamp.model_copy(deep=True)
        if len(guards) > 100:
            raise BackgroundFailure("JOB_STORAGE_FULL")
        values = list(guards.values())
        return ScopeGuardV1(schemaVersion=1, reads=[] if write else values, writes=values if write else [])

    def validate(self, state, directory, workspace, guards):
        self._ready(state, directory, digest_bytes(workspace))
        captured = [*guards.reads, *guards.writes]
        marker = self._stamp(state, NAMESPACE)
        if marker not in captured:
            raise BackgroundFailure("DEPENDENCY_CHANGED")
        for expected in captured:
            try:
                current = self._stamp(state, expected.key)
            except ValueError:
                raise BackgroundFailure("DEPENDENCY_CHANGED") from None
            if expected != current:
                raise BackgroundFailure("DEPENDENCY_CHANGED")
            if expected.key not in {NAMESPACE, CLOCK}:
                definition = next((item for item in state.history.definitions if item.key == expected.key), None)
                if definition is None or self.fingerprint(workspace, definition.selector, missing=True) != current.fingerprint:
                    self._fence(state.project_id)
        return True

    def advance(self, state, before, after, *, touches=frozenset()):
        if state.history is None or state.history.phase != "ready" or state.history.workspace_sha256 != digest_bytes(before):
            self._fence(state.project_id)
        clock = self._stamp(state, CLOCK)
        clock.generation += 1
        for definition in state.history.definitions:
            previous = self.fingerprint(before, definition.selector, missing=True)
            current = self.fingerprint(after, definition.selector, missing=True)
            stamp = self._stamp(state, definition.key)
            if stamp.fingerprint != previous:
                self._fence(state.project_id)
            if previous != current or definition.key in touches:
                stamp.generation, stamp.fingerprint = clock.generation, current
        state.history.workspace_sha256 = digest_bytes(after)


def digest_bytes(workspace):
    import hashlib
    return hashlib.sha256(rich_snapshot_bytes(workspace)).hexdigest()
