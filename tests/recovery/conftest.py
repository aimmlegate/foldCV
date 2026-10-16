"""NB tests permit registered pipe children, never a production runtime fallback."""

import hashlib
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture(autouse=True)
def offline_background_boundaries(request, monkeypatch, tmp_path):
    if not request.node.path.name.startswith("test_background_"):
        yield
        return
    root = Path(__file__).resolve().parents[2]
    counter = root / "docs/gui/handoffs/BACKGROUND-WORK/native-attempts.json"
    before = hashlib.sha256(counter.read_bytes()).hexdigest()
    monkeypatch.syspath_prepend(str(root / "services/api/src"))
    from resume_api.agent.runtime import CodexAgentRuntime
    from resume_api.connection import ConnectionAdapter
    from resume_api.providers.codex_cli import CodexCliProvider
    from spikes.background.harness import SYNTHETIC_SPAWN

    def forbidden(*args, **kwargs):
        raise AssertionError("production runtime/connection factory is forbidden in offline NB tests")

    for cls in (CodexAgentRuntime, ConnectionAdapter, CodexCliProvider):
        monkeypatch.setattr(cls, "__init__", forbidden)
    original = subprocess.Popen
    child_hash = hashlib.sha256((root / "spikes/background/fake_child.py").read_bytes()).hexdigest()

    def guarded(arguments, *args, **kwargs):
        allowed = SYNTHETIC_SPAWN.get()
        if (allowed is None or not isinstance(arguments, list) or tuple(arguments) != allowed
                or arguments[:4] != [sys.executable, "-I", "-S", "-u"] or len(arguments) != 5 or kwargs.get("shell")):
            raise AssertionError("unregistered child spawn is forbidden in offline NB tests")
        script = Path(arguments[-1])
        if (script.is_symlink() or not script.resolve().is_relative_to(tmp_path.resolve())
                or hashlib.sha256(script.read_bytes()).hexdigest() != child_hash
                or kwargs.get("env") != {"HOME": str(script.parent), "LANG": "C.UTF-8"}
                or kwargs.get("cwd") != script.parent):
            raise AssertionError("synthetic child identity, environment or ownership is invalid")
        return original(arguments, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guarded)
    yield
    assert hashlib.sha256(counter.read_bytes()).hexdigest() == before
