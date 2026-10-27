"""A service app in a temporary store, a signed-in async client, a connection without a CLI and an exportable project."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from resume_api.app import create_app
from resume_api.cli.profile import VERSION
from resume_api.connection import Metadata, Quota
from tests.projects.support import source_blobs
from tests.templates.storage_fixtures import workspace

ORIGIN = "http://127.0.0.1:39281"
SECRET = "synthetic-service-secret-0123456789abcdef"
PROJECT = "template-project"
DOCX_WORKER = '''import json, zipfile
from pathlib import Path
json.loads(Path("template-docx-input.json").read_text(encoding="utf-8"))
with zipfile.ZipFile("resume.docx", "w") as archive:
    archive.writestr("word/document.xml", "<w:document/>")
'''


class HealthyConnection:
    """Metadata without a CLI process: a status reply is `connected` unless the service latched `cleanup_blocked`."""

    def inspect(self, _files, _cancel, *, full=True):
        return Metadata(VERSION, ("gpt-6-luna",), "plus", Quota("available", 25, 1800000000))


def make_app(tmp_path: Path, **options):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("<html>synthetic shell</html>", encoding="utf-8")
    (dist / "asset.js").write_text("safe asset", encoding="utf-8")
    options.setdefault("data_root", tmp_path / "data")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist, **options)


def add_project(app, value=None):
    papers, sources = workspace()
    app.app.state.projects.repository.create(value or papers, blobs=source_blobs(sources))


@asynccontextmanager
async def signed_in(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN,
                                 headers={"Origin": ORIGIN}) as client:
        assert (await client.post("/v1/session/exchange", json={"secret": SECRET})).status_code == 200
        yield client


async def open_project(client, project=PROJECT):
    opened = (await client.post(f"/v2/projects/{project}/open", json={})).json()
    return opened["editorToken"], opened["response"]["snapshot"]


async def export(client, editor, project=PROJECT):
    token, snapshot = editor
    return await client.post(f"/v2/projects/{project}/export",
                             json={"schemaVersion": 1, "editorToken": token, "snapshot": snapshot})


async def status(client):
    return (await client.post("/v1/host/status", json={})).json()["state"]


def operations(tmp_path: Path) -> list[Path]:
    root = tmp_path / "operations"
    return sorted(root.iterdir()) if root.exists() else []
