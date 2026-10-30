"""Run one bounded document worker in the service-owned operation group: the V7 DOCX export and the PDF render."""

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


class TemplateDocxRenderer:
    """The V7 export: one captured template render request in, the editable DOCX out."""

    ALLOWED = frozenset({"RICH_EXPORT_UNSUPPORTED", "RICH_TEMPLATE_MISMATCH", "RICH_TEMPLATE_ASSET_MISMATCH",
        "RICH_TEMPLATE_UNAVAILABLE", "RENDER_OUTPUT_LIMIT", "RENDERER_MISMATCH", "RICH_IMAGE_MISSING", "RICH_TABLE_INVALID",
        "FONT_UNAVAILABLE", "FONT_MISMATCH", "ASSET_UNAVAILABLE", "ASSET_MISMATCH"})

    def __init__(self, *, executor=None):
        self.executor = executor

    async def render_template(self, request, files: OperationFiles) -> bytes:
        from packages.resume_core.models.template_render import TemplateRenderRequestV1
        if files.path is None:
            raise RenderFailure("RICH_RENDER_FAILED")
        captured = TemplateRenderRequestV1.model_validate(request.model_dump(mode="json", by_alias=True))
        (files.path / "template-docx-input.json").write_text(captured.model_dump_json(by_alias=True), encoding="utf-8")
        return await self._run(files)

    async def _run(self, files: OperationFiles) -> bytes:
        from packages.resume_core.rich_limits import DOCX_BYTES
        workspace = files.path
        process = files.spawn(Path(sys.executable), (str(WORKER),), capture=False)
        try:
            code = await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(self.executor, process.wait), timeout=30)
        finally:
            files.stop_worker()
        if code:
            try:
                status = json.loads((workspace / "render-status.json").read_bytes())
                error = status["code"]
            except (OSError, ValueError, KeyError, TypeError):
                status, error = {}, "RICH_RENDER_FAILED"
            located = {key: status[key] for key in ("blockId", "fragment") if isinstance(status.get(key), str)}
            raise RenderFailure(error if error in self.ALLOWED else "RICH_RENDER_FAILED", located)
        result = workspace / "resume.docx"
        try:
            if not result.is_file() or result.stat().st_size > DOCX_BYTES:
                raise RenderFailure("RENDER_OUTPUT_LIMIT")
            with zipfile.ZipFile(result) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise RenderFailure("RICH_RENDER_FAILED")
            return result.read_bytes()
        except (OSError, zipfile.BadZipFile):
            raise RenderFailure("RICH_RENDER_FAILED") from None
