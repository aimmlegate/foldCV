"""Presentation and snapshot identity come only from the project's captured package."""

from ..models.template_render import presentation_value
from ..template_export import snapshot_identity as authored_snapshot_identity


SUPPORTED_AUTHORING = frozenset({'node_index'})


def validate_presentation(document, package):
    from ..rich_fields import inline_groups
    for block in document.blocks():
        if block.presentation is None:
            raise ValueError('template block has no authored presentation')
        refs = [block.presentation]
        for _container, group in inline_groups(block):
            for part in group:
                refs.append(getattr(part, 'presentation', None))
                refs.extend(getattr(child, 'presentation', None) for child in getattr(part, 'content', []))
        for ref in refs:
            if ref is None:
                continue
            if (ref.package_hash != package.package_hash or ref.view_key not in package.recipe.views
                    or ref.style_token not in package.recipe.style.text):
                raise ValueError('unsupported captured presentation reference')
            if ref.node_index is not None and ('node_index' not in SUPPORTED_AUTHORING
                    or ref.node_index >= len(package.recipe.views[ref.view_key].nodes)):
                raise ValueError('unsupported template node presentation')


def snapshot_identity(workspace):
    if workspace.project is None:
        return None
    return authored_snapshot_identity(workspace)


def project_presentation(workspace):
    snapshot = snapshot_identity(workspace)
    if snapshot is None:
        return None
    project = workspace.project
    validate_presentation(project.document, project.template_package)
    return {'schemaVersion': 1, 'snapshot': snapshot.model_dump(mode='json', by_alias=True),
        **presentation_value(project.document, project.template_package)}
