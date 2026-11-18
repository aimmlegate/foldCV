"""Original source bytes from the project folder."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from urllib.parse import quote

from fastapi.responses import Response

from packages.resume_core.repository.project_repository import blob_path
from packages.resume_core.repository.source_diff import additions, removals
from packages.resume_core.extraction.parser import MAX_SOURCE

from .blobs import read_owned
from .errors import ProjectFailure


def beyond_original(service, project_id):
    """The present document against the original: the words each shown field has and its source lines lack (the
    editor marks them as added), and the words of those lines the document no longer shows (marked in the original)."""
    session = service.repository.open(project_id)
    with session.lock:
        return {'added': additions(session.workspace), 'removed': removals(session.workspace)}


def original(service, project_id, source_id, *, download=False):
    session = service.repository.open(project_id)
    workspace = service.repository.read(project_id)
    owner = workspace.project or workspace.pre_draft
    source = next((item for item in owner.sources if item.id == source_id), None) if owner is not None else None
    if source is None:
        raise ProjectFailure('SOURCE_NOT_FOUND', 404)
    path = blob_path(session.directory, 'sources', source.id)
    data = read_owned(path, MAX_SOURCE, 'SOURCE_BYTES_MISSING')
    if hashlib.sha256(data).hexdigest() != source.byte_sha256:
        raise ProjectFailure('SOURCE_BYTES_MISMATCH', 409)
    name = PurePosixPath(source.original_name.replace('\\', '/')).name
    name = ''.join(char for char in name if ord(char) >= 32 and ord(char) != 127) or 'original'
    media_type = {
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.txt': 'text/plain',
        '.md': 'text/markdown',
        '.markdown': 'text/markdown',
    }.get(PurePosixPath(name.lower()).suffix, 'application/octet-stream')
    disposition = 'attachment' if download else 'inline'
    return Response(data, media_type=media_type, headers={
        'Cache-Control': 'no-store',
        'Content-Disposition': f"{disposition}; filename*=UTF-8''{quote(name, safe='')}",
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-FoldCV-Sha256': source.byte_sha256,
    })
