"""MP01: Codex qualifies by publisher, version table and features, not by exact version or binary hash."""

import hashlib
import threading

import pytest

from resume_api.cli import distribution, profile as codex, qualification
from resume_api.cli.experimental_profile import ExperimentalCliProfile, ExperimentalProfileError
from resume_api.cli.qualification import Compatibility, QualificationError, Signature
from resume_api.connection import ConnectionAdapter, ConnectionFailure
from resume_api.lifecycle import OperationFiles
from tests.service.test_connection import cli  # noqa: F401  (fixture)


@pytest.mark.parametrize(("banner", "status"), [
    ("codex-cli 0.162.0-alpha.2", "supported"), ("codex-cli 0.162.0-alpha.17.2", "supported"),
    ("codex-cli 0.163.0-alpha.11.1", "supported"), ("codex-cli 0.163.0", "graceful"), ("codex-cli 1.0.0", "graceful"),
])
def test_versions_inside_the_table_qualify(banner, status):
    assert codex.qualify(banner) == status


@pytest.mark.parametrize("banner", ["codex-cli 0.162.0-alpha.1", "codex-cli 0.161.9", "2.1.308 (Claude Code)",
                                    "codex-cli", "codex-cli " + "9" * 80])
def test_versions_below_the_floor_or_foreign_are_unsupported(banner):
    with pytest.raises(QualificationError, match="CLI_UNSUPPORTED"):
        codex.qualify(banner)


def test_a_listed_broken_version_is_unsupported(monkeypatch):
    monkeypatch.setattr(codex, "COMPATIBILITY", Compatibility("0.162.0-alpha.2", "0.163.0-alpha.11.1", ("0.163.1",)))
    with pytest.raises(QualificationError):
        codex.qualify("codex-cli 0.163.1")
    assert codex.qualify("codex-cli 0.163.2") == "graceful"


@pytest.mark.parametrize(("listing", "safe"), [
    ("shell_tool   stable   false\nunified_exec   stable   true\n", True),
    ("shell_tool   stable   true\n", False),
    ("code_mode   under development   true\n", False),
    ("", False),
    ("garbage\n", False),
])
def test_features_list_must_report_required_features_off(listing, safe):
    if safe:
        codex.check_features(listing)
    else:
        with pytest.raises(QualificationError, match="CLI_PROFILE_UNSAFE"):
            codex.check_features(listing)


@pytest.fixture
def user_binary(tmp_path, monkeypatch):
    binary = tmp_path / "bin" / "codex"
    binary.parent.mkdir()
    binary.write_bytes(b"user-installed codex")
    binary.chmod(0o755)
    signatures = {}
    monkeypatch.setattr(qualification, "signature", lambda path: signatures.get(path.name) or (_ for _ in ()).throw(
        QualificationError("CLI_UNSUPPORTED")))
    return binary, signatures


def test_user_installed_binary_qualifies_by_publisher_signature(tmp_path, user_binary):
    binary, signatures = user_binary
    profile = ExperimentalCliProfile(tmp_path / "cli-experiment", binary)
    assert not profile.managed
    with pytest.raises(ExperimentalProfileError, match="CLI_UNSUPPORTED"):
        profile.check_binary()
    signatures["codex"] = Signature("ABCDE12345", "codex")
    with pytest.raises(ExperimentalProfileError, match="CLI_UNSUPPORTED"):
        profile.check_binary()
    signatures["codex"] = Signature("2DC432GLL2", "codex")
    profile.check_binary()
    binary.write_bytes(b"self-updated codex")
    profile.check_binary()


def test_managed_runtime_keeps_its_hash_pin(tmp_path, monkeypatch):
    executable = distribution.managed_executable(tmp_path / "cli-runtime")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"managed codex")
    executable.chmod(0o755)
    monkeypatch.setattr(qualification, "signature", lambda _path: pytest.fail("signature read for the managed runtime"))
    profile = ExperimentalCliProfile(tmp_path / "cli-experiment", executable)
    assert profile.managed
    monkeypatch.setattr(distribution, "CLI_SHA256", hashlib.sha256(b"managed codex").hexdigest())
    profile.check_binary()
    executable.write_bytes(b"changed codex")
    with pytest.raises(ExperimentalProfileError, match="CLI_UNSUPPORTED"):
        profile.check_binary()


@pytest.mark.parametrize(("version", "status"), [
    ("codex-cli " + distribution.RELEASE, "supported"), ("codex-cli 0.163.0-alpha.11.1", "supported"),
    ("codex-cli 0.170.0", "graceful"), ("codex-cli 0.161.0", None),
])
def test_connection_accepts_any_qualifying_version(cli, tmp_path, version, status):  # noqa: F811
    path, configure = cli
    configure(version=version)
    with OperationFiles(tmp_path / "operations").open() as files:
        if status is None:
            with pytest.raises(ConnectionFailure) as failure:
                ConnectionAdapter(path).inspect(files, threading.Event())
            assert failure.value.code == "UNSUPPORTED_VERSION" and failure.value.version == version
        else:
            result = ConnectionAdapter(path).inspect(files, threading.Event())
            assert result.version == version and result.version_status == status
