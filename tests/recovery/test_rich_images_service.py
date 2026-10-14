"""Image admission, durable history bytes and late ingestion through the real service."""

import asyncio
from io import BytesIO
import threading
import sys
from pathlib import Path

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.models.rich_document import ImageBlock
from packages.resume_core.rules import RulesStore
from resume_api.gui_projects import ProjectFailure
from resume_api.rich_assets import ImageSessionRequest, ImageUploadCapture
from resume_api.rich_projects import RichProjectService
from tests.recovery.test_rich_persistence import without_sources


def service(tmp_path):
    instance = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"), lambda: None)
    workspace = without_sources()
    instance.loaded = True; instance.workspaces[workspace.project_id] = workspace
    assert instance.persist(workspace.project_id) == "durable"
    return instance, workspace.project_id


def refs(service, identifier, revision, live=(), history=(), closed=False):
    service.update_image_session(identifier, ImageSessionRequest(sessionId="session", revision=revision,
        live=list(live), history=list(history), closed=closed))


def capture(revision=1, id="upload", replacement=None):
    return ImageUploadCapture(sessionId="session", revision=revision, actionId=id, reservationId=id, replacementId=replacement)


def png(color="red"):
    out = BytesIO(); Image.new("RGB", (16, 8), color).save(out, format="PNG"); return out.getvalue()


@pytest.mark.asyncio
async def test_image_upload_delete_undo_redo_and_abandoned_branch_retain_then_release_actual_bytes(tmp_path):
    instance, identifier = service(tmp_path); refs(instance, identifier, 1)
    aid = await instance.ingest_image(identifier, png(), capture())
    asset = instance.workspaces[identifier].project.assets[0]
    path = instance.storage.root / "projects" / identifier / asset.path
    assert path.is_file() and instance.images[(identifier, aid)] == path.read_bytes()
    refs(instance, identifier, 2, (aid,), (aid,))
    workspace = instance.workspaces[identifier]
    block = ImageBlock(id="photo", revision=1, children=[], provenance=[], type="image", content=None,
        props={"assetId": aid, "alt": "sample", "caption": [], "width": 160, "height": 80, "alignment": "center"})
    workspace.project.document.regions[2].blocks.append(block)
    assert instance.persist(identifier) == "durable"
    workspace.project.document.regions[2].blocks.pop()
    instance.persist(identifier); refs(instance, identifier, 3, (), (aid,))
    assert path.is_file()
    workspace.project.document.regions[2].blocks.append(block)
    refs(instance, identifier, 4, (aid,), (aid,)); instance.persist(identifier)
    assert path.read_bytes() == instance.images[(identifier, aid)]
    workspace.project.document.regions[2].blocks.pop(); instance.persist(identifier)
    refs(instance, identifier, 5, (), (aid,))
    assert path.is_file()
    refs(instance, identifier, 6)
    assert not path.exists() and instance.workspaces[identifier].project.assets == []
    assert (identifier, aid) not in instance.images and not instance.image_reservations


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["edit", "close", "server_edit"])
async def test_image_decode_reply_after_edit_or_session_close_publishes_no_asset_or_file(tmp_path, monkeypatch, change):
    instance, identifier = service(tmp_path); refs(instance, identifier, 1)
    from resume_api import rich_assets
    original = rich_assets.normalize_image
    started, finish = threading.Event(), threading.Event()
    def delayed(*args):
        started.set(); finish.wait(5); return original(*args)
    monkeypatch.setattr(rich_assets, "normalize_image", delayed)
    task = asyncio.create_task(instance.ingest_image(identifier, png(), capture()))
    assert await asyncio.to_thread(started.wait, 2)
    if change == "server_edit":
        from tests.recovery.test_rich_persistence import patch
        instance.mutate(identifier, patch(instance.read(identifier), "Newer server edit"))
    else:
        refs(instance, identifier, 2, closed=change == "close")
    before = instance.read(identifier)
    finish.set()
    with pytest.raises(ProjectFailure, match="STALE_IMAGE_INSERTION"):
        await task
    assert instance.read(identifier) == before
    assert not instance.images and not instance.image_reservations
    assert not list((instance.storage.root / "projects" / identifier / "images").glob("*"))


