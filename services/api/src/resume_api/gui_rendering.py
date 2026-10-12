"""Converter-free rendering with the existing owned-worker cleanup boundary."""

import asyncio
import json
from pathlib import Path
import sys
import zipfile

from packages.resume_core.models.recovery import DocxError
from packages.resume_core.rendering.docx_errors import DocxFailure, failure
from packages.resume_core.rendering.privacy import guard_render_document
from packages.resume_core.rendering.template import RenderFailure, renderer_sha256
from .lifecycle import OperationFiles
from .rendering import WORKER, ALLOWED_ERRORS


class GuiDocxRenderer:
    async def render(self, document, anchors, files: OperationFiles) -> bytes:
        guard_render_document(document)
        if files.path is None:
            raise failure("DOCX_RENDER_FAILED")
        workspace = files.path
        payload = {"document": document.model_dump(mode="json", by_alias=True),
            "anchors": {path: anchor.model_dump(mode="json", by_alias=True) for path, anchor in anchors.items()},
            "rendererSha256": renderer_sha256()}
        (workspace / "docx-input.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        process = files.spawn(Path(sys.executable), (str(WORKER),), capture=False)
        try:
            code = await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=30)
        finally:
            files.stop_worker()
        if code:
            try:
                data = json.loads((workspace / "render-status.json").read_bytes())
                if data.get("code", "").startswith("DOCX_"):
                    raise DocxFailure(DocxError.model_validate(data))
                code = data["code"]
            except (OSError, ValueError, KeyError, TypeError):
                raise failure("DOCX_RENDER_FAILED") from None
            raise RenderFailure(code if code in ALLOWED_ERRORS else "RENDER_FAILED")
        result = workspace / "resume.docx"
        try:
            if not result.is_file() or result.stat().st_size > 8 * 1024 * 1024:
                raise RenderFailure("RENDER_OUTPUT_LIMIT")
            with zipfile.ZipFile(result) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise failure("DOCX_RENDER_FAILED")
            return result.read_bytes()
        except (OSError, zipfile.BadZipFile):
            raise failure("DOCX_RENDER_FAILED") from None
