"""Read-only access to the bytes retained at import."""

import hashlib
from pathlib import PurePosixPath
from urllib.parse import quote

from fastapi.responses import Response

from .gui_projects import ProjectFailure


def original_response(service, identifier, source_id, *, download=False):
    workspace = service.read(identifier)
    owner = workspace.project or workspace.pre_draft
    source = next((item for item in owner.sources if item.id == source_id), None)
    if source is None:
        raise ProjectFailure("SOURCE_NOT_FOUND", 404)
    data = service.originals.get((identifier, source.id))
    if data is None:
        raise ProjectFailure("SOURCE_BYTES_MISSING", 404)
    if hashlib.sha256(data).hexdigest() != source.byte_sha256:
        raise ProjectFailure("SOURCE_BYTES_MISMATCH", 409)
    name = PurePosixPath(source.original_name.replace("\\", "/")).name
    name = "".join(char for char in name if ord(char) >= 32 and ord(char) != 127) or "original"
    media_type = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
    }.get(PurePosixPath(name.lower()).suffix, "application/octet-stream")
    disposition = "attachment" if download else "inline"
    return Response(data, media_type=media_type, headers={
        "Cache-Control": "no-store",
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(name, safe='')}",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "X-FoldCV-Sha256": source.byte_sha256,
    })


def mount_original_sources(app, service):
    prefix = "/v1/rich/projects/{identifier}/sources/{source_id}/original"

    @app.get(prefix)
    async def original(identifier: str, source_id: str):
        return original_response(service, identifier, source_id)

    @app.get(prefix + "/download")
    async def download(identifier: str, source_id: str):
        return original_response(service, identifier, source_id, download=True)