@pytest.mark.asyncio
async def test_concurrent_image_reservations_reject_twenty_first_and_cancel_releases_capacity(tmp_path, monkeypatch):
    instance, identifier = service(tmp_path); refs(instance, identifier, 1)
    from resume_api import rich_assets
    original = rich_assets.normalize_image
    gate = threading.Event()
    def delayed(*args):
        gate.wait(5); return original(*args)
    monkeypatch.setattr(rich_assets, "normalize_image", delayed)
    tasks = [asyncio.create_task(instance.ingest_image(identifier, png(), capture(id=f"upload-{i}"))) for i in range(20)]
    await asyncio.sleep(.05)
    assert len(instance.image_reservations) == 20
    with pytest.raises(ProjectFailure, match="IMAGE_CAPACITY_LIMIT"):
        await instance.ingest_image(identifier, png(), capture(id="overflow"))
    tasks[0].cancel(); gate.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert isinstance(results[0], asyncio.CancelledError)
    assert all(isinstance(result, str) for result in results[1:])
    assert len(instance.workspaces[identifier].project.assets) == 1
    assert not instance.image_reservations


@pytest.mark.asyncio
async def test_bad_image_does_not_change_durable_document_or_hold_capacity(tmp_path):
    instance, identifier = service(tmp_path); refs(instance, identifier, 1)
    before = instance.read(identifier)
    with pytest.raises(ProjectFailure, match="IMAGE_INVALID"):
        await instance.ingest_image(identifier, b"not an image", capture())
    assert instance.read(identifier) == before and not instance.image_reservations
    aid = await instance.ingest_image(identifier, png(), capture(id="valid"))
    refs(instance, identifier, 2, (aid,), (aid,))
    result = await instance.delete_project(identifier)
    assert result.status == "deleted" and not instance.images
    assert not (instance.storage.root / "projects" / identifier).exists()


@pytest.mark.asyncio
async def test_image_upload_has_an_authenticated_body_exception_without_raising_json_limits(tmp_path):
    import httpx
    from resume_api.app import create_app
    origin, secret = "http://127.0.0.1:39329", "synthetic-image-session-0123456789"
    dist = tmp_path / "dist"; dist.mkdir(); (dist / "index.html").write_text("fixture")
    app = create_app(origin=origin, secret=secret, temp_root=tmp_path / "operations", dist=dist, data_root=tmp_path / "store")
    instance = app.app.state.rich_projects
    workspace = without_sources(); identifier = workspace.project_id
    instance.loaded = True; instance.workspaces[identifier] = workspace; instance.persist(identifier)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin) as client:
        path = f"/v1/rich/projects/{identifier}/images/upload"
        assert (await client.post(path, headers={"Origin": origin}, files={"file": ("image.png", png(), "image/png")})).status_code == 401
        await client.post("/v1/session/exchange", headers={"Origin": origin}, json={"secret": secret})
        session = await client.post(f"/v1/rich/projects/{identifier}/images/session", headers={"Origin": origin},
            json={"sessionId": "session", "revision": 1, "live": [], "history": []})
        assert session.status_code == 200
        headers = {"Origin": origin, "X-FoldCV-Session": "session", "X-FoldCV-Revision": "1",
            "X-FoldCV-Action": "image", "X-FoldCV-Reservation": "image"}
        response = await client.post(path, headers=headers, files={"file": ("image.png", png() + b"\0" * (1024 * 1024), "image/png")})
        assert response.status_code == 201
        aid = response.headers["X-FoldCV-Asset"]
        content = await client.get(f"/v1/rich/projects/{identifier}/images/{aid}")
        assert content.status_code == 200 and content.headers["content-type"] == "image/png"
        assert content.content == instance.images[(identifier, aid)]
        assert (await client.post(path, headers=headers, files={"file": ("image.png", b"x" * (10 * 1024 * 1024 + 64 * 1024 + 1), "image/png")})).status_code == 413
        assert (await client.post(f"/v1/rich/projects/{identifier}/mutations", headers={"Origin": origin, "Content-Type": "application/json"}, content=b"x" * (1024 * 1024 + 1))).status_code == 413
        assert (await client.post(path, files={"file": ("image.png", png(), "image/png")})).status_code == 403


