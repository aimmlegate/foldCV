"""The template icons a Focus row can take, for the facts panel's search (D122)."""

from packages.resume_core.editing.template_panel_focus import icon_choices
from packages.resume_core.models.template_package import remember_asset

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
    # D187: the app's own icons, and the copies this résumé keeps, served by hash in the same way.
    own, seen = [], set()
    library = getattr(service, 'own_icons', None)
    for entry in library.list() if library is not None else []:
        assert library is not None
        icon = library.get(entry['id'])
        if icon is not None:
            remember_asset(icon.sha256, icon.bytes_base64, 'image/png')
            own.append({'id': icon.id, 'names': [icon.name], 'sha256': icon.sha256})
            seen.add(icon.id)
    for icon in project.own_icons:
        remember_asset(icon.sha256, icon.bytes_base64, 'image/png')
        if icon.id not in seen:
            own.append({'id': icon.id, 'names': [icon.name], 'sha256': icon.sha256, 'kept': True})
    return {**value, 'own': own}
