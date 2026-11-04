"""Where the managed Codex comes from: the newest non-preview release of openai/codex on GitHub (D146).

An install takes the `codex-package-<target>.tar.gz` asset of the release GitHub marks latest, checked against the
SHA-256 GitHub records for the asset; on macOS the CLI and its code-mode host must carry OpenAI's signature as well.
0.162.0-alpha.17.2 was the one pinned release before updates; a package installed then still counts through its
hashes below.
"""

from pathlib import Path
import re

from packages.resume_core.host import WINDOWS
from .releases import Fetch, Record, Release, ReleaseFailure, Runtime, checked_size, checked_version, strict_json

LATEST_URL = "https://api.github.com/repos/openai/codex/releases/latest"
DOWNLOAD_URL = "https://github.com/openai/codex/releases/download/"
PACKAGE_MANIFEST = "codex-package.json"
if WINDOWS:
    TARGET, CLI, HOST = "x86_64-pc-windows-msvc", "bin/codex.exe", "bin/codex-code-mode-host.exe"
    CLI_SHA256 = "f5521b058ca08e249afd3b25b4681e81100181d92e73aa6b94bb8e75c2aa487b"
    HOST_SHA256 = "ec91f7a04dcb1a36f0e2ed87885777bf78900c2ea3295e82621c5721fd5d9f41"
    MANIFEST_SHA256 = "f2fd3028e915fc8f9e7b4ca20ef7a32898270f4c2585d98b3a8d5ba6a93bae93"
else:
    TARGET, CLI, HOST = "aarch64-apple-darwin", "bin/codex", "bin/codex-code-mode-host"
    CLI_SHA256 = "9b47aa34d14c35d87fbe2702fc6c4163d965b30fd88b3defd19e80e780f40d8d"
    HOST_SHA256 = "81e6dd884f8e61c0f049582cbc32b8b8bbc3e385d86531f5f1a86c6d166a6973"
    MANIFEST_SHA256 = "95ea87bed0ff10cb2cbd9b0541b0e332b4c87f74efd961924029beb33bebb407"
RELEASE = "0.162.0-alpha.17.2"
_TAG = re.compile(r"rust-v(.+)")
_DIGEST = re.compile(r"sha256:([0-9a-f]{64})")


def package_name() -> str:
    return "codex-package-" + TARGET + ".tar.gz"


def latest(fetch: Fetch) -> Release:
    value = strict_json(fetch(LATEST_URL, 8_388_608))
    if not isinstance(value, dict) or value.get("draft") is not False or value.get("prerelease") is not False:
        raise ReleaseFailure("invalid_package")
    tag = value.get("tag_name")
    match = _TAG.fullmatch(tag) if isinstance(tag, str) else None
    version = checked_version(match.group(1) if match else None)
    assets = value.get("assets")
    found = ([item for item in assets if isinstance(item, dict) and item.get("name") == package_name()]
             if isinstance(assets, list) else [])
    asset = found[0] if len(found) == 1 else {}
    digest = _DIGEST.fullmatch(asset["digest"]) if isinstance(asset.get("digest"), str) else None
    url = DOWNLOAD_URL + str(tag) + "/" + package_name()
    if digest is None or asset.get("browser_download_url") != url or asset.get("state") != "uploaded":
        raise ReleaseFailure("invalid_package")
    return Release(version, url, checked_size(asset.get("size")), digest.group(1))


def runtime(root: Path) -> Runtime:
    # Read on each use, so a test can patch the module values.
    return Runtime(Path(root), CLI, (CLI, HOST, PACKAGE_MANIFEST),
                   Record(RELEASE, {CLI: CLI_SHA256, HOST: HOST_SHA256, PACKAGE_MANIFEST: MANIFEST_SHA256}))


def managed_executable(root: Path) -> Path:
    return runtime(root).executable()
