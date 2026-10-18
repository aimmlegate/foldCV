"""Rich snapshots/portable bytes, version isolation and monotonic stale-save guards."""

import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_archive_zip import ArchiveFailure, read_zip, write_zip
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.rich_archive import archive_payload, export_rich_archive, open_rich_archive
from packages.resume_core.rich_images import ImageFailure, normalize_image
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rendering.rich_docx import render_rich_docx
from packages.resume_core.rules import RulesStore
from resume_api.rich_projects import RichProjectService
from tests.recovery.generation_fixtures import CreationProvider, frozen_now
from tests.support.importing import importer, complete
from resume_api.agent.runtime import RuntimeResult


def fixture():
    return WorkspaceV6.model_validate(json.loads(Path("tests/fixtures/rich_workspace.json").read_text()))


def without_sources():
    workspace = fixture()
    from packages.resume_core.rendering.rich_template import require_rich_template
    workspace.project.template = require_rich_template().manifest
    workspace.project.sources = []
    workspace.project.assets = []
    workspace.project.document.regions[2].blocks = [b for b in workspace.project.document.regions[2].blocks if b.type != "image"]
    return workspace


def image_asset(workspace):
    image = Image.new("RGB", (16, 8), "red")
    output = BytesIO(); image.save(output, format="PNG")
    asset, blob = normalize_image(output.getvalue(), "asset-test")
    workspace.project.assets = [asset]
    from packages.resume_core.models.rich_document import ImageBlock
    workspace.project.document.regions[2].blocks.append(ImageBlock.model_validate({"type": "image", "id": "test-image",
        "revision": 1, "children": [], "provenance": [], "content": None, "props": {"assetId": asset.id,
            "alt": "red test", "caption": [], "width": 160.0, "height": 80.0, "alignment": "left"}}))
    return asset, blob


def patch(workspace, text="Changed", identifier="change-1"):
    block = workspace.project.document.regions[0].blocks[0].model_copy(deep=True)
    block.content[0].text = text
    return RichMutation.model_validate({"schemaVersion": 1, "projectId": workspace.project_id,
        "clientMutationId": identifier, "actionId": identifier, "kind": "typing",
        "capture": {"sessionId": "session", "actionId": identifier, "actionToken": 0, "dependencies": []},
        "steps": [{"kind": "put_block", "parentId": "header", "afterId": None,
            "beforeRevision": block.revision, "block": block.model_dump(by_alias=True)}]})


@pytest.mark.asyncio
async def test_extraction_diagnostics_survive_typing_undo_and_durable_reopen(tmp_path, monkeypatch):
    runtime, _sessions = importer(monkeypatch)
    from packages.resume_core.background_inverse import inverse_mutation
    from packages.resume_core.rich_mutations import locate
    provider = CreationProvider()
    store_root = tmp_path / "store"
    service = RichProjectService(tmp_path / "operations", RulesStore(store_root), lambda: (provider, "fixture"), import_runtime=runtime)
    try:
        data = Path("tests/fixtures/recovery/E1.txt").read_bytes()
        selected = await service.select(data, "E1.txt", True)
        pid = selected.project_id
        generation = service.start(pid)
        await service.tasks[(pid, generation)]
        before = service.read(pid).model_copy(deep=True)
        report = before.project.facts.extraction.model_copy(deep=True)
        block = next(block for block in before.project.document.blocks() if block.type == "paragraph"
            and isinstance(block.content, list) and any(span.type == "text" for span in block.content)).model_copy(deep=True)
        next(span for span in block.content if span.type == "text").text += " QA edit"
        siblings, index, parent = locate(before.project.document, block.id)
        request = RichMutation(schemaVersion=1, projectId=pid, clientMutationId="keep-report", actionId="keep-report",
            kind="typing", capture={"sessionId": "qa", "actionId": "keep-report", "actionToken": 0, "dependencies": []},
            steps=[{"kind": "put_block", "parentId": parent.id, "afterId": siblings[index - 1].id if index else None,
                "beforeRevision": block.revision, "block": block.model_dump(by_alias=True), "keepChildren": True}])
        service.mutate(pid, request)
        edited = service.read(pid).model_copy(deep=True)
        assert edited.project.facts.extraction == report
        assert before.project.facts.extraction == report
        undo = inverse_mutation(before, edited, mutation_id="undo-report", session_id="qa")
        service.mutate(pid, undo)
        assert service.read(pid).project.facts.extraction == report
        transferred, *_ = open_rich_archive(service.portable(pid), "report-copy")
        assert transferred.project.facts.extraction == report
        assert service.originals[(pid, before.project.sources[0].id)] == data
        assert len(runtime.calls) == 1 and not provider.calls
    finally:
        await service.shutdown()
    reopened = RichProjectService(tmp_path / "reopened", RulesStore(store_root), lambda: None)
    assert reopened.read(pid).project.facts.extraction == report


