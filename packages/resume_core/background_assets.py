"""Owned blob pins and delayed reclamation share the canonical lifecycle guard."""

from datetime import datetime
import hashlib
import os
import re

from .background_limits import LIMITS
from .background_store import BackgroundFailure
from .models.background import AssetPinV1, AssetReferenceV1, OrphanAssetV1
from .project_store import owned_file
from .rich_project_store import RichProjectStore


def elapsed(now, since):
    return (datetime.fromisoformat(now.replace("Z", "+00:00")) - datetime.fromisoformat(since.replace("Z", "+00:00"))).total_seconds()


def pin_snapshot(state, canonical, workspace, kind, owner, *, images=None, sources=None, extend=False):
    project, collection = workspace.project, workspace.project or workspace.pre_draft
    references = []
    for asset in project.assets if project else []:
        if images is None or asset.id in images:
            references.append(AssetReferenceV1(kind="image", id=asset.id, path=asset.path, sha256=asset.sha256, size=asset.size))
    for source in collection.sources:
        if sources is None or source.id in sources:
            path = canonical._blob(canonical._directory(workspace.project_id), "sources", source.id)
            references.append(AssetReferenceV1(kind="source", id=source.id, path="sources/" + path.name,
                sha256=source.byte_sha256, size=path.stat().st_size))
    if images is not None and set(images) - {item.id for item in references if item.kind == "image"}:
        raise BackgroundFailure("JOB_SCOPE_INVALID")
    if sources is not None and set(sources) - {item.id for item in references if item.kind == "source"}:
        raise BackgroundFailure("JOB_SCOPE_INVALID")
    unique = {(item.kind, item.path): item for item in references}
    directory = canonical._directory(workspace.project_id)
    for item in unique.values():
        path = directory / item.path
        owned_file(path, 32 * 1024 * 1024)
        raw = path.read_bytes()
        if len(raw) != item.size or hashlib.sha256(raw).hexdigest() != item.sha256:
            raise BackgroundFailure("OUTCOME_UNKNOWN")
    if len(unique) > 100:
        raise BackgroundFailure("JOB_STORAGE_FULL")
    pin = AssetPinV1(kind=kind, owner=owner, references=list(unique.values()))
    previous = next((item for item in state.asset_pins if (item.kind, item.owner) == (kind, owner)), None)
    if previous is not None:
        if extend:
            combined = {(ref.kind, ref.path): ref for ref in previous.references}
            for ref in pin.references:
                if (ref.kind, ref.path) in combined and combined[(ref.kind, ref.path)] != ref:
                    raise BackgroundFailure("OUTCOME_UNKNOWN")
                combined[(ref.kind, ref.path)] = ref
            if len(combined) > 100:
                raise BackgroundFailure("JOB_STORAGE_FULL")
            previous.references = list(combined.values())
            pin = previous
        elif previous != pin:
            raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
    elif pin.references:
        state.asset_pins.append(pin)
    if pin.references:
        from .agent_store import digest
        checksum = digest([ref.model_dump(mode="json", by_alias=True) for ref in pin.references])
        if kind == "job":
            from .background_store import job_in
            job_in(state, owner).asset_pins_sha256 = checksum
        elif kind == "inverse":
            next(item for item in state.inverses if item.proposal_id == owner).asset_pins_sha256 = checksum
    return pin


def guard_removal(state, before, after):
    retained = {asset.path for asset in after.project.assets} if after.project else set()
    previous = {asset.path for asset in before.project.assets} if before.project else set()
    for value, paths in ((before, previous), (after, retained)):
        paths.update("sources/" + hashlib.sha256(source.id.encode()).hexdigest() + ".bin"
            for source in (value.project or value.pre_draft).sources)
    pinned = {ref.path for pin in state.asset_pins for ref in pin.references}
    if (previous - retained) & pinned:
        raise BackgroundFailure("DEPENDENCY_CHANGED")


def release_resolved_jobs(state):
    from .background_store import RESOLVED_PUBLICATION, TERMINAL_EXECUTION
    eligible = {job.id for job in state.jobs if job.execution in TERMINAL_EXECUTION
        and job.publication in RESOLVED_PUBLICATION - {"none"} and all(attempt.cleanup_verified for attempt in job.attempts)}
    state.asset_pins = [pin for pin in state.asset_pins if pin.kind != "job" or pin.owner not in eligible]
    for job in state.jobs:
        if job.id in eligible:
            job.asset_pins_sha256 = None


