"""Owned image ingestion with session history references and late-result guards."""

import asyncio
from dataclasses import dataclass, field

from packages.resume_core.gui_archive_zip import ArchiveFailure
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.rich_document import ImageBlock
from packages.resume_core.rich_api import ImageSessionRequest, ImageUploadCapture
from packages.resume_core.rich_archive import archive_payload
from packages.resume_core.rich_asset_lifecycle import ImageOwner, ImageRetention
from packages.resume_core.rich_images import ImageFailure, normalize_image
from packages.resume_core.rich_limits import ImageReferences
from packages.resume_core.rich_project_store import rich_snapshot_bytes
from packages.resume_core.rich_snapshot_merge import reconcile
from packages.resume_core.project_store import ProjectStoreFailure
from .gui_projects import ProjectFailure


@dataclass
class ImageSession:
    revision: int
    live: tuple[str, ...]
    history: tuple[str, ...]
    pending: set[str] = field(default_factory=set)
    closed: bool = False


def image_ids(workspace):
    return tuple(block.props.asset_id for block in workspace.project.document.blocks() if isinstance(block, ImageBlock)) if workspace.project else ()


class RichAssets:
    def initialize_images(self):
        self.image_sessions = {}
        self.image_reservations = {}
        self.image_tasks = set()

    def image_references(self, identifier):
        sessions = [session for (pid, _), session in self.image_sessions.items() if pid == identifier and not session.closed]
        live = image_ids(self.workspaces[identifier])
        return ImageReferences(live=live, durable=live,
            history=tuple({asset for session in sessions for asset in (*session.history, *session.live, *session.pending)}))

    def update_image_session(self, identifier, request):
        with self.state_lock:
            self.require_agent_writable(identifier)
            workspace = self.read(identifier)
            if workspace.project is None:
                raise ProjectFailure("DOCUMENT_NOT_CREATED")
            key = (identifier, request.session_id)
            previous = self.image_sessions.get(key)
            if previous is None and request.previous_session_id:
                old = self.image_sessions.get((identifier, request.previous_session_id))
                if old:
                    old.closed = True
            if previous and (previous.closed or request.revision < previous.revision):
                raise ProjectFailure("STALE_IMAGE_SESSION")
            if previous and request.revision == previous.revision and not request.closed and (
                    tuple(request.live) != previous.live or tuple(request.history) != previous.history):
                raise ProjectFailure("STALE_IMAGE_SESSION")
            if previous and request.revision == previous.revision and not request.closed:
                return
            assets = {asset.id for asset in workspace.project.assets}
            if not set((*request.live, *request.history)) <= assets:
                raise ProjectFailure("IMAGE_REFERENCE_MISSING", 422)
            session = ImageSession(request.revision, tuple(request.live), tuple(request.history), closed=request.closed)
            jobs = getattr(self, "background_jobs", None)
            if jobs is not None and jobs.enabled:
                from packages.resume_core.agent_store import digest
                from packages.resume_core.background_assets import JobAssets
                from packages.resume_core.background_store import BackgroundFailure
                try:
                    JobAssets(jobs.store).session(identifier, "session_" + digest(request.session_id)[:40],
                        set((*request.live, *request.history)), closed=request.closed,
                        previous="session_" + digest(request.previous_session_id)[:40] if request.previous_session_id else None)
                except BackgroundFailure as error:
                    raise ProjectFailure(error.code, 409) from None
            self.image_sessions[key] = session
            self.reclaim_images(identifier)

    def reclaim_images(self, identifier):
        workspace = self.workspaces[identifier]
        if not workspace.project or any(pid == identifier for pid, _ in self.image_reservations):
            return
        refs = self.image_references(identifier)
        keep = set((*refs.live, *refs.durable, *refs.history, *refs.in_flight))
        jobs = getattr(self, "background_jobs", None)
        assets = None
        if jobs is not None and jobs.enabled:
            from packages.resume_core.background_assets import JobAssets
            from packages.resume_core.background_store import BackgroundFailure
            assets = JobAssets(jobs.store)
            jobs.store.open(identifier)
            try:
                removable = assets.collectable(identifier, keep)
            except BackgroundFailure:
                return
            keep.update(asset.id for asset in workspace.project.assets if asset.id not in removable)
        removed = [asset for asset in workspace.project.assets if asset.id not in keep]
        if not removed:
            if assets is not None:
                assets.reclaim_blobs(identifier)
            return
        old = workspace.project.assets
        workspace.project.assets = [asset for asset in old if asset.id in keep]
        if self.persist(identifier) != "durable":
            workspace.project.assets = old
            return
        for asset in removed:
            self.images.pop((identifier, asset.id), None)
        if assets is not None:
            assets.reclaim_blobs(identifier)
        else:
            self.storage.reclaim_images(workspace)

    async def ingest_image(self, identifier, raw, capture):
        key = (identifier, capture.reservation_id)
        owner = ImageOwner(identifier, capture.session_id, capture.revision)
        with self.state_lock:
            self.require_agent_writable(identifier)
            workspace = self.read(identifier)
            document_revision = workspace.document_revision
            session = self.image_sessions.get((identifier, capture.session_id))
            if workspace.project is None or session is None or session.closed or session.revision != capture.revision:
                raise ProjectFailure("STALE_IMAGE_INSERTION")
            if key in self.image_reservations:
                raise ProjectFailure("IMAGE_RESERVATION_EXISTS")
            refs = self.image_references(identifier)
            # Pending editor images count before their autosave reaches the service.
            refs = ImageReferences(live=session.live, durable=refs.durable, history=refs.history)
            retention = ImageRetention(owner, workspace.project.assets, refs)
            reserved = [item for (pid, _), item in self.image_reservations.items() if pid == identifier]
            retention.reservations.update({item.id: item for item in reserved})
            try:
                reservation = retention.reserve(capture.reservation_id, capture.action_id, len(raw), len(raw), capture.replacement_id is not None)
            except ValueError:
                try:
                    # Decode can prove deduplication or smaller output; no new bytes publish without the final check.
                    reservation = retention.reserve(capture.reservation_id, capture.action_id, len(raw), 0, capture.replacement_id is not None)
                except ValueError:
                    raise ProjectFailure("IMAGE_CAPACITY_LIMIT", 422) from None
            self.image_reservations[key] = reservation
        task = asyncio.current_task()
        self.image_tasks.add(task)
        try:
            import threading
            async with self.worker_slot(threading.Event()):
                asset, data = await asyncio.to_thread(normalize_image, raw, capture.reservation_id)
            with self.state_lock:
                current = self.image_sessions.get((identifier, capture.session_id))
                if (identifier in self.deleted_ids or current is not session or current.closed or current.revision != capture.revision
                        or self.workspaces[identifier].document_revision != document_revision):
                    raise ProjectFailure("STALE_IMAGE_INSERTION")
                workspace = self.read(identifier)
                existing = next((old for old in workspace.project.assets if old.sha256 == asset.sha256), None)
                asset = existing or asset.model_copy(update={"id": "asset-" + asset.sha256})
                refs = self.image_references(identifier)
                retention = ImageRetention(owner, workspace.project.assets, ImageReferences(live=current.live,
                    durable=refs.durable, history=refs.history))
                retention.reservations.update({item.id: item for (pid, _), item in self.image_reservations.items() if pid == identifier})
                try:
                    retention.publish(capture.reservation_id, asset, owner, capture.replacement_id)
                except ValueError:
                    raise ProjectFailure("IMAGE_CAPACITY_LIMIT", 422) from None
                workspace.project.assets = retention.assets
                proof = workspace.model_copy(deep=True)
                if capture.replacement_id:
                    def remove(blocks):
                        for index, block in enumerate(blocks):
                            if isinstance(block, ImageBlock) and block.props.asset_id == capture.replacement_id:
                                blocks.pop(index); return True
                            if remove(block.children):
                                return True
                        return False
                    for region in proof.project.document.regions:
                        if remove(region.blocks):
                            break
                proof.project.document.regions[2].blocks.append(ImageBlock(id="admission-image", revision=1,
                    provenance=[], children=[], type="image", content=None, props={"assetId": asset.id,
                        "alt": "", "caption": [], "width": asset.width, "height": asset.height, "alignment": "left"}))
                images = {aid: blob for (pid, aid), blob in self.images.items() if pid == identifier}
                images[asset.id] = data
                rich_snapshot_bytes(workspace)
                archive_payload(proof, {sid: blob for (pid, sid), blob in self.originals.items() if pid == identifier}, images)
                self.images[(identifier, asset.id)] = data
                self.workspaces[identifier] = reconcile(self.workspaces[identifier], workspace)
                current.pending.add(asset.id)
                if self.persist(identifier) != "durable":
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
                jobs = getattr(self, "background_jobs", None)
                if jobs is not None and jobs.enabled:
                    from packages.resume_core.agent_store import digest
                    from packages.resume_core.background_assets import JobAssets
                    JobAssets(jobs.store).session(identifier, "session_" + digest(capture.session_id)[:40],
                        set((*current.live, *current.history, *current.pending)))
                return asset.id
        except ImageFailure as error:
            raise ProjectFailure(error.code, 422) from None
        except ArchiveFailure as error:
            raise ProjectFailure(error.code, 422) from None
        except ProjectStoreFailure as error:
            raise ProjectFailure(error.code, 422) from None
        except BackgroundFailure as error:
            raise ProjectFailure(error.code, 409) from None
        finally:
            self.image_tasks.discard(task)
            with self.state_lock:
                self.image_reservations.pop(key, None)
                if identifier not in self.deleted_ids:
                    self.reclaim_images(identifier)
