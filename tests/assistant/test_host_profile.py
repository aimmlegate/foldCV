"""The pinned code-mode host belongs only to the sandboxed assistant profile."""

import hashlib
import os
import subprocess
import sys

import pytest

from resume_api.agent import host_profile as agent
from resume_api.cli.experimental_profile import BINARY, ExperimentalCliProfile, ExperimentalProfileError


@pytest.fixture
def pinned_host(tmp_path, monkeypatch):
    host = tmp_path / "host"
    manifest = tmp_path / "codex-package.json"
    host.write_bytes(b"synthetic-host")
    host.chmod(0o700)
    manifest.write_bytes(b"synthetic-manifest")
    monkeypatch.setattr(agent, "CODE_MODE_HOST", host)
    monkeypatch.setattr(agent, "HOST_SHA256", hashlib.sha256(host.read_bytes()).hexdigest())
    monkeypatch.setattr(agent, "PACKAGE_MANIFEST", manifest)
    monkeypatch.setattr(agent, "MANIFEST_SHA256", hashlib.sha256(manifest.read_bytes()).hexdigest())
    return host, manifest


@pytest.mark.parametrize("damage", ["host", "manifest", "missing", "symlink", "mode"])
def test_changed_or_unsafe_host_fails_before_launch(tmp_path, pinned_host, monkeypatch, damage):
    host, manifest = pinned_host
    agent.check_host()
    if damage == "host":
        host.write_bytes(b"changed")
    elif damage == "manifest":
        manifest.write_bytes(b"changed")
    elif damage == "missing":
        host.unlink()
    elif damage == "symlink":
        target = tmp_path / "target"
        host.rename(target)
        host.symlink_to(target)
    else:
        host.chmod(0o600)
    launches = []
    monkeypatch.setattr(ExperimentalCliProfile, "launch", lambda *args: launches.append(args))
    with pytest.raises(ExperimentalProfileError, match="AGENT_CODE_MODE_HOST_UNSUPPORTED"):
        agent.AgentProofProfile(tmp_path).launch(BINARY, agent.APP_SERVER_PREFIX, tmp_path)
    assert launches == []


@pytest.mark.parametrize("args", [
    ("exec", "--model", "example"), ("login",), ("app-server", "daemon"),
    ("app-server", "--strict-config", "--listen", "ws://127.0.0.1:1234"),
    (*agent.APP_SERVER_PREFIX, "--code-mode-host", "wss://example.test"),
    (*agent.APP_SERVER_PREFIX, "--listen", "ws://127.0.0.1:1234"),
])
def test_agent_launcher_rejects_other_modes_before_profile_access(tmp_path, monkeypatch, args):
    checks = []
    monkeypatch.setattr(agent, "check_host", lambda: checks.append(True))
    with pytest.raises(ExperimentalProfileError, match="AGENT_RUNTIME_ONLY"):
        agent.AgentProofProfile(tmp_path).launch(BINARY, args, tmp_path)
    assert checks == []


def test_only_assistant_config_enables_local_host(tmp_path):
    def settings(profile):
        values = profile.config(tmp_path)[1::2]
        return dict(value.split("=", 1) for value in values)

    regular = settings(ExperimentalCliProfile(tmp_path))
    assistant = settings(agent.AgentProofProfile(tmp_path))
    for feature in ("code_mode", "code_mode_host"):
        assert regular[f"features.{feature}"] == "false"
        assert assistant[f"features.{feature}"] == "true"
    for feature in ("shell_tool", "unified_exec", "multi_agent", "plugins", "hooks", "apps"):
        assert regular[f"features.{feature}"] == assistant[f"features.{feature}"] == "false"


@pytest.mark.skipif(sys.platform != "darwin" or not agent.CODE_MODE_HOST.is_file(),
                    reason="Requires the pinned macOS companion")
def test_sandbox_allows_host_only_for_agent_and_still_denies_shell(tmp_path):
    agent.check_host()
    operation = tmp_path.resolve()
    regular = ExperimentalCliProfile(operation / "profile")
    assistant = agent.AgentProofProfile(operation / "profile")
    environment = {"PATH": os.defpath, "HOME": str(operation), "TMPDIR": str(operation)}

    def run(policy, executable, *args):
        return subprocess.run(["/usr/bin/sandbox-exec", "-p", policy, str(executable), *args],
                              env=environment, input="", capture_output=True, text=True, timeout=10)

    policy = assistant._policy(operation, agent.APP_SERVER_PREFIX)
    allowed = run(policy, agent.CODE_MODE_HOST, "--help")
    assert allowed.returncode == 0, allowed.stderr
    assert "Usage: codex-code-mode-host" in allowed.stdout
    for profile, args in ((regular, agent.APP_SERVER_PREFIX), (assistant, ("exec",)),
                          (assistant, ("login", "status"))):
        denied = run(profile._policy(operation, args), agent.CODE_MODE_HOST, "--help")
        assert denied.returncode != 0
        assert "Usage: codex-code-mode-host" not in denied.stdout
    denied = run(policy, "/bin/sh", "-c", "printf FORBIDDEN_AGENT_SHELL")
    assert denied.returncode != 0
    assert "FORBIDDEN_AGENT_SHELL" not in denied.stdout