def test_rich_snapshot_and_portable_preserve_styles_ids_owned_image_bytes(tmp_path):
    workspace = without_sources(); asset, blob = image_asset(workspace)
    store = RichProjectStore(tmp_path / "store")
    images = {(workspace.project_id, asset.id): blob}
    store.save(workspace, {}, {}, images)
    loaded, errors, _ = RichProjectStore(tmp_path / "store").load_all()
    recovered, _, _, recovered_images = loaded[workspace.project_id]
    assert errors == {} and recovered == workspace and recovered_images == images
    archive = export_rich_archive(workspace, {}, {}, {asset.id: blob})
    files = read_zip(archive)
    assert files[asset.path] == blob
    raw = json.loads(files["workspace.json"])
    assert "undoSlots" not in raw and "editSessions" not in raw and "generations" not in raw
    imported, originals, artifacts, imported_images = open_rich_archive(archive, "imported")
    assert imported.project.document == workspace.project.document and imported.project.facts == workspace.project.facts
    assert imported_images == {asset.id: blob} and originals == artifacts == {}
    assert imported.project_id == imported.project.project_id == "imported"


@pytest.mark.parametrize("version", [5, 99])
def test_unsupported_local_versions_stay_listed_unchanged_and_supported_projects_open(version, tmp_path):
    workspace = without_sources(); store = RichProjectStore(tmp_path)
    store.save(workspace, {}, {})
    other = workspace.model_copy(deep=True)
    other.project_id = other.project.project_id = "unsupported"
    store.save(other, {}, {})
    path = tmp_path / "projects/unsupported/workspace.json"
    raw = json.loads(path.read_bytes()); raw["schemaVersion"] = version
    path.write_text(json.dumps(raw)); before = path.read_bytes()
    loaded, errors, registry = RichProjectStore(tmp_path).load_all()
    assert set(loaded) == {workspace.project_id} and errors == {"unsupported": "PROJECT_VERSION_UNSUPPORTED"}
    assert {e.project_id for e in registry.entries} == {workspace.project_id, "unsupported"}
    assert path.read_bytes() == before
    store.tombstone("unsupported")
    assert store.cleanup_deleted("unsupported").cleanup_status == "complete"
    assert not path.exists()
    assert store.load_all()[0][workspace.project_id][0] == workspace


@pytest.mark.parametrize("version", [5, 99])
def test_portable_known_old_and_future_version_never_migrate(version):
    workspace = without_sources()
    files = archive_payload(workspace, {}, {})
    manifest = json.loads(files["manifest.json"]); manifest["schemaVersion"] = version
    files["manifest.json"] = json.dumps(manifest).encode()
    with pytest.raises(ArchiveFailure, match="ARCHIVE_VERSION_UNSUPPORTED"):
        open_rich_archive(write_zip(files), "new")


def test_stale_store_cannot_overwrite_newer_snapshot_and_replay_cannot_reuse_payload(tmp_path):
    workspace = without_sources(); first = RichProjectStore(tmp_path); first.save(workspace, {}, {})
    second = RichProjectStore(tmp_path); old = second.load_all()[0][workspace.project_id][0]
    request = patch(workspace)
    new, replay = apply_rich_mutation(workspace, request)
    first.save(new, {}, {})
    assert not replay and apply_rich_mutation(new, request)[1]
    with pytest.raises(RichMutationFailure, match="MUTATION_ID_REUSED"):
        apply_rich_mutation(new, patch(workspace, "Other"))
    old, _ = apply_rich_mutation(old, patch(old, "Stale", "stale"))
    with pytest.raises(ProjectStoreFailure, match="PROJECT_REVISION_CHANGED"):
        second.save(old, {}, {})
    assert RichProjectStore(tmp_path).load_all()[0][workspace.project_id][0] == new


def test_archive_image_integrity_and_optional_cache_omission_preserve_required_content():
    workspace = without_sources(); asset, blob = image_asset(workspace)
    files = archive_payload(workspace, {}, {asset.id: blob})
    files[asset.path] = b"wrong"
    with pytest.raises(ArchiveFailure, match="ARCHIVE_HASH_MISMATCH"):
        open_rich_archive(write_zip(files), "new")
    files = archive_payload(workspace, {}, {asset.id: blob})
    files["images/unlisted.png"] = blob
    with pytest.raises(ArchiveFailure, match="ARCHIVE_MANIFEST_INVALID"):
        open_rich_archive(write_zip(files), "new")
    assert all(b"blob:" not in data for name, data in files.items() if name.endswith("json"))


