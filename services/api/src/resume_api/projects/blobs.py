"""Read only private, owned project files; map retained import blobs to their existing names."""

from packages.resume_core.project_store import owned_file
from packages.resume_core.storage import StorageFailure

from .errors import ProjectFailure


def read_owned(path, maximum, missing):
    if not path.exists() and not path.is_symlink():
        raise ProjectFailure(missing, 404)
    try:
        owned_file(path, maximum)
        return path.read_bytes()
    except FileNotFoundError:
        raise ProjectFailure(missing, 404) from None
    except StorageFailure:
        raise ProjectFailure('PROJECT_UNSAFE_STORAGE', 503) from None
    except OSError:
        raise ProjectFailure(missing, 404) from None


def retained_blobs(project, workspace, originals, artifacts, images):
    def lookup(mapping, key):
        return mapping.get((project, key), mapping.get(key))
    owner = workspace.project or workspace.pre_draft
    if owner is None:
        return []
    blobs = []
    for source in owner.sources:
        blob = lookup(originals, source.id)
        if blob is not None:
            blobs.append(('sources', source.id, blob, source.byte_sha256))
    if workspace.project is not None:
        for asset in workspace.project.assets:
            blob = lookup(images, asset.id)
            if blob is not None:
                blobs.append(('images', asset.path, blob, asset.sha256))
        for render in workspace.project.renders:
            blob = lookup(artifacts, render.id)
            if blob is not None:
                blobs.append(('renders', render.id, blob, render.docx_sha256))
    return blobs
