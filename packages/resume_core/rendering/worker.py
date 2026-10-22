"""One isolated render worker. LibreOffice stays in this worker's process group."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pymupdf

from packages.resume_core.rendering import layout
from packages.resume_core.rendering.models import RenderRequest
from packages.resume_core.rendering.docx_errors import DocxFailure, failure, validate_document, writer_failure
from packages.resume_core.models.recovery import Anchor
from pydantic import TypeAdapter
from packages.resume_core.rendering.template import (APP_FONTS, PACKAGE_SHA256, SOFFICE,
                                                     RenderFailure, icon_path, require_template,
                                                     renderer_sha256, sha256_file, require_docx_template)

MAX_DOCX = 8 * 1024 * 1024
MAX_RICH_DOCX = 32 * 1024 * 1024
MAX_PDF = 12 * 1024 * 1024
MAX_ZIP = 16 * 1024 * 1024


def _clean_environment(workspace: Path) -> dict[str, str]:
    locations = {name: workspace / name for name in ("home", "tmp", "cache", "data", "state")}
    for path in locations.values():
        path.mkdir(mode=0o700, exist_ok=True)
    return {
        "PATH": os.defpath,
        "HOME": str(locations["home"]),
        "TMPDIR": str(locations["tmp"]),
        "XDG_CACHE_HOME": str(locations["cache"]),
        "XDG_DATA_HOME": str(locations["data"]),
        "XDG_STATE_HOME": str(locations["state"]),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "SAL_USE_VCLPLUGIN": "osx",
    }


def _strip_docx_metadata(path: Path) -> None:
    clean = path.with_suffix(".clean.docx")
    with zipfile.ZipFile(path) as original, zipfile.ZipFile(clean, "w") as output:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == "docProps/core.xml":
                data = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        b'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"/>')
            output.writestr(entry, data)
    clean.replace(path)


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _words_in_order(haystack: str, value: str) -> bool:
    position = 0
    for word in value.split():
        found = haystack.find(word, position)
        if found < 0:
            return False
        position = found + len(word)
    return True


def _expected_text(request: RenderRequest) -> list[str]:
    document = request.document
    expected = [document.candidate.name, document.candidate.title, document.candidate.summary,
                document.footer]
    expected += [item.label for item in document.focus]
    expected += [item.duration for item in document.focus]
    for section in document.sidebar:
        items = [item for item in section.items if item.strip()]
        if items:
            expected.extend([section.title, *items])
    for project in document.projects:
        expected.extend([project.company, project.period, project.stack, project.description,
                         project.role, *(item for item in project.tasks if item.strip()),
                         *(item for item in project.results if item.strip())])
    expected.extend(item for item in document.achievements if item.strip())
    for group in document.skill_groups:
        if group.items.strip():
            expected.extend([group.title, group.items])
    return [value for value in expected if value.strip()]


def _verify_pdf(pdf_path: Path, request: RenderRequest) -> int:
    with pymupdf.open(pdf_path) as pdf:
        if len(pdf) == 0 or len(pdf) > 30:
            raise RenderFailure("RENDER_PAGE_LIMIT")
        text = _normalize(" ".join(page.get_text() for page in pdf))
        expected = _expected_text(request)
        for value in expected:
            if _normalize(value) not in text and not _words_in_order(text, _normalize(value)):
                raise RenderFailure("RENDER_CONTENT_LOSS")
        expected_words = Counter(word for value in expected for word in _normalize(value).split())
        pdf_words = Counter(text.split())
        if any(pdf_words[word] < count for word, count in expected_words.items()):
            raise RenderFailure("RENDER_CONTENT_LOSS")
        for page in pdf:
            fonts = {name.split("+")[-1] for _, _, _, name, *_ in page.get_fonts(full=True)}
            if not fonts or not fonts <= {"SourceSansPro-Regular", "SourceSansPro-Bold"}:
                raise RenderFailure("FONT_SUBSTITUTED")
            body = page.get_text().replace(request.document.candidate.name, "").replace(request.document.candidate.title, "")
            body = body.replace(request.document.footer, "") if request.document.footer else body
            if not _normalize(body):
                raise RenderFailure("RENDER_BLANK_PAGE")
            if abs(page.rect.width - 595.3) > 1 or abs(page.rect.height - 841.9) > 1:
                raise RenderFailure("RENDER_PAGE_GEOMETRY")
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        box = pymupdf.Rect(span["bbox"])
                        if box.x0 < -0.5 or box.y0 < -0.5 or box.x1 > page.rect.width + 0.5 or box.y1 > page.rect.height + 0.5:
                            raise RenderFailure("RENDER_CLIPPED")
        return len(pdf)


def _convert(docx_path: Path, pdf_path: Path, workspace: Path) -> None:
    output = workspace / "pdf-output"
    output.mkdir(mode=0o700, exist_ok=True)
    profile = (workspace / "lo-profile").as_uri()
    args = [str(SOFFICE), f"-env:UserInstallation={profile}", "--headless",
            "--convert-to", "pdf:writer_pdf_Export", "--outdir", str(output), str(docx_path)]
    try:
        process = subprocess.Popen(args, cwd=workspace, env=_clean_environment(workspace),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, shell=False, start_new_session=False)
        try:
            result = process.wait(timeout=24)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
            raise RenderFailure("CONVERTER_TIMEOUT") from None
    except OSError:
        raise RenderFailure("CONVERTER_UNAVAILABLE") from None
    converted = output / (docx_path.stem + ".pdf")
    if result != 0 or not converted.is_file():
        raise RenderFailure("CONVERTER_FAILED")
    converted.replace(pdf_path)


def _strip_pdf_metadata(path: Path) -> None:
    clean = path.with_suffix(".clean.pdf")
    with pymupdf.open(path) as pdf:
        pdf.set_metadata({})
        pdf.save(clean, garbage=4, deflate=True)
    clean.replace(path)


def _write_zip(path: Path, docx: Path, pdf: Path, metadata: dict) -> None:
    body = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, content in (("resume.docx", docx.read_bytes()), ("resume.pdf", pdf.read_bytes()), ("render.json", body)):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    if path.stat().st_size > MAX_ZIP:
        raise RenderFailure("RENDER_OUTPUT_LIMIT")


def render(workspace: Path) -> None:
    request = RenderRequest.model_validate_json((workspace / "render-input.json").read_bytes())
    manifest = require_template()
    if request.snapshot.template_package_sha256 != PACKAGE_SHA256:
        raise RenderFailure("TEMPLATE_MISMATCH")
    renderer_hash = renderer_sha256()
    if request.snapshot.renderer_sha256 != renderer_hash:
        raise RenderFailure("RENDERER_MISMATCH")
    for item in request.document.focus:
        icon_path(item.icon, manifest)
    data = request.document.model_dump(mode="json", by_alias=False)
    data["sidebar"] = [{**section, "items": [item for item in section["items"] if item.strip()]}
                       for section in data["sidebar"] if any(item.strip() for item in section["items"])]
    data["achievements"] = [item for item in data["achievements"] if item.strip()]
    data["skill_groups"] = [group for group in data["skill_groups"] if group["items"].strip()]
    for project in data["projects"]:
        project["tasks"] = [item for item in project["tasks"] if item.strip()]
        project["results"] = [item for item in project["results"] if item.strip()]
    docx = workspace / "resume.docx"
    pdf = workspace / "resume.pdf"
    try:
        layout.render_docx(data, docx)
    except ValueError:
        raise RenderFailure("RENDER_UNSUPPORTED_CONTENT") from None
    _strip_docx_metadata(docx)
    if docx.stat().st_size > MAX_DOCX:
        raise RenderFailure("RENDER_OUTPUT_LIMIT")
    _convert(docx, pdf, workspace)
    _strip_pdf_metadata(pdf)
    if pdf.stat().st_size > MAX_PDF:
        raise RenderFailure("RENDER_OUTPUT_LIMIT")
    pages = _verify_pdf(pdf, request)
    metadata = {
        "snapshotId": request.snapshot.id,
        "projectRevision": request.snapshot.project_revision,
        "snapshotSha256": request.snapshot.snapshot_sha256,
        "templateId": "generic", "templateVersion": "1.0.0",
        "templatePackageSha256": PACKAGE_SHA256,
        "rendererVersion": "1.0.0",
        "rendererSha256": renderer_hash,
        "converterVersion": manifest["converter"]["version"],
        "converterSha256": manifest["converter"]["sha256"],
        "pageCount": pages,
        "docxSha256": sha256_file(docx), "pdfSha256": sha256_file(pdf),
        "capabilities": {"editableDocx": True, "pdfDerivedFromDocx": True, "embeddedPdfFonts": True},
    }
    _write_zip(workspace / "render-output.zip", docx, pdf, metadata)


def render_docx_only(workspace: Path) -> None:
    payload = json.loads((workspace / "docx-input.json").read_bytes())
    anchors = {path: TypeAdapter(Anchor).validate_python(anchor) for path, anchor in payload["anchors"].items()}
    document = validate_document(payload["document"], anchors)
    manifest = require_docx_template()
    if payload["rendererSha256"] != renderer_sha256():
        raise RenderFailure("RENDERER_MISMATCH")
    for index, item in enumerate(document.focus):
        try:
            icon_path(item.icon, manifest)
        except RenderFailure as error:
            if error.code == "UNSUPPORTED_FOCUS_ICON":
                raise failure("DOCX_UNKNOWN_FOCUS_ICON", f"focus[{index}].icon", anchors) from None
            raise
    docx = workspace / "resume.docx"
    try:
        layout.render_docx(document.model_dump(mode="json"), docx)
    except Exception as error:
        raise writer_failure(error, anchors) from None
    _strip_docx_metadata(docx)
    if docx.stat().st_size > MAX_DOCX:
        raise RenderFailure("RENDER_OUTPUT_LIMIT")


def main() -> int:
    workspace = Path.cwd()
    try:
        inputs = [name for name in ('template-docx-input.json', 'rich-docx-input.json', 'docx-input.json', 'render-input.json')
            if (workspace / name).exists()]
        if len(inputs) != 1:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        if inputs[0] == 'template-docx-input.json':
            from packages.resume_core.models.template_render import TemplateRenderRequestV1
            from packages.resume_core.rendering.captured_docx import render_captured_docx
            request = TemplateRenderRequestV1.model_validate_json((workspace / inputs[0]).read_bytes())
            content = render_captured_docx(request, workspace)
            if len(content) > MAX_RICH_DOCX:
                raise RenderFailure('RENDER_OUTPUT_LIMIT')
            (workspace / 'resume.docx').write_bytes(content)
        elif inputs[0] == 'rich-docx-input.json':
            from packages.resume_core.models.rich_document import RichDocumentV1
            from packages.resume_core.rendering.rich_docx import render_rich_docx, renderer_sha256 as rich_renderer_sha256
            payload = json.loads((workspace / "rich-docx-input.json").read_bytes())
            if payload["rendererSha256"] != rich_renderer_sha256():
                raise RenderFailure("RENDERER_MISMATCH")
            document = RichDocumentV1.model_validate(payload["document"])
            import hashlib
            import re
            images = {}
            for identifier, checksum in payload.get("images", {}).items():
                if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
                    raise RenderFailure("RICH_IMAGE_MISSING")
                data = (workspace / (checksum + ".image")).read_bytes()
                if len(data) > 20 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != checksum:
                    raise RenderFailure("RICH_IMAGE_MISSING")
                images[identifier] = data
            from packages.resume_core.models.rich_facts import WorkingFacts
            facts = WorkingFacts.model_validate(payload["facts"]) if "facts" in payload else None
            content = render_rich_docx(document, images, facts)
            if len(content) > MAX_RICH_DOCX:
                raise RenderFailure("RENDER_OUTPUT_LIMIT")
            (workspace / "resume.docx").write_bytes(content)
        elif (workspace / "docx-input.json").is_file():
            render_docx_only(workspace)
        else:
            render(workspace)
        return 0
    except DocxFailure as error:
        (workspace / "render-status.json").write_text(error.error.model_dump_json(by_alias=True), encoding="utf-8")
        return 1
    except RenderFailure as error:
        code = error.code
    except Exception:
        if (workspace / "docx-input.json").is_file():
            (workspace / "render-status.json").write_text(failure("DOCX_RENDER_FAILED").error.model_dump_json(by_alias=True), encoding="utf-8")
            return 1
        code = "RENDER_FAILED"
    (workspace / "render-status.json").write_text(json.dumps({"code": code}), encoding="utf-8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
