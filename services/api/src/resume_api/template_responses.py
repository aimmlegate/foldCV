"""Keep new snapshot responses on the same canonical numeric encoding as hashes."""

from fastapi.responses import JSONResponse, Response

from packages.resume_core.template_api import TemplateProjectResponseV1
from packages.resume_core.templates.compiler import canonical


def wire_response(value, *, status=200):
    if isinstance(value, TemplateProjectResponseV1) or getattr(value, 'schema_version', None) == 2:
        return Response(canonical(value), status_code=status, media_type='application/json', headers={'Cache-Control': 'no-store'})
    return JSONResponse(value.model_dump(mode='json', by_alias=True), status_code=status, headers={'Cache-Control': 'no-store'})
