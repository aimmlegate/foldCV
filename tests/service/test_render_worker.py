"""The render workers under the service: the V7 export (POST /v2/projects/{id}/export through
`projects.exports.production_render` and `rendering.TemplateDocxRenderer`) and the PDF `rendering.DocumentRenderer`."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import signal
from contextlib import contextmanager

import httpx
import pytest

from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rendering.template import RenderFailure
from resume_api import lifecycle, rendering
from resume_api.cli import runner as cli_runner
from resume_api.cli.runner import group_members
from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.rendering import DocumentRenderer, TemplateDocxRenderer
from tests.service.app_fixtures import (DOCX_WORKER, ORIGIN, PROJECT, HealthyConnection, add_project, export, make_app,
                                        open_project, operations, signed_in, status)
from tests.templates.storage_fixtures import joined, literal, workspace

DOCX = b"PK\x03\x04synthetic-export"
# Writes the DOCX, leaves a second process in its group and reports the group id; `hold` keeps the worker running.
GROUP_WORKER = '''import os, signal, subprocess, sys, zipfile
from pathlib import Path
subprocess.Popen([sys.executable, "-c", "import signal; signal.pause()"])
with zipfile.ZipFile("resume.docx", "w") as archive:
    archive.writestr("word/document.xml", "<w:document/>")
Path({ready!r}).write_text(str(os.getpgid(0)))
if {hold!r}:
    signal.pause()
'''


async def _bytes():
    return DOCX


def service(tmp_path, **options):
    app = make_app(tmp_path, connection_adapter=HealthyConnection(), **options)
    add_project(app)
    return app


def use_worker(monkeypatch, tmp_path, source, name="worker.py"):
    script = tmp_path / name
    script.write_text(source, encoding="utf-8")
    monkeypatch.setattr(rendering, "WORKER", script)
    return script


class PassedDeadline:
    """The rendering module's asyncio: the 30 s worker deadline passes as soon as the worker reports it runs."""

    def __init__(self, ready: Path):
        self.ready = ready

    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def wait_for(self, awaitable, timeout):
        assert timeout == 30
        for _ in range(500):
            if self.ready.exists():
                break
            await asyncio.sleep(0.01)
        awaitable.cancel()
        raise asyncio.TimeoutError


