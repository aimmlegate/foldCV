"""The résumé's photo (D187): add, replace or remove, one history action each. The client sends the cropped square;
Python checks it again and stores it in the project's images; the file stays while history can bring it back."""

from __future__ import annotations

import base64
import binascii
import hashlib

from packages.resume_core.image_check import check_image
from packages.resume_core.models.rich_workspace import LocalImageAsset
from packages.resume_core.models.projects import digest_request

from .errors import ProjectFailure


def set_photo(service, project_id, request):
    from .editing import result
    session = service.repository.open(project_id)
    with session.lock:
        session.require_editor(request.editor_token)
        service.require_writable(project_id)
    photo, blobs = None, []
    if request.image is not None:
        try:
            data = base64.b64decode(request.image, validate=True)
            checked = check_image(data, 'photo')
        except (ValueError, binascii.Error) as error:
            code = str(error) if str(error).startswith('IMAGE_') else 'IMAGE_INVALID'
            raise ProjectFailure(code, 422) from None
        digest = hashlib.sha256(data).hexdigest()
        extension = 'jpg' if checked.mime_type == 'image/jpeg' else 'png'
        photo = LocalImageAsset(id='photo-' + digest[:32], sha256=digest, path=f'images/{digest}.{extension}',
            mimeType=checked.mime_type, size=len(data), width=checked.width, height=checked.height)
        blobs = [('images', photo.path, data, digest)]

    def build(committed):
        if committed.project is None:
            raise ProjectFailure('IMPORT_PROJECT_NOT_AUTHORED', 409)
        if committed.project.photo == photo:
            return None
        after = committed.model_copy(deep=True)
        after.project.photo = photo
        return after, {}
    outcome = service.repository.mutate(project_id, base_revision=request.base_revision,
        client_mutation_id=request.client_mutation_id, request_sha256=digest_request(request.model_dump(mode='json',
            by_alias=True, exclude={'editor_token'})), action_id=request.client_mutation_id, kind='edit', build=build,
        blobs=blobs)
    return result(service, session, outcome, request.client_mutation_id)
