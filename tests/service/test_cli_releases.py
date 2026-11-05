"""D146: the newest release of each managed CLI, the signature of Claude's manifest, FoldCV's release records, and the
Windows checks that need no codesign."""

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from packages.resume_core import host
from resume_api.providers.claude import distribution as claude_distribution
from resume_api.providers.codex import distribution
from resume_api.cli import openpgp, qualification
from resume_api.providers.claude import profile as claude
from resume_api.providers.claude.profile import ClaudeCliProfile
from resume_api.cli.qualification import QualificationError
from resume_api.cli.releases import RECORD, Record, Release, ReleaseFailure, newer
from resume_api.providers.registry import CLAUDE, discovered

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "claude-release"
MANIFEST = (FIXTURES / "manifest-2.1.318.json").read_bytes()
SIGNATURE = (FIXTURES / "manifest-2.1.318.json.sig").read_bytes()
BASE = claude_distribution.BASE_URL


def pages(**changes):
    found = {BASE + "latest": b"2.1.318\n", BASE + "2.1.318/manifest.json": MANIFEST,
             BASE + "2.1.318/manifest.json.sig": SIGNATURE, **changes}

    def fetch(url, limit):
        assert len(found[url]) <= limit
        return found[url]
    return fetch


def test_the_release_key_is_the_published_one_and_signs_the_2_1_318_manifest():
    key = claude_distribution.release_key()
    assert key.fingerprint == "31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE" and key.modulus.bit_length() == 4096
    openpgp.verify(MANIFEST, SIGNATURE, key)
    openpgp.verify(MANIFEST, openpgp.dearmor(SIGNATURE), key)


@pytest.mark.parametrize("damage", ["document", "signature", "armor", "key", "type"])
def test_any_change_voids_the_signature(damage):
    key, document, signature = claude_distribution.release_key(), MANIFEST, openpgp.dearmor(SIGNATURE)
    if damage == "document":
        document = MANIFEST.replace(b'"2.1.318"', b'"2.1.319"', 1)
    elif damage == "signature":
        signature = signature[:-3] + bytes([signature[-3] ^ 1]) + signature[-2:]
    elif damage == "armor":
        signature = SIGNATURE.replace(b"\n=", b"\n=A", 1)
    elif damage == "key":
        key = openpgp.PublicKey(key.fingerprint, key.modulus - 2, key.exponent)
    else:
        # A signature over text instead of a binary document (type 0x01).
        signature = signature[:4] + b"\x01" + signature[5:]
    with pytest.raises(openpgp.SignatureError):
        openpgp.verify(document, signature, key)


def test_a_key_packet_with_another_fingerprint_is_refused():
    with pytest.raises(openpgp.SignatureError):
        openpgp.key(claude_distribution.KEY_PACKET, "0" * 40)


@pytest.mark.parametrize(("platform", "binary", "size", "checksum"), [
    ("darwin-arm64", "claude", 319598464, "677a2ea7bf576cedd20e191d973914ed8a41796f53a63b1923381ddc4d5b5e7d"),
    ("win32-x64", "claude.exe", 342408352, "b9aa5b08dc2cc46ea77d334dce792d1b8fdbb3a43bb290efdebdc905b1181082"),
])
def test_claude_takes_the_newest_release_from_its_signed_manifest(monkeypatch, platform, binary, size, checksum):
    monkeypatch.setattr(claude_distribution, "PLATFORM", platform)
    monkeypatch.setattr(claude_distribution, "BINARY", binary)
    assert claude_distribution.latest(pages()) == Release("2.1.318", BASE + "2.1.318/" + platform + "/" + binary,
                                                          size, checksum)


@pytest.mark.parametrize(("changes", "code"), [
    ({BASE + "latest": b"<html>not found</html>"}, "invalid_package"),
    ({BASE + "latest": b"\xff"}, "invalid_package"),
    ({BASE + "2.1.318/manifest.json": MANIFEST + b"\n"}, "invalid_package"),
    ({BASE + "2.1.318/manifest.json.sig": b"-----BEGIN PGP SIGNATURE-----\n\n=AAAA\n-----END PGP SIGNATURE-----"},
     "invalid_package"),
])
def test_claude_refuses_what_the_release_key_did_not_sign(changes, code):
    with pytest.raises(ReleaseFailure) as failure:
        claude_distribution.latest(pages(**changes))
    assert failure.value.code == code


def test_claude_refuses_a_platform_the_manifest_does_not_name(monkeypatch):
    monkeypatch.setattr(claude_distribution, "PLATFORM", "plan9-mips")
    with pytest.raises(ReleaseFailure, match="invalid_package"):
        claude_distribution.latest(pages())


def test_a_network_failure_stays_a_download_failure():
    def offline(_url, _limit):
        raise ReleaseFailure("download_failed")
    with pytest.raises(ReleaseFailure, match="download_failed"):
        claude_distribution.latest(offline)


def listing(**changes):
    name = distribution.package_name()
    asset = {"name": name, "state": "uploaded", "size": 202589789,
             "digest": "sha256:d559bb88e74d471265857b93b7f19bc250dae527673b9191b33534478093f6bc",
             "browser_download_url": distribution.DOWNLOAD_URL + "rust-v0.166.0/" + name}
    other = {**asset, "name": name.replace(".tar.gz", ".tar.zst"), "browser_download_url": "https://example.invalid/x"}
    value = {"tag_name": "rust-v0.166.0", "draft": False, "prerelease": False, "assets": [other, asset]}
    for key, change in changes.items():
        if key.startswith("asset_"):
            asset[key.removeprefix("asset_")] = change
        else:
            value[key] = change
    body = json.dumps(value).encode()
    return lambda url, _limit: body if url == distribution.LATEST_URL else pytest.fail(url)


