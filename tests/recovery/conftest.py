"""NB tests permit registered pipe children, never a production runtime fallback."""

import hashlib
import os
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
    from spikes.background.appserver_driver import SharedAppServer
    # The SDK evaluates Popen's generic type during import, before the spawn guard.
    import mcp

    def forbidden(*args, **kwargs):
        raise AssertionError("production runtime/connection factory is forbidden in offline NB tests")

    for cls in (CodexAgentRuntime, ConnectionAdapter, CodexCliProvider):
        monkeypatch.setattr(cls, "__init__", forbidden)
    monkeypatch.setattr(SharedAppServer, "native", forbidden)
    original = subprocess.Popen
    registered = []
    child_hashes = {hashlib.sha256((root / "spikes/background" / name).read_bytes()).hexdigest()
        for name in ("fake_child.py", "fake_publication_child.py", "fake_appserver.py")}

    def guarded(arguments, *args, **kwargs):
        # Existing group cleanup reads only PID/group/status, never command lines.
        if (registered and arguments == ["/bin/ps", "-axo", "pid=,pgid=,stat="]
                and not args and set(kwargs) <= {"stdout", "stderr", "env"}
                and kwargs.get("stdout") == subprocess.PIPE and kwargs.get("stderr") == subprocess.PIPE
                and kwargs.get("env") == {"PATH": os.defpath, "LC_ALL": "C"}):
            return original(arguments, **kwargs)
        allowed = SYNTHETIC_SPAWN.get()
        if (allowed is None or not isinstance(arguments, list) or tuple(arguments) != allowed
                or arguments[:4] != [sys.executable, "-I", "-S", "-u"] or len(arguments) != 5 or kwargs.get("shell")):
            raise AssertionError("unregistered child spawn is forbidden in offline NB tests")
        script = Path(arguments[-1])
        if (script.is_symlink() or not script.resolve().is_relative_to(tmp_path.resolve())
                or hashlib.sha256(script.read_bytes()).hexdigest() not in child_hashes
                or kwargs.get("env") != {"HOME": str(script.parent), "LANG": "C.UTF-8"}
                or kwargs.get("cwd") != script.parent):
            raise AssertionError("synthetic child identity, environment or ownership is invalid")
        process = original(arguments, *args, **kwargs)
        registered.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", guarded)
    yield
    assert hashlib.sha256(counter.read_bytes()).hexdigest() == before
