"""Reviewed identities from the official Codex release, never a floating version."""

from pathlib import Path

RELEASE = "0.162.0-alpha.17.2"
ARCHIVE_URL = ("https://github.com/openai/codex/releases/download/rust-v" + RELEASE
               + "/codex-package-aarch64-apple-darwin.tar.gz")
ARCHIVE_BYTES = 132097637
ARCHIVE_SHA256 = "f05b8447bae71d556050fd4066ea4cd066a7b8881ca9c086b88215e7d3d76264"
CLI_SHA256 = "9b47aa34d14c35d87fbe2702fc6c4163d965b30fd88b3defd19e80e780f40d8d"
HOST_SHA256 = "81e6dd884f8e61c0f049582cbc32b8b8bbc3e385d86531f5f1a86c6d166a6973"
MANIFEST_SHA256 = "95ea87bed0ff10cb2cbd9b0541b0e332b4c87f74efd961924029beb33bebb407"


def managed_executable(root: Path) -> Path:
    return root / RELEASE / "bin/codex"
