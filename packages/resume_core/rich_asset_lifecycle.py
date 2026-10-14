"""Session asset reservations and retained-reference admission protocol."""

from __future__ import annotations

from dataclasses import dataclass

from .models.rich_workspace import AssetReservation, LocalImageAsset
from .rich_limits import IMAGE_BYTES, ImageReferences, retained_image_bytes


@dataclass(frozen=True)
class ImageOwner:
    project_id: str
    session_id: str
    revision: int


class ImageRetention:
    def __init__(self, owner: ImageOwner, assets: list[LocalImageAsset], references: ImageReferences):
        retained_image_bytes(assets, references)
        self.owner = owner
        self.assets = list(assets)
        self.references = references
        self.reservations: dict[str, AssetReservation] = {}

    def _reserved(self, exclude: str | None = None) -> tuple[int, int]:
        active = [item for item in self.reservations.values()
                  if item.id != exclude and item.status in {"reserved", "decoding"}]
        return sum(item.retained_bytes for item in active), sum(item.live_blocks for item in active)

    def reserve(self, reservation_id: str, action_id: str, input_size: int, retained_size: int,
                replacement: bool = False) -> AssetReservation:
        if reservation_id in self.reservations:
            raise ValueError("duplicate image reservation")
        if not 0 < input_size <= IMAGE_BYTES:
            raise ValueError("image input exceeds 10 MiB")
        if retained_size < 0:
            raise ValueError("nonnegative retained image reservation required")
        reserved_bytes, reserved_blocks = self._reserved()
        blocks = 0 if replacement else 1
        retained_image_bytes(self.assets, self.references, reserved_bytes + retained_size, reserved_blocks + blocks)
        item = AssetReservation(id=reservation_id, projectId=self.owner.project_id, sessionId=self.owner.session_id,
                                actionId=action_id, dependencyRevision=self.owner.revision,
                                retainedBytes=retained_size, liveBlocks=blocks, status="reserved")
        self.reservations[item.id] = item
        return item

    def cancel(self, reservation_id: str) -> None:
        item = self.reservations[reservation_id]
        if item.status in {"reserved", "decoding"}:
            self.reservations[reservation_id] = item.model_copy(update={"status": "cancelled"})

    def fail(self, reservation_id: str) -> None:
        item = self.reservations[reservation_id]
        if item.status in {"reserved", "decoding"}:
            self.reservations[reservation_id] = item.model_copy(update={"status": "failed"})

    def publish(self, reservation_id: str, asset: LocalImageAsset, current_owner: ImageOwner,
                replacement_id: str | None = None) -> str:
        item = self.reservations[reservation_id]
        if item.status not in {"reserved", "decoding"}:
            return "stale"
        if current_owner != self.owner or (item.project_id, item.session_id, item.dependency_revision) != (
                current_owner.project_id, current_owner.session_id, current_owner.revision):
            self.reservations[reservation_id] = item.model_copy(update={"status": "stale"})
            return "stale"
        if (item.live_blocks == 0) != (replacement_id is not None) or (
                replacement_id is not None and replacement_id not in self.references.live):
            self.fail(reservation_id)
            raise ValueError("image replacement reservation mismatch")
        existing = next((old for old in self.assets if old.id == asset.id), None)
        if existing is not None and existing != asset:
            self.fail(reservation_id)
            raise ValueError("image identity cannot replace bytes")
        assets = self.assets if existing is not None else [*self.assets, asset]
        live = list(self.references.live)
        if replacement_id is not None:
            live[live.index(replacement_id)] = asset.id
        else:
            live.append(asset.id)
        refs = ImageReferences(live=tuple(live), durable=self.references.durable,
                               history=tuple(set((*self.references.history, *self.references.live, asset.id))),
                               in_flight=self.references.in_flight)
        reserved_bytes, reserved_blocks = self._reserved(exclude=reservation_id)
        try:
            retained_image_bytes(assets, refs, reserved_bytes, reserved_blocks)
        except ValueError:
            self.fail(reservation_id)
            raise
        self.assets = assets
        self.references = refs
        self.reservations[reservation_id] = item.model_copy(update={"status": "published"})
        return "published"

    def set_references(self, references: ImageReferences) -> None:
        reserved_bytes, reserved_blocks = self._reserved()
        retained_image_bytes(self.assets, references, reserved_bytes, reserved_blocks)
        self.references = references

    def reclaimable_ids(self, supported_project: bool) -> set[str]:
        if not supported_project or any(item.status in {"reserved", "decoding"} for item in self.reservations.values()):
            return set()
        refs = self.references
        retained = set((*refs.live, *refs.durable, *refs.history, *refs.in_flight))
        return {asset.id for asset in self.assets if asset.id not in retained}
