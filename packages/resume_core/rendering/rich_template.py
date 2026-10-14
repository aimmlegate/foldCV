"""Verify the separately identified rich template and its shared geometry."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .template import RenderFailure
from ..models.contracts import AssetRef, TemplateManifest, _safe_path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "templates/foldcv-reference/manifest.json"
PACKAGE_SHA256 = "29e386d7ed0c3db4d99b7d67f440a11aeec05c08de6ad7eba623bca412a73529"


@dataclass(frozen=True)
class RichTemplatePackage:
    manifest: TemplateManifest
    specification: dict


def require_rich_template(root: Path = ROOT, manifest_path: Path = MANIFEST_PATH,
                          expected_sha256: str = PACKAGE_SHA256) -> RichTemplatePackage:
    try:
        raw = manifest_path.read_bytes()
        if manifest_path.is_symlink() or hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise RenderFailure("RICH_TEMPLATE_MISMATCH")
        manifest = json.loads(raw)
        if (manifest["id"], manifest["version"], manifest["rendererVersion"]) != ("foldcv-reference", "1.0.0", "1.0.0"):
            raise RenderFailure("RICH_TEMPLATE_MISMATCH")
        assets = []
        for relative, checksum in manifest["assets"].items():
            if not _safe_path(relative):
                raise RenderFailure("RICH_TEMPLATE_UNSAFE_ASSET")
            path = root / relative
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or any(
                parent.is_symlink() for parent in path.parents if parent != root and parent.is_relative_to(root)
            ):
                raise RenderFailure("RICH_TEMPLATE_UNSAFE_ASSET")
            blob = path.read_bytes()
            if hashlib.sha256(blob).hexdigest() != checksum:
                raise RenderFailure("RICH_TEMPLATE_ASSET_MISMATCH")
            assets.append(AssetRef(path=relative, sha256=checksum, size=len(blob)))
        spec = json.loads((root / "templates/foldcv-reference/spec.json").read_bytes())
        if (spec["schemaVersion"], spec["id"], spec["version"]) != (1, "foldcv-reference", "1.0.0"):
            raise RenderFailure("RICH_TEMPLATE_MISMATCH")
        return RichTemplatePackage(TemplateManifest(id="foldcv-reference", version="1.0.0",
            packageSha256=expected_sha256, contentPolicyVersion=manifest["contentPolicyVersion"], assets=assets), spec)
    except (OSError, KeyError, ValueError, TypeError) as error:
        raise RenderFailure("RICH_TEMPLATE_UNAVAILABLE") from error
