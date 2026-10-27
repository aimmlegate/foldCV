"""Image bytes by hash. Upload stays on the V6 editor; unreferenced files go on session close."""

from __future__ import annotations

import hashlib
import re

from fastapi.responses import Response
from packages.resume_core.rich_limits import IMAGE_BYTES

from .blobs import read_owned
from .errors import ProjectFailure


def image_bytes(service, project_id, sha):
    if re.fullmatch(r'[0-9a-f]{64}', sha) is None:
        raise ProjectFailure('IMAGE_NOT_FOUND', 404)
    session = service.repository.open(project_id)
    folder = session.directory / 'images'
    for extension, media in (('png', 'image/png'), ('jpg', 'image/jpeg')):
        path = folder / (sha + '.' + extension)
        if not path.is_file():
            continue
        data = read_owned(path, IMAGE_BYTES, 'IMAGE_NOT_FOUND')
        if hashlib.sha256(data).hexdigest() != sha:
            raise ProjectFailure('IMAGE_NOT_FOUND', 404)
        return Response(data, media_type=media, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
    raise ProjectFailure('IMAGE_NOT_FOUND', 404)
