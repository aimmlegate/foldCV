"""The template icons a Focus row can take, for the facts panel's search (D122)."""

from packages.resume_core.template_panel_focus import icon_choices
from packages.resume_core.templates.models import remember_asset

from .errors import ProjectFailure


def choices(service, project_id):
    project = service.repository.read(project_id).project
    if project is None:
        raise ProjectFailure('FOCUS_ICONS_UNAVAILABLE', 409)
    try:
        value, assets = icon_choices(project, service.remembered_icons())
    except ValueError:
        raise ProjectFailure('FOCUS_ICONS_UNAVAILABLE', 409) from None
    # Packed and generated icons are no assets of their own; the asset route serves their checked bytes by hash.
    for asset in assets:
        remember_asset(asset.sha256, asset.bytes_base64, asset.mime_type)
    return value
