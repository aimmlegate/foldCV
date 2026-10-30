"""Portable .foldcv export and import through the unchanged v7 archive format."""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from packages.resume_core.archive_zip import ArchiveFailure, write_zip
from packages.resume_core.project_repository import blob_path, decode_project
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.storage import StorageFailure
from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
from packages.resume_core.template_import import identity
from packages.resume_core.extraction.parser import MAX_SOURCE
from packages.resume_core.rich_limits import IMAGE_BYTES

from .blobs import read_owned
from .errors import STATUS, ProjectFailure


class ArchiveDownload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, strict=True, extra='forbid')
    editor_token: str = Field(alias='editorToken', min_length=1)
    project_revision: int = Field(alias='projectRevision')
    document_revision: int = Field(alias='documentRevision')


def export_archive(service, project_id, request, *, trusted=False):
    """The open editor's project as a .foldcv file. The journal stays on disk. `trusted` is the assistant's export.
    The lock covers the project file and the images, which a sweep may remove. Sources and import records are
    content-addressed and stay until delete, so they are read, and the zip is built, after the lock."""
    session = service.repository.open(project_id)
    try:
        with session.lock:
            if not trusted:
                session.require_editor(request.editor_token)
            workspace = service.repository.read(project_id)
            if (workspace.project_revision, workspace.document_revision) != (request.project_revision, request.document_revision):
                raise ProjectFailure('STALE_ARCHIVE', 409)
            raw = (session.directory / 'workspace.json').read_bytes()
            images = {}
            if workspace.project is not None:
                for asset in workspace.project.assets:
                    path = session.directory / asset.path
                    if path.is_file():
                        images[asset.id] = read_owned(path, IMAGE_BYTES, 'IMAGE_NOT_FOUND')
        loaded = decode_project(session.directory, raw, history=True)
        owner = loaded.project or loaded.pre_draft
        originals = {}
        for source in owner.sources:
            path = blob_path(session.directory, 'sources', source.id)
            originals[source.id] = read_owned(path, MAX_SOURCE, 'SOURCE_BYTES_MISSING')
        return write_zip(archive_payload_v7(loaded, originals, images))
    except ArchiveFailure as error:
        raise ProjectFailure(error.code, 422) from None
    except ProjectFailure:
        raise
    except ProjectStoreFailure as error:
        raise ProjectFailure(error.code, STATUS.get(error.code, 409)) from None
    except StorageFailure:
        raise ProjectFailure('PROJECT_UNSAFE_STORAGE', 503) from None
    except OSError:
        raise ProjectFailure('SOURCE_BYTES_MISSING', 404) from None
    except (ValueError, RecursionError):
        raise ProjectFailure('PROJECT_LOAD_FAILED', 503) from None


def import_archive(service, data):
    """Store an uploaded .foldcv as a new project."""
    project_id = identity('project')
    try:
        workspace, originals, _artifacts, images = open_archive_v7(data, project_id)
    except ArchiveFailure as error:
        raise ProjectFailure(error.code, 422) from None
    blobs = [('sources', source_id, blob, hashlib.sha256(blob).hexdigest()) for source_id, blob in originals.items()]
    owner = workspace.project
    if owner is not None:
        for asset in owner.assets:
            blob = images.get(asset.id)
            if blob is not None:
                blobs.append(('images', asset.path, blob, asset.sha256))
    service.repository.create(workspace, blobs=blobs)
    return service.response(project_id)
