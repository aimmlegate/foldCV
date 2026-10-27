"""Stored and portable pre-drafts keep their exact sources; archive images are checked by content."""

import pytest
import json
from io import BytesIO
from PIL import Image

from packages.resume_core.models.template_facts import WorkingFactsV2
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
from packages.resume_core.archive_zip import ArchiveFailure, digest, read_zip, write_zip
from packages.resume_core.rich_images import normalize_image
from packages.resume_core.models.template_document import TemplateImageBlock
from packages.resume_core.project_repository import ProjectRepository
from tests.templates.editor_fixtures import source_blobs
from tests.templates.storage_fixtures import workspace


def test_source_only_pre_draft_round_trip_never_selects_an_installed_template(tmp_path):
    value, sources = workspace()
    data = value.model_dump(by_alias=True)
    data['preDraft'] = {'selectedInput': 'text', 'selectedSourceId': value.project.sources[0].id,
        'sources': data['project']['sources'], 'facts': WorkingFactsV2(schemaVersion=2, revision=1,
            records=[], tombstones=[], extensions=[], observations=[], relations=[], manualScopes=[]).model_dump(by_alias=True),
        'operations': [], 'warnings': [], 'templatePackage': None, 'templateOperations': []}
    data['project'] = None
    draft = WorkspaceV7.model_validate(data)
    ProjectRepository(tmp_path / 'isolated').create(draft, blobs=source_blobs(sources))
    reopened = ProjectRepository(tmp_path / 'isolated').read(draft.project_id)
    assert reopened == draft and reopened.pre_draft.template_package is None
    copied, retained, _, _ = open_archive_v7(write_zip(archive_payload_v7(reopened, sources, {})), 'pre-draft-copy')
    assert copied.pre_draft == draft.pre_draft and retained == sources


def test_pre_draft_cannot_carry_generic_assertions_without_its_package():
    value, _ = workspace()
    data = value.model_dump(by_alias=True)
    data['preDraft'] = {'selectedInput': 'text', 'selectedSourceId': value.project.sources[0].id,
        'sources': data['project']['sources'], 'facts': data['project']['facts'], 'operations': [], 'warnings': [],
        'templatePackage': None, 'templateOperations': []}
    data['project'] = None
    with pytest.raises(ValueError, match='captured package'):
        WorkspaceV7.model_validate(data)


def test_rehashed_invalid_image_has_an_archive_integrity_outcome():
    value, sources = workspace()
    buffer = BytesIO()
    Image.new('RGB', (16, 8), 'red').save(buffer, format='PNG')
    asset, blob = normalize_image(buffer.getvalue(), 'synthetic-image')
    value.project.assets = [asset]
    value.project.document.regions[2].blocks.append(TemplateImageBlock(type='image', id='image-block', revision=1,
        children=[], provenance=[], content=None, presentation=value.project.document.regions[2].blocks[0].presentation,
        props={'assetId': asset.id, 'alt': 'Synthetic image', 'caption': [], 'width': 160, 'height': 80, 'alignment': 'left'}))
    files = read_zip(write_zip(archive_payload_v7(value, sources, {asset.id: blob})))
    files[asset.path] = b'corrupt normalized image'
    manifest = json.loads(files['manifest.json'])
    entry = next(item for item in manifest['entries'] if item['path'] == asset.path)
    entry.update(size=len(files[asset.path]), sha256=digest(files[asset.path]))
    files['manifest.json'] = json.dumps(manifest).encode()
    with pytest.raises(ArchiveFailure, match='ARCHIVE_IMAGE_MISMATCH'):
        open_archive_v7(write_zip(files), 'bad-image-copy')
    with pytest.raises(ArchiveFailure, match='ARCHIVE_IMAGE_MISMATCH'):
        write_zip(archive_payload_v7(value, sources, {asset.id: b'wrong bytes'}))