class JobAssets:
    def __init__(self, jobs):
        self.jobs, self.canonical = jobs, RichProjectStore(jobs.root)

    @staticmethod
    def readable(state, jobs):
        if state.project_id in jobs.fences or any(intent.phase not in {"receipt_stored", "reconciled"}
                for intent in [*state.intents, *state.manual_intents]):
            raise BackgroundFailure("OUTCOME_UNKNOWN")

    def capture(self, project, kind, owner, *, images=None, sources=None):
        self.jobs.open(project)
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            self.readable(state, self.jobs)
            workspace, checksum = self.canonical._read_committed_unlocked(project, synchronize=True)
            self._ready(state, directory, checksum)
            pin_snapshot(state, self.canonical, workspace, kind, owner, images=images, sources=sources)
            self.jobs._write(directory, state, self.jobs._all())
            return workspace, checksum

    def _ready(self, state, directory, checksum):
        if state.history is not None or (directory / "history-activation.json").exists():
            from .background_history import ScopeHistory
            ScopeHistory(self.jobs, None)._ready(state, directory, checksum)

    def release(self, project, kind, owner):
        if kind not in {"export", "session"}:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        entry = next((entry for entry in self.jobs.canonical.registry().entries if entry.project_id == project), None)
        with self.jobs.guard(project, deleted=bool(entry and entry.tombstoned)) as directory:
            state = self.jobs._read(project, directory)
            state.asset_pins = [pin for pin in state.asset_pins if (pin.kind, pin.owner) != (kind, owner)]
            self.jobs._write(directory, state, self.jobs._all())

    def session(self, project, owner, images, *, closed=False, previous=None):
        self.jobs.open(project)
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            self.readable(state, self.jobs)
            state.asset_pins = [pin for pin in state.asset_pins if pin.kind != "session" or pin.owner not in {owner, previous}]
            workspace, checksum = self.canonical._read_committed_unlocked(project)
            self._ready(state, directory, checksum)
            if not closed:
                pin_snapshot(state, self.canonical, workspace, "session", owner, images=images, sources=[])
            self.jobs._write(directory, state, self.jobs._all())

    def bytes_for(self, project, kind, owner):
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            pin = next((item for item in state.asset_pins if (item.kind, item.owner) == (kind, owner)), None)
            images, sources = {}, {}
            for ref in pin.references if pin else []:
                path = self.canonical._directory(project) / ref.path
                owned_file(path, 32 * 1024 * 1024)
                raw = path.read_bytes()
                if len(raw) != ref.size or hashlib.sha256(raw).hexdigest() != ref.sha256:
                    raise BackgroundFailure("OUTCOME_UNKNOWN")
                (images if ref.kind == "image" else sources)[ref.id] = raw
            return images, sources

    def collectable(self, project, live):
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            self.readable(state, self.jobs)
            workspace, checksum = self.canonical._read_committed_unlocked(project)
            self._ready(state, directory, checksum)
            pinned = {ref.path for pin in state.asset_pins for ref in pin.references}
            from .models.rich_document import ImageBlock
            live = set(live) | ({block.props.asset_id for block in workspace.project.document.blocks()
                if isinstance(block, ImageBlock)} if workspace.project else set())
            keep = {asset.path for asset in workspace.project.assets if asset.id in live} if workspace.project else set()
            candidates = {asset.path: asset.id for asset in workspace.project.assets if asset.path not in keep} if workspace.project else {}
            self._orphans(state, set(candidates) - pinned, keep | pinned)
            due = {item.path for item in state.orphan_assets if elapsed(self.jobs.clock(), item.orphaned_at) >= LIMITS.orphan_asset_seconds}
            self.jobs._write(directory, state, self.jobs._all())
            return {identifier for path, identifier in candidates.items() if path in due and path not in pinned}

    def _orphans(self, state, candidates, keep):
        state.orphan_assets = [item for item in state.orphan_assets if item.path not in keep]
        known = {item.path for item in state.orphan_assets}
        state.orphan_assets.extend(OrphanAssetV1(path=path, orphanedAt=self.jobs.clock()) for path in sorted(candidates - known))

    def reclaim_blobs(self, project):
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            self.readable(state, self.jobs)
            workspace, checksum = self.canonical._read_committed_unlocked(project)
            self._ready(state, directory, checksum)
            keep = {ref.path for pin in state.asset_pins for ref in pin.references}
            active = set(keep)
            from .models.rich_document import ImageBlock
            live = {block.props.asset_id for block in workspace.project.document.blocks()
                if isinstance(block, ImageBlock)} if workspace.project else set()
            active.update(asset.path for asset in (workspace.project.assets if workspace.project else []) if asset.id in live)
            keep.update(asset.path for asset in (workspace.project.assets if workspace.project else []))
            collection = workspace.project or workspace.pre_draft
            canonical = self.canonical._directory(project)
            keep.update("sources/" + self.canonical._blob(canonical, "sources", source.id).name for source in collection.sources)
            active.update("sources/" + self.canonical._blob(canonical, "sources", source.id).name for source in collection.sources)
            paths = {}
            for kind, pattern in (("images", r"[0-9a-f]{64}\.(?:png|jpg)"), ("sources", r"[0-9a-f]{64}\.bin")):
                folder = canonical / kind
                if not folder.exists():
                    continue
                if folder.is_symlink():
                    raise BackgroundFailure("JOB_STORE_CORRUPT")
                for path in folder.iterdir():
                    if re.fullmatch(pattern, path.name) is None:
                        raise BackgroundFailure("JOB_STORE_CORRUPT")
                    owned_file(path, 32 * 1024 * 1024)
                    paths[kind + "/" + path.name] = path
            self._orphans(state, paths.keys() - keep, active)
            self.jobs._write(directory, state, self.jobs._all())
            removed = set()
            for item in state.orphan_assets:
                if item.path in paths and item.path not in keep and elapsed(self.jobs.clock(), item.orphaned_at) >= LIMITS.orphan_asset_seconds:
                    paths[item.path].unlink()
                    fd = os.open(paths[item.path].parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                    removed.add(item.path)
            state.orphan_assets = [item for item in state.orphan_assets if item.path not in removed]
            self.jobs._write(directory, state, self.jobs._all())
            return removed