def test_corrupt_image_isolated_on_restart_preserves_other_projects_and_original_bytes(tmp_path):
    workspace = without_sources(); asset, blob = image_asset(workspace)
    store = RichProjectStore(tmp_path)
    store.save(workspace, {}, {}, {(workspace.project_id, asset.id): blob})
    other = without_sources(); other.project_id = other.project.project_id = "other"
    store.save(other, {}, {})
    path = tmp_path / "projects" / workspace.project_id / asset.path
    path.write_bytes(blob[:-1] + bytes([blob[-1] ^ 1]))
    before = path.read_bytes()
    loaded, errors, _ = RichProjectStore(tmp_path).load_all()
    assert set(loaded) == {"other"} and errors == {workspace.project_id: "IMAGE_BYTES_MISMATCH"}
    assert path.read_bytes() == before


def test_portable_capacity_counts_required_bytes_and_omits_cache_before_rejecting(tmp_path):
    from packages.resume_core.models.contracts import Source
    from packages.resume_core.models.rich_workspace import RichRenderSnapshot
    from packages.resume_core.rendering.rich_docx import renderer_sha256
    from packages.resume_core.rendering.rich_template import PACKAGE_SHA256
    workspace = without_sources()
    blob = b"x" * (30 * 1024 * 1024)
    checksum = hashlib.sha256(blob).hexdigest()
    workspace.project.sources = [Source(id="source", revision=1, originalName="large.txt", mimeType="text/plain",
        byteSha256=checksum, byteRef="sources/source/original", parser="text", parserVersion="1", units=[], overlays=[], warnings=[])]
    cached = b"y" * (32 * 1024 * 1024)
    render = RichRenderSnapshot(id="cache", documentRevision=workspace.document_revision, factsRevision=workspace.project.facts.revision,
        templateSha256=PACKAGE_SHA256, rendererVersion="1.0.0", rendererSha256=renderer_sha256(),
        docxSha256=hashlib.sha256(cached).hexdigest(), docxSize=len(cached), docxPath="renders/cache.docx")
    payload = archive_payload(workspace, {"source": blob}, {}, (render, cached))
    assert "sources/source/original" in payload and "renders/cache.docx" not in payload
    second = workspace.project.sources[0].model_copy(deep=True)
    second.id, second.byte_ref = "second", "sources/second/original"
    workspace.project.sources.append(second)
    with pytest.raises(ProjectStoreFailure, match="ARCHIVE_CAPACITY_LIMIT"):
        RichProjectStore(tmp_path).save(workspace, {(workspace.project_id, "source"): blob, (workspace.project_id, "second"): blob}, {})
    assert not (tmp_path / "projects" / workspace.project_id).exists()


def test_image_animation_format_and_normalized_dimensions_are_checked_before_publication():
    output = BytesIO()
    Image.new("RGB", (8, 4), "red").save(output, format="WEBP")
    asset, blob = normalize_image(output.getvalue(), "webp")
    assert asset.mime_type == "image/png" and (asset.width, asset.height) == (8, 4) and blob.startswith(b"\x89PNG")
    output = BytesIO()
    Image.new("RGB", (8, 4), "red").save(output, format="PNG", save_all=True, append_images=[Image.new("RGB", (8, 4), "blue")])
    with pytest.raises(ImageFailure, match="IMAGE_ANIMATED"):
        normalize_image(output.getvalue(), "animated")
    with pytest.raises(ImageFailure, match="IMAGE_INVALID"):
        normalize_image(b"broken", "broken")
    with pytest.raises(ImageFailure, match="IMAGE_INPUT_LIMIT"):
        normalize_image(b"x" * (10 * 1024 * 1024 + 1), "large")