@pytest.mark.asyncio
async def test_replacement_and_reload_release_only_bytes_absent_from_document_and_new_history(tmp_path):
    instance, identifier = service(tmp_path); refs(instance, identifier, 1)
    old = await instance.ingest_image(identifier, png("red"), capture())
    refs(instance, identifier, 2, (old,), (old,))
    block = ImageBlock(id="photo", revision=1, children=[], provenance=[], type="image", content=None,
        props={"assetId": old, "alt": "sample", "caption": [], "width": 160, "height": 80, "alignment": "center"})
    instance.workspaces[identifier].project.document.regions[2].blocks.append(block); instance.persist(identifier)
    new = await instance.ingest_image(identifier, png("blue"), capture(2, "replace", old))
    assert old != new and (identifier, old) in instance.images and (identifier, new) in instance.images
    refs(instance, identifier, 3, (new,), (old, new))
    instance.workspaces[identifier].project.document.regions[2].blocks[-1].props.asset_id = new
    instance.persist(identifier)
    refs(instance, identifier, 4, (old,), (old, new))
    instance.workspaces[identifier].project.document.regions[2].blocks[-1].props.asset_id = old
    instance.persist(identifier)
    assert (identifier, new) in instance.images
    instance.update_image_session(identifier, ImageSessionRequest(sessionId="reopened", revision=1, live=[old], history=[old],
        previousSessionId="session"))
    assert instance.image_sessions[(identifier, "session")].closed
    assert (identifier, old) in instance.images and (identifier, new) not in instance.images


@pytest.mark.asyncio
async def test_delete_waits_for_explicit_export_and_never_publishes_its_late_artifact(tmp_path):
    instance, identifier = service(tmp_path)
    started, release = asyncio.Event(), asyncio.Event()
    class DelayedRenderer:
        async def render(self, *_args):
            started.set(); await release.wait(); return b"late artifact"
    instance.renderer = DelayedRenderer()
    export = asyncio.create_task(instance.export(identifier)); await started.wait()
    keys = [key for key in instance.tasks if key[0] == identifier]
    assert len(keys) == 1 and instance.tasks[keys[0]] is export
    delete = asyncio.create_task(instance.delete_project(identifier)); await asyncio.sleep(0)
    assert instance.cancels[keys[0]].is_set(); release.set()
    with pytest.raises(ProjectFailure, match="STALE_EXPORT"):
        await export
    assert (await delete).status == "deleted"
    assert not instance.artifacts and not instance.files and not instance.tasks


@pytest.mark.asyncio
async def test_normalized_duplicate_replacement_at_full_byte_budget_keeps_existing_asset(tmp_path, monkeypatch):
    import hashlib
    from packages.resume_core.models.rich_workspace import LocalImageAsset
    from resume_api import rich_assets
    instance, identifier = service(tmp_path)
    blob = png() + b"\0" * (20 * 1024 * 1024 - len(png()))
    checksum = hashlib.sha256(blob).hexdigest()
    old = LocalImageAsset(id="budget-old", sha256=checksum, path=f"images/{checksum}.png", mimeType="image/png",
        size=len(blob), width=16, height=8)
    workspace = instance.workspaces[identifier]; workspace.project.assets = [old]; instance.images[(identifier, old.id)] = blob
    workspace.project.document.regions[2].blocks.append(ImageBlock(id="budget-photo", revision=1, type="image", children=[], provenance=[], content=None,
        props={"assetId": old.id, "alt": "", "caption": [], "width": 160, "height": 80, "alignment": "left"}))
    assert instance.persist(identifier) == "durable"; refs(instance, identifier, 1, (old.id,), (old.id,))
    monkeypatch.setattr(rich_assets, "normalize_image", lambda _raw, _id: (old, blob))
    assert await instance.ingest_image(identifier, png(), capture(replacement=old.id)) == old.id
    assert instance.workspaces[identifier].project.assets == [old] and not instance.image_reservations
