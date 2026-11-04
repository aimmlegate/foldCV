"""Reviewed identities from the official Codex release, never a floating version."""

from pathlib import Path

from packages.resume_core.host import WINDOWS

RELEASE = "0.162.0-alpha.17.2"
if WINDOWS:
    # The archive's SHA-256 is the digest GitHub records for the release asset.
    TARGET, CLI, HOST = "x86_64-pc-windows-msvc", "bin/codex.exe", "bin/codex-code-mode-host.exe"
    ARCHIVE_BYTES = 159772874
    ARCHIVE_SHA256 = "65630fbc9c8f2b23113e4c6e0bceaa6aa63ae6c43a11872598dc9cf56410e66d"
    CLI_SHA256 = "f5521b058ca08e249afd3b25b4681e81100181d92e73aa6b94bb8e75c2aa487b"
    HOST_SHA256 = "ec91f7a04dcb1a36f0e2ed87885777bf78900c2ea3295e82621c5721fd5d9f41"
    MANIFEST_SHA256 = "f2fd3028e915fc8f9e7b4ca20ef7a32898270f4c2585d98b3a8d5ba6a93bae93"
else:
    TARGET, CLI, HOST = "aarch64-apple-darwin", "bin/codex", "bin/codex-code-mode-host"
    ARCHIVE_BYTES = 132097637
    ARCHIVE_SHA256 = "f05b8447bae71d556050fd4066ea4cd066a7b8881ca9c086b88215e7d3d76264"
    CLI_SHA256 = "9b47aa34d14c35d87fbe2702fc6c4163d965b30fd88b3defd19e80e780f40d8d"
    HOST_SHA256 = "81e6dd884f8e61c0f049582cbc32b8b8bbc3e385d86531f5f1a86c6d166a6973"
    MANIFEST_SHA256 = "95ea87bed0ff10cb2cbd9b0541b0e332b4c87f74efd961924029beb33bebb407"
ARCHIVE_URL = ("https://github.com/openai/codex/releases/download/rust-v" + RELEASE
               + "/codex-package-" + TARGET + ".tar.gz")


def managed_executable(root: Path) -> Path:
    return root / RELEASE / CLI
