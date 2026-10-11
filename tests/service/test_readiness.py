"""Local developer preflight states use only synthetic CLI output."""

from pathlib import Path
import platform
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from tools import local_readiness as readiness
from packages.resume_core.rendering import template
from resume_api.connection import ConnectionAdapter, ConnectionFailure


def test_local_readiness_checks_current_pinned_runtime():
    readiness.check_local()


def test_local_readiness_reports_host_and_dependency_errors(monkeypatch):
    monkeypatch.setattr(platform, "mac_ver", lambda: ("27.0", (), ""))
    with pytest.raises(readiness.ReadinessError, match="macOS 26.6.2 arm64"):
        readiness.check_local()
    monkeypatch.setattr(platform, "mac_ver", lambda: ("26.6.2", (), ""))
    original = readiness.importlib.metadata.version
    monkeypatch.setattr(readiness.importlib.metadata, "version",
                        lambda package: "0.0" if package == "PyMuPDF" else original(package))
    with pytest.raises(readiness.ReadinessError, match="Python dependency PyMuPDF must be 1.28.2"):
        readiness.check_local()


@pytest.mark.parametrize("code,remedy", [
    ("CONVERTER_UNAVAILABLE", "install-local-renderer.sh"),
    ("FONT_UNAVAILABLE", "app-local fonts"),
    ("ASSET_MISMATCH", "checked-in template assets"),
])
def test_local_readiness_reports_renderer_failure(monkeypatch, code, remedy):
    def fail():
        raise template.RenderFailure(code)
    monkeypatch.setattr(template, "require_template", fail)
    with pytest.raises(readiness.ReadinessError, match=remedy):
        readiness.check_local()


def test_unsupported_cli_version_never_checks_login(tmp_path):
    calls = tmp_path / "calls"
    cli = tmp_path / "codex"
    cli.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$1\" >> '{calls}'\nprintf 'codex-cli 0.162.0-alpha.17.2\\n'\n",
                   encoding="utf-8")
    cli.chmod(0o700)
    assert "outside the pinned profile" in readiness.check_cli(cli)
    assert calls.read_text(encoding="utf-8") == "--version\n"


def test_entrypoint_reports_missing_dependency_without_traceback():
    result = subprocess.run([sys.executable, "-S", "tools/run-local.py", "--check"],
                            cwd=readiness.ROOT, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "Python dependency PyMuPDF must be 1.28.2" in result.stderr
    assert "Traceback" not in result.stderr
    assert "http://" not in result.stdout


def test_entrypoint_handles_cli_path_with_spaces_without_login(tmp_path):
    directory = tmp_path / "CLI with spaces"
    directory.mkdir()
    calls = directory / "calls"
    cli = directory / "codex"
    cli.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$1\" >> '{calls}'\nprintf 'codex-cli 0.162.0-alpha.17.2\\n'\n",
                   encoding="utf-8")
    cli.chmod(0o700)
    result = subprocess.run([sys.executable, "tools/run-local.py", "--check", "--codex-executable", str(cli)],
                            cwd=readiness.ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "outside the pinned profile" in result.stderr
    assert "http://" not in result.stdout
    assert calls.read_text(encoding="utf-8") == "--version\n"


def test_metadata_cleanup_failure_blocks_preflight(monkeypatch, tmp_path):
    cli = tmp_path / "codex"
    cli.touch()
    monkeypatch.setattr(readiness, "bounded_version", lambda _: "codex-cli 0.162.0-alpha.2")

    def fail(_self, _files, _cancel):
        raise ConnectionFailure("PROCESS_CLEANUP_FAILED")

    monkeypatch.setattr(ConnectionAdapter, "inspect", fail)
    with pytest.raises(readiness.ReadinessError, match="process cleanup failed"):
        readiness.check_cli(cli)