@pytest.mark.asyncio
async def test_fresh_rich_creation_initial_docx_restart_and_portable_without_inference(tmp_path, monkeypatch):
    runtime, _sessions = importer(monkeypatch)
    provider = CreationProvider(fail_kind="GuiDraftProposal")
    service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"), lambda: (provider, "fixture"), clock=frozen_now, import_runtime=runtime)
    data = Path("tests/fixtures/recovery/E1.txt").read_bytes()
    selected = await service.select(data, "pasted.txt", True)
    identifier = selected.project_id
    generation = service.start(identifier)
    await service.tasks[(identifier, generation)]
    assert service.generations[identifier].status == "completed"
    workspace = service.read(identifier)
    assert workspace.schema_version == 6 and workspace.project.schema_version == 5 and len(runtime.calls) == 1 and not provider.calls
    assert service.durability(identifier) == "durable" and workspace.project.renders
    from packages.resume_core.rich_presentation import authored_text
    units = workspace.project.sources[0].units
    from collections import Counter
    import re
    text = " ".join(authored_text(block) for block in workspace.project.document.blocks())
    assert not (Counter(re.findall(r"\w+", data.decode())) - Counter(re.findall(r"\w+", text)))
    assert all(region.blocks for region in workspace.project.document.regions)
    assert len(workspace.project.import_coverage) == len(units)
    assert workspace.project.facts.mode == "digest" and any(record.kind == "claim" for record in workspace.project.facts.records)
    assert {operation.kind for operation in workspace.project.operations} == {"normalize_semantics", "render"}
    assert service.originals[(identifier, workspace.project.sources[0].id)] == data
    snapshot, docx = await service.export(identifier)
    with ZipFile(BytesIO(docx)) as archive:
        xml = archive.read("word/document.xml").decode()
        assert "Ирина Примерова" in xml and "w:rFonts" in xml
        assert len([name for name in archive.namelist() if name.endswith(".odttf")]) == 5
        assert "saveSubsetFonts" in archive.read("word/settings.xml").decode()
    reopened = RichProjectService(tmp_path / "operations-2", RulesStore(tmp_path / "store"), lambda: (provider, "fixture"), clock=frozen_now, import_runtime=runtime)
    assert reopened.read(identifier) == workspace and len(runtime.calls) == 1 and not provider.calls
    assert (await reopened.export(identifier))[1] == docx
    portable = reopened.portable(identifier)
    other = RichProjectService(tmp_path / "operations-3", RulesStore(tmp_path / "other"), lambda: (provider, "fixture"), clock=frozen_now, import_runtime=runtime)
    imported = other.import_portable(portable)
    assert other.read(imported).project.document == workspace.project.document
    assert other.read(imported).project.renders == []
    assert len(runtime.calls) == 1 and not provider.calls


@pytest.mark.asyncio
async def test_technical_render_failure_keeps_imported_rich_content_but_cannot_claim_completed_export(tmp_path, monkeypatch):
    runtime, _sessions = importer(monkeypatch)
    from packages.resume_core.rendering.template import RenderFailure
    class FailedRenderer:
        async def render(self, *_args):
            raise RenderFailure("RENDER_OUTPUT_LIMIT")
    provider = CreationProvider()
    service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"), lambda: (provider, "fixture"),
        clock=frozen_now, renderer=FailedRenderer(), import_runtime=runtime)
    selected = await service.select(Path("tests/fixtures/recovery/E1.txt").read_bytes(), "pasted.txt", True)
    identifier = selected.project_id
    generation = service.start(identifier); await service.tasks[(identifier, generation)]
    state = service.generations[identifier]
    assert state.status == "failed" and state.error_code == "RENDER_OUTPUT_LIMIT"
    workspace = service.read(identifier)
    assert workspace.project is not None and workspace.project.renders == []
    assert workspace.project.document.regions[2].blocks and service.durability(identifier) == "durable"
    assert len(runtime.calls) == 1 and not provider.calls


@pytest.mark.asyncio
async def test_empty_digest_keeps_source_as_an_editable_partial_result(tmp_path, monkeypatch):
    async def script(session, value, cancel):
        await complete(session, facts=False)
        return RuntimeResult(state="completed")
    runtime, _sessions = importer(monkeypatch, script)
    data = Path("tests/fixtures/recovery/E1.txt").read_bytes()
    service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"),
        lambda: (object(), "fixture"), clock=frozen_now, import_runtime=runtime)
    selected = await service.select(data, "pasted.txt", True)
    generation = service.start(selected.project_id)
    await service.tasks[(selected.project_id, generation)]
    assert service.generations[selected.project_id].status == "completed"
    workspace = service.read(selected.project_id)
    assert workspace.project is not None and workspace.pre_draft is None
    report = workspace.project.facts.extraction
    assert report.fact_count == 0 and report.status == "partial"
    assert any("пуста" in issue.section for issue in report.unresolved)
    assert any(warning.code == "source_details_unresolved" for warning in workspace.warnings)
    assert "".join(unit.text for unit in workspace.project.sources[0].units) == data.decode()
    assert service.originals[(selected.project_id, workspace.project.sources[0].id)] == data
    reopened = RichProjectService(tmp_path / "operations-2", RulesStore(tmp_path / "store"), lambda: None, clock=frozen_now)
    assert reopened.read(selected.project_id) == workspace
    imported, *_ = open_rich_archive(reopened.portable(selected.project_id), "empty-import")
    assert imported.project.facts == workspace.project.facts and imported.warnings == workspace.warnings
    assert runtime.calls == ["fixture"]
