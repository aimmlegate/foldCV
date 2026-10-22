"""Canonical saves preserve captured packages and immutable source observations."""

import pytest
import json
from io import BytesIO
from PIL import Image

from packages.resume_core.models.template_facts import Observation, WorkingFactsV2
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.gui_archive_zip import ArchiveFailure, digest, read_zip, write_zip
from packages.resume_core.rich_images import normalize_image
from packages.resume_core.models.template_document import TemplateImageBlock
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.templates.compiler import canonical, compile_bytes, sha256
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.storage_fixtures import workspace
from tests.templates.test_transactions import extension_step, request
from packages.resume_core.template_facts import human_edit
from packages.resume_core.rich_mutations import apply_rich_mutation


def bump(value):
    changed = value.model_copy(deep=True)
    changed.project_revision += 1
    changed.document_revision += 1
    changed.project.revision = changed.project_revision
    changed.project.document.revision = changed.document_revision
    return changed


@pytest.mark.parametrize('rewrite', ['package', 'source_unit', 'observation'])
def test_save_cannot_replace_retained_template_source_or_observation(tmp_path, rewrite):
    before, sources = workspace()
    before.project.facts.observations = [Observation(id='observation', itemHandle='handle-a', fieldKey='title',
        rawInput='Retained interpretation', typedValue=None, evidence=before.project.facts.extensions[0].cells[0].evidence,
        ownerRelations=[], proposalHash=sha256(b'proposal'), admission='uncertain', receiptIds=[])]
    store = RichProjectStore(tmp_path / 'isolated')
    originals = {(before.project_id, key): data for key, data in sources.items()}
    store.save(before, originals, {})
    path = store.projects / before.project_id / 'workspace.json'
    original = path.read_bytes()
    changed = bump(before)
    if rewrite == 'package':
        config = before.project.template_package.definition.model_dump(by_alias=True)
        config['template']['revision'] = '2'
        config['style']['text']['body']['size'] = 11
        package = compile_bytes(canonical(config), BUNDLED_TEMPLATE.parent, original_format='json')
        changed.project.template_package = package
        for block in changed.project.document.blocks():
            block.presentation.package_hash = package.package_hash
            for span in block.content:
                span.presentation.package_hash = package.package_hash
    elif rewrite == 'source_unit':
        changed.project.sources[0].units[0].text += ' Forged appended content.'
    else:
        changed.project.facts.observations[0].raw_input = 'Replaced observation'
    with pytest.raises(ProjectStoreFailure):
        store.save(changed, originals, {})
    assert path.read_bytes() == original
    assert RichProjectStore(tmp_path / 'isolated').load_all()[0][before.project_id][0] == before


def test_source_only_pre_draft_round_trip_never_selects_an_installed_template(tmp_path):
    value, sources = workspace()
    data = value.model_dump(by_alias=True)
    data['preDraft'] = {'selectedInput': 'text', 'selectedSourceId': value.project.sources[0].id,
        'sources': data['project']['sources'], 'facts': WorkingFactsV2(schemaVersion=2, revision=1,
            records=[], tombstones=[], extensions=[], observations=[], relations=[], manualScopes=[]).model_dump(by_alias=True),
        'operations': [], 'warnings': [], 'templatePackage': None, 'templateOperations': []}
    data['project'] = None
    draft = WorkspaceV7.model_validate(data)
    store = RichProjectStore(tmp_path / 'isolated')
    store.save(draft, {(draft.project_id, key): data for key, data in sources.items()}, {})
    reopened = RichProjectStore(tmp_path / 'isolated').load_all()[0][draft.project_id][0]
    assert reopened == draft and reopened.pre_draft.template_package is None
    copied, retained, _, _ = open_rich_archive(export_rich_archive(reopened, sources, {}, {}), 'pre-draft-copy')
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


def test_failed_atomic_save_keeps_old_disk_and_exact_retry_does_not_reapply_history(tmp_path, monkeypatch):
    from packages.resume_core import rich_project_store as module
    before, sources = workspace()
    store = RichProjectStore(tmp_path / 'isolated')
    originals = {(before.project_id, key): data for key, data in sources.items()}
    store.save(before, originals, {})
    path = store.projects / before.project_id / 'workspace.json'
    previous = path.read_bytes()
    raw = human_edit(before.project.facts, 'paper-a', 'year', 'forthcoming')
    command = request(before, [extension_step(before, raw.extensions[0])])
    candidate, _ = apply_rich_mutation(before, command)
    write = module.atomic_write
    def failing(target, data, **kwargs):
        if target.name == 'workspace.json':
            raise OSError('synthetic disk failure')
        return write(target, data, **kwargs)
    monkeypatch.setattr(module, 'atomic_write', failing)
    with pytest.raises(ProjectStoreFailure, match='PROJECT_SAVE_FAILED'):
        store.save(candidate, originals, {})
    assert path.read_bytes() == previous
    assert candidate.project.facts.extensions[0].cells[2].raw_input == 'forthcoming'
    retry, replayed = apply_rich_mutation(candidate, command)
    assert replayed and retry == candidate
    monkeypatch.setattr(module, 'atomic_write', write)
    store.save(retry, originals, {})
    assert RichProjectStore(tmp_path / 'isolated').load_all()[0][before.project_id][0] == candidate


def test_rehashed_invalid_image_has_an_archive_integrity_outcome():
    value, sources = workspace()
    buffer = BytesIO()
    Image.new('RGB', (16, 8), 'red').save(buffer, format='PNG')
    asset, blob = normalize_image(buffer.getvalue(), 'synthetic-image')
    value.project.assets = [asset]
    value.project.document.regions[2].blocks.append(TemplateImageBlock(type='image', id='image-block', revision=1,
        children=[], provenance=[], content=None, presentation=value.project.document.regions[2].blocks[0].presentation,
        props={'assetId': asset.id, 'alt': 'Synthetic image', 'caption': [], 'width': 160, 'height': 80, 'alignment': 'left'}))
    files = read_zip(export_rich_archive(value, sources, {}, {asset.id: blob}))
    files[asset.path] = b'corrupt normalized image'
    manifest = json.loads(files['manifest.json'])
    entry = next(item for item in manifest['entries'] if item['path'] == asset.path)
    entry.update(size=len(files[asset.path]), sha256=digest(files[asset.path]))
    files['manifest.json'] = json.dumps(manifest).encode()
    with pytest.raises(ArchiveFailure, match='ARCHIVE_IMAGE_MISMATCH'):
        open_rich_archive(write_zip(files), 'bad-image-copy')
    with pytest.raises(ArchiveFailure, match='ARCHIVE_IMAGE_MISMATCH'):
        export_rich_archive(value, sources, {}, {asset.id: b'wrong bytes'})
