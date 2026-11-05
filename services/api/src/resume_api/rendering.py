"""Run one bounded document worker in the service-owned operation group: the V7 DOCX export."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import zipfile

from packages.resume_core.rendering.template import RenderFailure

from .lifecycle import OperationFiles, python_worker

WORKER = Path(__file__).resolve().parents[4] / "packages/resume_core/rendering/worker.py"


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
        process = files.spawn(*python_worker("render", str(WORKER)), capture=False)
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
