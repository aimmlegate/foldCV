"""Rich admission limits; legacy transport and render limits stay unchanged."""

from __future__ import annotations

from dataclasses import dataclass

from .models.rich_workspace import LocalImageAsset

MIB = 1024 * 1024
MUTATION_BYTES = MIB
IMAGE_BYTES = 10 * MIB
UPLOAD_OVERHEAD_BYTES = 64 * 1024
IMAGE_PIXELS = 25_000_000
LIVE_IMAGES = 20
RETAINED_IMAGE_BYTES = 20 * MIB
WORKSPACE_BYTES = 16 * MIB
DOCX_BYTES = 32 * MIB
ZIP_BYTES = 64 * MIB
ARCHIVE_EXPANDED_BYTES = 60 * MIB
ARCHIVE_ENTRY_BYTES = 32 * MIB
ARCHIVE_PAYLOAD_COUNT = 47


@dataclass(frozen=True)
class ImageReferences:
    live: tuple[str, ...] = ()
    durable: tuple[str, ...] = ()
    history: tuple[str, ...] = ()
    in_flight: tuple[str, ...] = ()


def retained_image_bytes(assets: list[LocalImageAsset], references: ImageReferences,
                         reserved_bytes: int = 0, reserved_blocks: int = 0) -> int:
    if not 0 <= reserved_bytes <= RETAINED_IMAGE_BYTES or not 0 <= reserved_blocks <= LIVE_IMAGES:
        raise ValueError("invalid image reservation")
    if len(references.live) + reserved_blocks > LIVE_IMAGES:
        raise ValueError("live image limit exceeded")
    by_id = {asset.id: asset for asset in assets}
    if len(by_id) != len(assets):
        raise ValueError("duplicate image asset identity")
    retained = set((*references.live, *references.durable, *references.history, *references.in_flight))
    if not retained <= by_id.keys():
        raise ValueError("missing retained image asset")
    by_hash: dict[str, int] = {}
    for asset_id in retained:
        asset = by_id[asset_id]
        if asset.sha256 in by_hash and by_hash[asset.sha256] != asset.size:
            raise ValueError("inconsistent image hash metadata")
        by_hash[asset.sha256] = asset.size
    total = sum(by_hash.values()) + reserved_bytes
    if total > RETAINED_IMAGE_BYTES:
        raise ValueError("retained image byte limit exceeded")
    return total


def portable_payload(required_sizes: list[int], optional_render_size: int | None, *,
                     manifest_size: int, render_manifest_size: int | None = None) -> list[int]:
    def fits(sizes: list[int], metadata_size: int) -> bool:
        return (len(sizes) <= ARCHIVE_PAYLOAD_COUNT
                and 0 < metadata_size <= ARCHIVE_ENTRY_BYTES
                and all(0 <= size <= ARCHIVE_ENTRY_BYTES for size in sizes)
                and sum(sizes) + metadata_size <= ARCHIVE_EXPANDED_BYTES)

    if not fits(required_sizes, manifest_size):
        raise ValueError("required portable payload exceeds capacity")
    if optional_render_size is not None and render_manifest_size is None:
        raise ValueError("render manifest byte size required")
    if optional_render_size is not None and render_manifest_size is not None and fits(
            [*required_sizes, optional_render_size], render_manifest_size):
        return [*required_sizes, optional_render_size]
    return list(required_sizes)
