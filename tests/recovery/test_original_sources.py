"""Original viewing preserves bytes, ownership and session boundaries."""

import hashlib
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.models.contracts import Source
from packages.resume_core.rules import RulesStore
from resume_api.app import create_app
from resume_api.gui_projects import ProjectFailure
from resume_api.original_sources import original_response
from resume_api.rich_projects import RichProjectService
from tests.recovery.test_rich_persistence import without_sources


def add_source(service, name="Original.md", data=b"# Original\r\n\r\n  Two spaces\tend\n"):
    workspace = without_sources()
    source = Source(id="source-original", revision=1, originalName=name, mimeType="application/octet-stream",
        byteSha256=hashlib.sha256(data).hexdigest(), byteRef="sources/source-original/original", parser="utf8",
        parserVersion="2", units=[], overlays=[], warnings=[])
    workspace.project.sources = [source]
    service.loaded = True
    service.workspaces[workspace.project_id] = workspace
    service.originals[(workspace.project_id, source.id)] = data
    assert service.persist(workspace.project_id) == "durable"
    return workspace.project_id, source, data


@pytest.mark.parametrize(("name", "mime"), [
    ("Original.PDF", "application/pdf"),
    ("Original.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("Original.txt", "text/plain"), ("Original.MD", "text/markdown"), ("Original.markdown", "text/markdown"),
])
def test_exact_original_survives_reopen_and_portable_transfer(tmp_path, name, mime):
    root = tmp_path / "store"
    service = RichProjectService(tmp_path / "operations", RulesStore(root), lambda: None)
    identifier, source, data = add_source(service, name)
    reopened = RichProjectService(tmp_path / "second", RulesStore(root), lambda: None)
    before = reopened.read(identifier).model_dump_json()
    response = original_response(reopened, identifier, source.id)
    assert bytes(response.body) == data
    assert response.headers["content-type"].split(";")[0] == mime
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-foldcv-sha256"] == source.byte_sha256
    assert reopened.read(identifier).model_dump_json() == before
    copied = reopened.import_portable(reopened.portable(identifier))
    assert bytes(original_response(reopened, copied, source.id).body) == data


def test_missing_unowned_and_corrupted_originals_fail_without_using_extracted_text(tmp_path):
    service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"), lambda: None)
    identifier, source, data = add_source(service)
    service.originals[(identifier, "unowned")] = data
    with pytest.raises(ProjectFailure, match="SOURCE_NOT_FOUND"):
        original_response(service, identifier, "unowned")
    service.originals.pop((identifier, source.id))
    with pytest.raises(ProjectFailure, match="SOURCE_BYTES_MISSING"):
        original_response(service, identifier, source.id)
    service.originals[(identifier, source.id)] = b"changed"
    with pytest.raises(ProjectFailure, match="SOURCE_BYTES_MISMATCH"):
        original_response(service, identifier, source.id)


@pytest.mark.asyncio
async def test_original_endpoint_auth_download_filename_and_deletion(tmp_path):
    origin, secret = "http://127.0.0.1:39329", "synthetic-original-session-0123456789"
    dist = tmp_path / "dist"; dist.mkdir(); (dist / "index.html").write_text("fixture")
    app = create_app(origin=origin, secret=secret, temp_root=tmp_path / "operations", dist=dist, data_root=tmp_path / "store")
    service = app.app.state.rich_projects
    identifier, source, data = add_source(service, "../Резюме\r\n.docx")
    path = f"/v1/rich/projects/{identifier}/sources/{source.id}/original"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin) as client:
        assert (await client.get(path)).status_code == 401
        await client.post("/v1/session/exchange", headers={"Origin": origin}, json={"secret": secret})
        assert (await client.get(path, headers={"Origin": "https://foreign.example"})).status_code == 403
        response = await client.get(path)
        assert response.content == data and response.status_code == 200
        download = await client.get(path + "/download")
        assert download.content == data
        assert download.headers["content-disposition"] == "attachment; filename*=UTF-8''%D0%A0%D0%B5%D0%B7%D1%8E%D0%BC%D0%B5.docx"
        assert (await client.get(path.replace(source.id, "absent"))).status_code == 404
        await service.delete_project(identifier)
        assert (await client.get(path)).status_code == 410
