"""One reviewed Claude Code release for the managed install (MP02b), never a floating version.

Pinned from the release's manifest.json after its manifest.json.sig verified with Anthropic's release key
31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE; the binary is the notarized one with Team ID Q6L2SF6YDW.
"""

from pathlib import Path

RELEASE = "2.1.308"
PLATFORM = "darwin-arm64"
BINARY_URL = "https://downloads.claude.ai/claude-code-releases/" + RELEASE + "/" + PLATFORM + "/claude"
BINARY_BYTES = 274675680
BINARY_SHA256 = "ca923c86ac84b30574a82331a05b6e066c27477a926ceaffe46a845a33e4dd37"
MANIFEST_SHA256 = "9a01bbf1996be52f13508ef9e47ef3fcf544ac39037ca91b4c87f2b4efc425fb"


def managed_executable(root: Path) -> Path:
    return root / RELEASE / "bin/claude"
