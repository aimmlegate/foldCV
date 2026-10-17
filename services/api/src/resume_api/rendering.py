"""Run one bounded document worker in the service-owned operation group."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import zipfile

from packages.resume_core.rendering.models import RenderRequest
from packages.resume_core.rendering.template import RenderFailure

from .lifecycle import OperationFiles

WORKER = Path(__file__).resolve().parents[4] / "packages/resume_core/rendering/worker.py"
MAX_ZIP = 16 * 1024 * 1024
ALLOWED_ERRORS = frozenset({
    "TEMPLATE_MISMATCH", "TEMPLATE_UNAVAILABLE", "RENDERER_MISMATCH", "CONVERTER_UNAVAILABLE", "CONVERTER_MISMATCH",
    "CONVERTER_TIMEOUT", "CONVERTER_FAILED", "ASSET_UNAVAILABLE", "ASSET_MISMATCH",
    "FONT_UNAVAILABLE", "FONT_MISMATCH", "FONT_SUBSTITUTED", "UNSUPPORTED_FOCUS_ICON",
    "RENDER_UNSUPPORTED_CONTENT", "RENDER_OUTPUT_LIMIT", "RENDER_PAGE_LIMIT", "RENDER_CONTENT_LOSS",
    "RENDER_BLANK_PAGE", "RENDER_PAGE_GEOMETRY", "RENDER_CLIPPED", "RENDER_FAILED",
})


class DocumentRenderer:
    def __init__(self, *, executor=None):
        self.executor = executor

    async def render(self, request: RenderRequest, files: OperationFiles) -> bytes:
        if files.path is None:
            raise RenderFailure("RENDER_FAILED")
        workspace = files.path
        (workspace / "render-input.json").write_bytes(request.model_dump_json(by_alias=True).encode("utf-8"))
        process = files.spawn(Path(sys.executable), (str(WORKER),), capture=False)
        try:
            code = await asyncio.get_running_loop().run_in_executor(self.executor, process.wait)
        finally:
            # A failed worker may leave its converter alive in the same group.
            files.stop_worker()
        if code:
            status = workspace / "render-status.json"
            try:
                data = json.loads(status.read_text(encoding="utf-8"))
                error = data["code"]
            except (OSError, ValueError, KeyError, TypeError):
                error = "RENDER_FAILED"
            raise RenderFailure(error if error in ALLOWED_ERRORS else "RENDER_FAILED")
        result = workspace / "render-output.zip"
        try:
            if not result.is_file() or result.stat().st_size > MAX_ZIP:
                raise RenderFailure("RENDER_OUTPUT_LIMIT")
            data = result.read_bytes()
            with zipfile.ZipFile(result) as archive:
                if archive.namelist() != ["resume.docx", "resume.pdf", "render.json"]:
                    raise RenderFailure("RENDER_FAILED")
            return data
        except (OSError, zipfile.BadZipFile):
            raise RenderFailure("RENDER_FAILED") from None