@contextmanager
def kill_group_after(ready: Path):
    try:
        yield
    finally:
        if ready.exists():
            try:
                os.killpg(int(ready.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


async def assert_restart_blocked(tmp_path):
    restarted = make_app(tmp_path, connection_adapter=HealthyConnection())
    async with signed_in(restarted) as client:
        assert await status(client) == "cleanup_blocked"
        refused = await export(client, await open_project(client))
        assert refused.status_code == 503 and refused.json()["error"]["code"] == "PROCESS_CLEANUP_FAILED"


@pytest.mark.asyncio
async def test_export_runs_the_worker_in_an_owned_directory_and_keeps_nothing(tmp_path, monkeypatch):
    use_worker(monkeypatch, tmp_path, "from pathlib import Path\nimport sys\n"
               "if not (Path('.lock').is_file() and Path('.owner').is_file()): sys.exit(3)\n" + DOCX_WORKER)
    app = service(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN,
                                 headers={"Origin": ORIGIN}) as anonymous:
        denied = await anonymous.post(f"/v2/projects/{PROJECT}/export", json={})
        assert denied.status_code == 401
    async with signed_in(app) as client:
        token, snapshot = await open_project(client)
        stale = await export(client, (token, {**snapshot, "documentRevision": snapshot["documentRevision"] + 1}))
        assert stale.status_code == 409
        assert operations(tmp_path) == []
        reply = await export(client, (token, snapshot))
        assert reply.status_code == 200, reply.text[:300]
        assert reply.content.startswith(b"PK") and reply.headers["cache-control"] == "no-store"
        assert reply.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert operations(tmp_path) == []


@pytest.mark.parametrize("private", ["Built a tool. Call 555-123-4567.", "Portfolio: alice.dev",
                                     "Website: alice.com", "LinkedIn: linkedin.com"])
@pytest.mark.asyncio
async def test_contact_text_reaches_the_worker_unchanged(tmp_path, monkeypatch, private):
    captured = []

    async def accepted(self, request, files):
        captured.append(request.model_dump_json(by_alias=True))
        return DOCX

    monkeypatch.setattr(TemplateDocxRenderer, "render_template", accepted)
    app = make_app(tmp_path, connection_adapter=HealthyConnection())
    add_project(app, joined(lambda ref: [literal(private, ref)]))
    async with signed_in(app) as client:
        reply = await export(client, await open_project(client))
        assert reply.status_code == 200 and reply.content == DOCX
    assert len(captured) == 1 and json.dumps(private)[1:-1] in captured[0]
    assert operations(tmp_path) == []


@pytest.mark.asyncio
async def test_a_worker_exception_is_sanitized_and_releases_the_directory(tmp_path, monkeypatch, capsys):
    original = TemplateDocxRenderer.render_template

    async def broken(self, request, files):
        (files.path / "synthetic.txt").write_text("private-marker")
        raise ValueError("private-marker")

    monkeypatch.setattr(TemplateDocxRenderer, "render_template", broken)
    use_worker(monkeypatch, tmp_path, DOCX_WORKER)
    app = service(tmp_path)
    async with signed_in(app) as client:
        editor = await open_project(client)
        failed = await export(client, editor)
        assert failed.status_code == 500 and failed.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "private-marker" not in failed.text
        assert operations(tmp_path) == []
        monkeypatch.setattr(TemplateDocxRenderer, "render_template", original)
        assert (await export(client, editor)).status_code == 200
        assert await status(client) == "connected"
    assert "private-marker" not in "".join(capsys.readouterr())


@pytest.mark.asyncio
async def test_a_passed_deadline_stops_the_worker_group_and_releases_the_directory(tmp_path, monkeypatch):
    ready = tmp_path / "worker-group"
    use_worker(monkeypatch, tmp_path, GROUP_WORKER.format(ready=str(ready), hold=True))
    monkeypatch.setattr(rendering, "asyncio", PassedDeadline(ready))
    app = service(tmp_path)
    with kill_group_after(ready):
        async with signed_in(app) as client:
            editor = await open_project(client)
            failed = await export(client, editor)
            assert failed.status_code >= 500 and "Shared title" not in failed.text
            assert group_members(int(ready.read_text())) == []
            assert operations(tmp_path) == []
            assert await status(client) == "connected"
            monkeypatch.setattr(rendering, "asyncio", asyncio)
            use_worker(monkeypatch, tmp_path, DOCX_WORKER, "plain-worker.py")
            assert (await export(client, editor)).status_code == 200


@pytest.mark.asyncio
async def test_an_export_holds_one_worker_slot(tmp_path, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def held(self, request, files):
        calls.append(files.path)
        started.set()
        await release.wait()
        return DOCX

    monkeypatch.setattr(TemplateDocxRenderer, "render_template", held)
    monkeypatch.setattr("resume_api.app.MAX_CONCURRENT", 1)
    app = service(tmp_path)
    papers, _ = workspace()
    data = papers.model_dump(by_alias=True)
    data["projectId"] = data["project"]["projectId"] = "second-project"
    add_project(app, WorkspaceV7.model_validate(data))
    async with signed_in(app) as client:
        first = asyncio.create_task(export(client, await open_project(client)))
        await asyncio.wait_for(started.wait(), 5)
        busy = await client.post("/v1/host/status", json={})
        assert busy.status_code == 429 and busy.json()["error"]["code"] == "BUSY"
        second = asyncio.create_task(export(client, await open_project(client, "second-project"), "second-project"))
        tasks = app.app.state.projects.tasks
        for _ in range(500):
            if tasks.list("second-project"):
                break
            await asyncio.sleep(0.01)
        assert [item["state"] for item in tasks.list("second-project")] == ["running"]
        assert len(calls) == 1
        release.set()
        assert (await first).status_code == 200 and (await second).status_code == 200
        assert len(calls) == 2
        assert await status(client) == "connected"
    assert operations(tmp_path) == []


@pytest.mark.asyncio
async def test_a_temporary_directory_failure_is_reported_and_does_not_latch(tmp_path, monkeypatch):
    use_worker(monkeypatch, tmp_path, DOCX_WORKER)
    original = lifecycle.OperationFiles.open

    @contextmanager
    def failed_open(self):
        raise SpikeError("TEMP_FAILED")
        yield self

    app = service(tmp_path)
    async with signed_in(app) as client:
        editor = await open_project(client)
        monkeypatch.setattr(lifecycle.OperationFiles, "open", failed_open)
        failed = await export(client, editor)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "TEMP_FAILED"
        monkeypatch.setattr(lifecycle.OperationFiles, "open", original)
        assert await status(client) == "connected"
        assert (await export(client, editor)).status_code == 200


@pytest.mark.asyncio
async def test_a_cleanup_failure_retains_the_owned_directory_and_blocks_a_restart(tmp_path, monkeypatch):
    async def failed_cleanup(self, request, files):
        raise SpikeError("PROCESS_CLEANUP_FAILED")

    monkeypatch.setattr(TemplateDocxRenderer, "render_template", failed_cleanup)
    app = service(tmp_path)
    async with signed_in(app) as client:
        failed = await export(client, await open_project(client))
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "PROCESS_CLEANUP_FAILED"
        assert "Shared title" not in failed.text
    owned = operations(tmp_path)
    assert len(owned) == 1 and (owned[0] / ".owner").is_file() and (owned[0] / ".cleanup-blocked").is_file()
    await assert_restart_blocked(tmp_path)
    assert owned[0].is_dir()


@pytest.mark.parametrize("source", ["renderer", "unsafe_root", "removal"])
@pytest.mark.asyncio
async def test_a_cleanup_failure_blocks_new_work_in_the_running_service(tmp_path, monkeypatch, source):
    calls = []

    async def failing(self, request, files):
        calls.append(files.path)
        if source == "renderer":
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        return DOCX

    @contextmanager
    def unsafe_open(self):
        raise SpikeError("UNSAFE_TEMP_ROOT")
        yield self

    original_remove = cli_runner.shutil.rmtree

    def failed_remove(path, *args, **kwargs):
        if Path(path).name.startswith("op-"):
            raise OSError("synthetic cleanup failure")
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(TemplateDocxRenderer, "render_template", failing)
    app = service(tmp_path)
    async with signed_in(app) as client:
        editor = await open_project(client)
        if source == "unsafe_root":
            monkeypatch.setattr(lifecycle.OperationFiles, "open", unsafe_open)
        if source == "removal":
            monkeypatch.setattr(cli_runner.shutil, "rmtree", failed_remove)
        failed = await export(client, editor)
        assert failed.status_code == 503
        assert failed.json()["error"]["code"] == {"renderer": "PROCESS_CLEANUP_FAILED", "unsafe_root": "UNSAFE_TEMP_ROOT",
                                                  "removal": "CLEANUP_FAILED"}[source]
        monkeypatch.undo()
        monkeypatch.setattr(TemplateDocxRenderer, "render_template", failing)
        before = len(calls)
        assert await status(client) == "cleanup_blocked"
        refused = await export(client, editor)
        assert refused.status_code == 503 and refused.json()["error"]["code"] == "PROCESS_CLEANUP_FAILED"
        assert len(calls) == before


@pytest.mark.parametrize("ending", ["exit", "deadline"])
@pytest.mark.asyncio
async def test_a_real_worker_group_that_cannot_be_stopped_is_retained_and_blocks_a_restart(tmp_path, monkeypatch, ending):
    ready = tmp_path / "worker-group"
    use_worker(monkeypatch, tmp_path, GROUP_WORKER.format(ready=str(ready), hold=ending == "deadline"))
    if ending == "deadline":
        monkeypatch.setattr(rendering, "asyncio", PassedDeadline(ready))

    def failed_stop(_process):
        raise SpikeError("PROCESS_CLEANUP_FAILED")

    app = service(tmp_path)
    with kill_group_after(ready):
        monkeypatch.setattr(lifecycle, "stop_group", failed_stop)
        async with signed_in(app) as client:
            failed = await export(client, await open_project(client))
            assert failed.status_code == 503 and failed.json()["error"]["code"] == "PROCESS_CLEANUP_FAILED"
            assert group_members(int(ready.read_text()))
        owned = operations(tmp_path)
        assert len(owned) == 1 and (owned[0] / ".owner").is_file() and (owned[0] / ".cleanup-blocked").is_file()
        monkeypatch.undo()
        await assert_restart_blocked(tmp_path)
        assert owned[0].is_dir()


@pytest.mark.asyncio
async def test_a_partial_removal_keeps_the_intent_and_blocks_a_restart(tmp_path, monkeypatch):
    unrelated = tmp_path / "operations" / ("op-" + "a" * 32)
    unrelated.mkdir(parents=True)
    (unrelated / ".owner").write_text(json.dumps({"owner": "another-app", "id": "a" * 32}))
    (unrelated / ".lock").touch()
    original_remove = cli_runner.shutil.rmtree

    def partial_remove(path, *args, **kwargs):
        if Path(path).name.startswith("op-"):
            (Path(path) / ".owner").unlink()
            (Path(path) / ".lock").unlink()
            raise OSError("synthetic partial removal")
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(TemplateDocxRenderer, "render_template", lambda *_args: _bytes())
    app = service(tmp_path)
    async with signed_in(app) as client:
        editor = await open_project(client)
        monkeypatch.setattr(cli_runner.shutil, "rmtree", partial_remove)
        failed = await export(client, editor)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "CLEANUP_FAILED"
    monkeypatch.setattr(cli_runner.shutil, "rmtree", original_remove)
    root = tmp_path / "operations"
    intents = list(root.glob(".cleanup-intent-op-*.json"))
    assert len(intents) == 1
    record = json.loads(intents[0].read_text())
    assert record == {"owner": lifecycle.OWNER,
                      "id": intents[0].name.removeprefix(".cleanup-intent-op-").removesuffix(".json")}
    damaged = root / ("op-" + record["id"])
    assert damaged.is_dir() and not (damaged / ".owner").exists()
    await assert_restart_blocked(tmp_path)
    assert damaged.is_dir() and unrelated.is_dir() and intents[0].is_file()


@pytest.mark.asyncio
async def test_an_intent_write_failure_never_starts_deletion(tmp_path, monkeypatch):
    def failed_intent(root, identifier, owner):
        raise OSError("synthetic intent failure")

    original_remove = cli_runner.shutil.rmtree
    attempts = []

    def tracked_remove(path, *args, **kwargs):
        if Path(path).name.startswith("op-"):
            attempts.append(path)
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(TemplateDocxRenderer, "render_template", lambda *_args: _bytes())
    app = service(tmp_path)
    async with signed_in(app) as client:
        editor = await open_project(client)
        monkeypatch.setattr(cli_runner, "_write_cleanup_intent", failed_intent)
        monkeypatch.setattr(cli_runner.shutil, "rmtree", tracked_remove)
        failed = await export(client, editor)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "CLEANUP_FAILED"
    assert attempts == []
    owned = [path for path in operations(tmp_path) if path.name.startswith("op-")]
    assert len(owned) == 1 and (owned[0] / ".owner").is_file() and (owned[0] / ".cleanup-blocked").is_file()
    monkeypatch.undo()
    await assert_restart_blocked(tmp_path)


@pytest.mark.asyncio
async def test_an_intent_unlink_failure_blocks_a_restart_without_a_directory(tmp_path, monkeypatch):
    original_unlink = Path.unlink

    def failed_unlink(path, *args, **kwargs):
        if path.name.startswith(".cleanup-intent-op-"):
            raise OSError("synthetic marker unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(TemplateDocxRenderer, "render_template", lambda *_args: _bytes())
    app = service(tmp_path)
    async with signed_in(app) as client:
        editor = await open_project(client)
        monkeypatch.setattr(Path, "unlink", failed_unlink)
        failed = await export(client, editor)
        monkeypatch.setattr(Path, "unlink", original_unlink)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "CLEANUP_FAILED"
    root = tmp_path / "operations"
    assert list(root.glob("op-*")) == [] and len(list(root.glob(".cleanup-intent-op-*.json"))) == 1
    monkeypatch.undo()
    await assert_restart_blocked(tmp_path)


@pytest.mark.parametrize(("worker", "code"), [
    ("import json, sys\nopen('render-status.json', 'w').write(json.dumps({'code': 'FONT_UNAVAILABLE'}))\nsys.exit(4)\n",
     "FONT_UNAVAILABLE"),
    ("import sys\nsys.stderr.write('private-crash-marker')\nsys.exit(7)\n", "RICH_RENDER_FAILED"),
])
@pytest.mark.asyncio
async def test_a_worker_failure_code_reaches_the_reply(tmp_path, monkeypatch, worker, code):
    use_worker(monkeypatch, tmp_path, worker)
    app = service(tmp_path)
    async with signed_in(app) as client:
        failed = await export(client, await open_project(client))
        assert "private-crash-marker" not in failed.text
        assert operations(tmp_path) == []
        assert failed.status_code == 422 and failed.json()["error"]["code"] == code


@pytest.mark.parametrize(("worker", "code"), [
    ("import json, sys\nopen('render-status.json', 'w').write(json.dumps({'code': 'FONT_UNAVAILABLE'}))\nsys.exit(4)\n",
     "FONT_UNAVAILABLE"),
    ("import json, sys\nopen('render-status.json', 'w').write(json.dumps({'code': 'private-marker'}))\nsys.exit(4)\n",
     "RENDER_FAILED"),
    ("import zipfile\nwith zipfile.ZipFile('render-output.zip', 'w') as out:\n    out.writestr('private.txt', 'x')\n",
     "RENDER_FAILED"),
    ("import sys\nsys.exit(0)\n", "RENDER_OUTPUT_LIMIT"),
])
@pytest.mark.asyncio
async def test_the_pdf_worker_reports_only_public_codes_and_cleans(tmp_path, monkeypatch, worker, code):
    script = use_worker(monkeypatch, tmp_path, worker)
    files = OperationFiles(tmp_path / "operations")

    class Request:
        # The worker is replaced, so the request body only has to serialize.
        def model_dump_json(self, **_options):
            return "{}"

    with pytest.raises(RenderFailure) as caught:
        with files.open():
            await DocumentRenderer().render(Request(), files)
    assert caught.value.code == code and "private" not in str(caught.value)
    assert operations(tmp_path) == [] and script.is_file()
