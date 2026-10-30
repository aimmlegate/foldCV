"""One reviewed Claude Code release for the managed install (MP02b), never a floating version.

Pinned from the release's manifest.json after its manifest.json.sig verified with Anthropic's release key
31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE; the macOS binary is the notarized one with Team ID Q6L2SF6YDW.
The Windows binary's checksum comes from the same manifest.
"""

from pathlib import Path

from packages.resume_core.host import WINDOWS

RELEASE = "2.1.308"
if WINDOWS:
    PLATFORM, BINARY = "win32-x64", "claude.exe"
    BINARY_BYTES = 297376928
    BINARY_SHA256 = "c9796ba22a9221586b36371b36f5b66198d66eb4badf6a4cf4a5f7b07becea53"
else:
    PLATFORM, BINARY = "darwin-arm64", "claude"
    BINARY_BYTES = 274675680
    BINARY_SHA256 = "ca923c86ac84b30574a82331a05b6e066c27477a926ceaffe46a845a33e4dd37"
BINARY_URL = "https://downloads.claude.ai/claude-code-releases/" + RELEASE + "/" + PLATFORM + "/" + BINARY
MANIFEST_SHA256 = "9a01bbf1996be52f13508ef9e47ef3fcf544ac39037ca91b4c87f2b4efc425fb"


def managed_executable(root: Path) -> Path:
    return root / RELEASE / "bin" / BINARY
