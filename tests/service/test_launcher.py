"""`resume_api.launcher.launch`: bounded startup and shutdown, and the template import offered by default."""

from __future__ import annotations

import asyncio

import pytest

from resume_api import launcher


def isolate(tmp_path, monkeypatch):
    dist = tmp_path / "apps/web/dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("synthetic shell", encoding="utf-8")
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "trusted_temp_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(launcher, "require_supported_host", lambda: None)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["startup", "shutdown"])
async def test_the_launcher_bounds_startup_and_shutdown(tmp_path, monkeypatch, phase):
    isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(launcher, "STARTUP_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(launcher, "SHUTDOWN_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(launcher, "create_app", lambda **_kwargs: object())
    monkeypatch.setattr(launcher, "tune_garbage_collector", lambda: None)

    class SlowServer:
        def __init__(self, _config):
            self.started = phase == "shutdown"
            self.should_exit = False

        async def serve(self, *, sockets):
            assert sockets
            if phase == "shutdown":
                self.should_exit = True
            await asyncio.Event().wait()

    monkeypatch.setattr(launcher.uvicorn, "Server", SlowServer)
    loop = asyncio.get_running_loop()
    start = loop.time()
    with pytest.raises(RuntimeError, match=f"Service {phase} timed out"):
        await launcher.launch(open_browser=False)
    assert loop.time() - start < 0.5


@pytest.mark.asyncio
async def test_the_launcher_offers_template_import_by_default(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after configuration")

    monkeypatch.setattr(launcher, "create_app", create)
    with pytest.raises(RuntimeError, match="stop after configuration"):
        await launcher.launch(open_browser=False)
    # Without a call cap /v1/rich/template-import reports the import unavailable.
    assert captured["template_import_call_cap"] == launcher.TEMPLATE_IMPORT_CALL_CAP > 0
    assert captured["experimental_profile"] is None and captured["temp_root"] == tmp_path / "operations"