def test_codex_takes_the_package_of_githubs_latest_release():
    found = distribution.latest(listing())
    assert found == Release("0.166.0", distribution.DOWNLOAD_URL + "rust-v0.166.0/" + distribution.package_name(),
                            202589789, "d559bb88e74d471265857b93b7f19bc250dae527673b9191b33534478093f6bc")


@pytest.mark.parametrize("changes", [
    {"prerelease": True}, {"draft": True}, {"tag_name": "v0.166.0"}, {"tag_name": "rust-v0.166.0 && echo"},
    {"asset_digest": None}, {"asset_digest": "md5:abc"}, {"asset_state": "starter"}, {"asset_size": 0},
    {"asset_browser_download_url": "https://example.invalid/codex-package.tar.gz"}, {"assets": []},
])
def test_codex_refuses_a_listing_that_does_not_check_out(changes):
    with pytest.raises(ReleaseFailure, match="invalid_package"):
        distribution.latest(listing(**changes))


def test_versions_compare_as_releases():
    assert newer("2.1.318", "2.1.308") and newer("0.166.0", "0.162.0-alpha.17.2")
    assert not newer("2.1.308", "2.1.308") and not newer("2.1.300", "2.1.308")
    assert not newer(None, "2.1.308") and not newer("2.1.318", None)


def write_release(root: Path, version: str, payload: bytes, *, record: bool = True) -> Path:
    entry = claude_distribution.entry()
    binary = root / version / entry
    binary.parent.mkdir(parents=True, mode=0o700)
    binary.write_bytes(payload)
    binary.chmod(0o700)
    if record:
        (root / version / RECORD).write_bytes(Record(version, {entry: hashlib.sha256(payload).hexdigest()}).encode())
    return binary


def test_the_newest_release_with_a_record_is_the_current_one(tmp_path, monkeypatch):
    runtime = claude_distribution.runtime(tmp_path / "runtime")
    assert runtime.current() is None
    assert runtime.executable() == tmp_path / "runtime" / claude_distribution.RELEASE / claude_distribution.entry()
    # The pinned release counts through its hashes in code, without a record.
    monkeypatch.setattr(claude_distribution, "BINARY_SHA256", hashlib.sha256(b"pinned").hexdigest())
    pinned = write_release(tmp_path / "runtime", claude_distribution.RELEASE, b"pinned", record=False)
    runtime = claude_distribution.runtime(tmp_path / "runtime")
    assert runtime.current() == (claude_distribution.RELEASE, pinned.parents[1])
    assert runtime.intact(pinned.parents[1])
    newest = write_release(tmp_path / "runtime", "2.1.318", b"newest")
    write_release(tmp_path / "runtime", "2.1.320", b"no record", record=False)
    (tmp_path / "runtime" / ".staging-x").mkdir()
    assert runtime.current() == ("2.1.318", newest.parents[1]) and runtime.executable() == newest
    assert runtime.package_of(newest) == newest.parents[1] and runtime.package_of(pinned) == pinned.parents[1]
    assert runtime.package_of(tmp_path / "runtime" / "2.1.320" / claude_distribution.entry()) is None
    assert runtime.package_of(tmp_path / "elsewhere" / "2.1.318" / claude_distribution.entry()) is None
    newest.write_bytes(b"changed")
    assert not runtime.intact(newest.parents[1])


@pytest.mark.parametrize("record", [
    {"version": "2.1.317", "files": {"bin/claude": "0" * 64}}, {"version": "2.1.318", "files": {}},
    {"version": "2.1.318", "files": {"../claude": "0" * 64}}, {"version": "2.1.318", "files": {"bin/claude": "x"}},
    {"version": "2.1.318", "files": {"bin/claude": "0" * 64}, "extra": True},
])
def test_a_record_that_does_not_fit_its_directory_counts_for_nothing(tmp_path, record):
    package = tmp_path / "runtime" / "2.1.318"
    package.mkdir(parents=True)
    (package / RECORD).write_text(json.dumps(record))
    assert claude_distribution.runtime(tmp_path / "runtime").current() is None


@pytest.fixture
def windows(monkeypatch):
    """Windows rules on this machine: no codesign may run, whatever the code asks."""
    monkeypatch.setattr(host, "WINDOWS", True)

    def refused(*_args, **_kwargs):
        raise AssertionError("codesign ran")
    monkeypatch.setattr(subprocess, "run", refused)
    qualification._SIGNATURES.clear()


def test_windows_refuses_every_signature_without_codesign(windows, tmp_path):
    binary = tmp_path / "claude.exe"
    binary.write_bytes(b"native")
    with pytest.raises(QualificationError, match="CLI_UNSUPPORTED"):
        qualification.require_publisher(binary, claude.TEAM_ID, claude.IDENTIFIER)
    assert discovered(CLAUDE, binary) is False


def test_windows_runs_only_the_managed_copy_its_record_names(windows, tmp_path):
    managed = write_release(tmp_path / ("cli-runtime-" + claude.KIND), "2.1.318", b"managed claude")
    profile = ClaudeCliProfile(tmp_path / ("cli-profile-" + claude.KIND), managed)
    assert profile.managed
    profile.check_binary()
    managed.write_bytes(b"changed claude")
    with pytest.raises(QualificationError, match="CLI_UNSUPPORTED"):
        profile.check_binary()
    native = tmp_path / "native" / "claude.exe"
    native.parent.mkdir()
    native.write_bytes(b"native")
    other = ClaudeCliProfile(tmp_path / ("cli-profile-" + claude.KIND), native)
    assert not other.managed
    with pytest.raises(QualificationError, match="CLI_UNSUPPORTED"):
        other.check_binary()
