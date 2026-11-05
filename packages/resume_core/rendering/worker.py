"""One isolated render worker: the captured template DOCX export."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.resume_core.rendering.template import RenderFailure

MAX_RICH_DOCX = 32 * 1024 * 1024
# The input names of the retired render modes: a directory holding one of them, or more than one input, is refused.
INPUTS = ('template-docx-input.json', 'rich-docx-input.json', 'docx-input.json', 'render-input.json')


def main() -> int:
    workspace = Path.cwd()
    try:
        inputs = [name for name in INPUTS if (workspace / name).exists()]
        if inputs != ['template-docx-input.json']:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        from packages.resume_core.models.template_render import TemplateRenderRequestV1
        from packages.resume_core.rendering.captured_docx import render_captured_docx
        request = TemplateRenderRequestV1.model_validate_json((workspace / inputs[0]).read_bytes())
        content = render_captured_docx(request, workspace)
        if len(content) > MAX_RICH_DOCX:
            raise RenderFailure('RENDER_OUTPUT_LIMIT')
        (workspace / 'resume.docx').write_bytes(content)
        return 0
    except RenderFailure as error:
        code, details = error.code, error.details
    except Exception:
        code, details = "RENDER_FAILED", {}
    (workspace / "render-status.json").write_text(json.dumps({"code": code, **details}), encoding="utf-8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
