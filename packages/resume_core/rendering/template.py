"""Verify fixed local renderer assets before each render."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "templates/generic/manifest.json"
SOFFICE = ROOT / ".tools/LibreOffice.app/Contents/MacOS/soffice"
APP_FONTS = ROOT / ".tools/LibreOffice.app/Contents/Resources/fonts/truetype"
PACKAGE_SHA256 = "d081df948bfd55d107c38d40387a9758f563f9c14a9cffc4a847f44cb687b8b9"


class RenderFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def renderer_sha256() -> str:
    digest = hashlib.sha256()
    for name in ("layout.py", "models.py", "template.py", "worker.py"):
        source = Path(__file__).with_name(name)
        digest.update(name.encode("ascii") + b"\0")
        digest.update(bytes.fromhex(sha256_file(source)))
    return digest.hexdigest()


def require_docx_template() -> dict:
    try:
        if sha256_file(MANIFEST) != PACKAGE_SHA256:
            raise RenderFailure("TEMPLATE_MISMATCH")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        if manifest["id"] != "generic" or manifest["version"] != "1.0.0" or manifest["rendererVersion"] != "1.0.0":
            raise RenderFailure("TEMPLATE_MISMATCH")
        for relative, expected in manifest["assets"].items():
            path = ROOT / relative
            if not path.is_file():
                raise RenderFailure("ASSET_UNAVAILABLE")
            if sha256_file(path) != expected:
                raise RenderFailure("ASSET_MISMATCH")
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        raise RenderFailure("TEMPLATE_UNAVAILABLE") from error
    return manifest


def require_template() -> dict:
    manifest = require_docx_template()
    try:
        if not SOFFICE.is_file():
            raise RenderFailure("CONVERTER_UNAVAILABLE")
        if sha256_file(SOFFICE) != manifest["converter"]["sha256"]:
            raise RenderFailure("CONVERTER_MISMATCH")
        for relative, expected in manifest["assets"].items():
            if relative.endswith(".ttf"):
                installed = APP_FONTS / Path(relative).name
                if not installed.is_file():
                    raise RenderFailure("FONT_UNAVAILABLE")
                if sha256_file(installed) != expected:
                    raise RenderFailure("FONT_MISMATCH")
    except (OSError, KeyError, ValueError) as error:
        raise RenderFailure("TEMPLATE_UNAVAILABLE") from error
    return manifest


def icon_path(icon: str, manifest: dict) -> Path:
    for directory in ("images", "devicon"):
        relative = f"skills/format-resume/assets/{directory}/{icon}.png"
        if relative in manifest["assets"]:
            return ROOT / relative
    raise RenderFailure("UNSUPPORTED_FOCUS_ICON")
