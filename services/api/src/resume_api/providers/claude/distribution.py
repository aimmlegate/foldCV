"""Where the managed Claude Code comes from: Anthropic's release bucket and its signed manifest (MP02b, D146).

An install takes the newest release, as Anthropic's own installer does (`latest`). The manifest must carry a good
signature of the release key 31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE, and the binary must have the size and
checksum the manifest names; on macOS it is also the notarized binary with Team ID Q6L2SF6YDW.
2.1.308 was the one pinned release before updates; a copy installed then still counts through its hashes below.
"""

from pathlib import Path

from packages.resume_core.host import WINDOWS
from ...cli import openpgp
from ...cli.releases import (Fetch, Record, Release, ReleaseFailure, Runtime, SHA256, checked_size, checked_version,
                             strict_json)

BASE_URL = "https://downloads.claude.ai/claude-code-releases/"
# The primary key packet of https://downloads.claude.ai/keys/claude-code.asc,
# "Anthropic Claude Code Release Signing <security@anthropic.com>".
KEY_FINGERPRINT = "31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE"
KEY_PACKET = (
    "BGnK73ABEACnbytJXkjweYrwIr0aLEFRlH+C0nF44KxFc7gQmJ6PjSPMGZADdxZcaixU7zZl8WxEpVO0wLmIH8cf2zGOdyuZg1Yaugk1vHb2b8WB"
    "hAGCQJdPgB8WXquedepEYtk56uP/gCoTjJDUZluEGBHnlnuujSJ4orxEdhSykEoAUfJZGEILPpMdbphFt/Sn+Eb/TxM5jpKPdwnv8AShNF/1mZU1"
    "fWTQq9tRKJUakZj04gdaDFElQXakCtTij+GT6yoYCARSHwGO+PC/Pr6q4tc+D7LRjxSBvUWDoFSmlqb/PJ1hj9D/7I2Oe4XXniAPWMR56KvxHlzO"
    "zrNQdJujbJdSkCwh1ZijkSd3y8ayW5WYUTGdRab99NUwagzlabe/VVF6kzJ0Scn5q3PihB2Y9Bwo0CKnkYk7a7KT77EWv0Kkq+VHmOtqX3a2hhX+"
    "b6a6ve9rzJ1qZYGj+obv/C3Sx1LzUjAfqVy7RJDf2uAoP5t2g8u/TkSpUxhMVEjZBkSxYZhMyzQM6t8IgkUfnSrIPTHixbDWARZ4beMOBjxyPZK1"
    "nP7OOrNR3TkKJtwLMQAabURCDnL0PjS0iwBTU4jtumBD1XSULyWuoTvMljrpQr1nV1oDyOt0OLqaKA2McWtd9PdXhC8y2EIg7TmrTlJLfHYbdmki"
    "CYj4J49Q8HWkN/6WE+RTUwARAQAB"
)
if WINDOWS:
    PLATFORM, BINARY = "win32-x64", "claude.exe"
    BINARY_SHA256 = "c9796ba22a9221586b36371b36f5b66198d66eb4badf6a4cf4a5f7b07becea53"
else:
    PLATFORM, BINARY = "darwin-arm64", "claude"
    BINARY_SHA256 = "ca923c86ac84b30574a82331a05b6e066c27477a926ceaffe46a845a33e4dd37"
RELEASE = "2.1.308"


def entry() -> str:
    return "bin/" + BINARY


def release_key() -> openpgp.PublicKey:
    return openpgp.key(KEY_PACKET, KEY_FINGERPRINT)


def latest(fetch: Fetch) -> Release:
    """The `latest` channel's release for this platform, from its signed manifest."""
    try:
        version = checked_version(fetch(BASE_URL + "latest", 64).decode("ascii", "strict").strip())
    except UnicodeError:
        raise ReleaseFailure("invalid_package") from None
    manifest = fetch(BASE_URL + version + "/manifest.json", 1_048_576)
    signature = fetch(BASE_URL + version + "/manifest.json.sig", 65_536)
    try:
        openpgp.verify(manifest, signature, release_key())
    except openpgp.SignatureError:
        raise ReleaseFailure("invalid_package") from None
    value = strict_json(manifest)
    platforms = value.get("platforms") if isinstance(value, dict) else None
    item = platforms.get(PLATFORM) if isinstance(platforms, dict) else None
    if (not isinstance(item, dict) or value.get("version") != version or item.get("binary") != BINARY
            or not isinstance(item.get("checksum"), str) or not SHA256.fullmatch(item["checksum"])):
        raise ReleaseFailure("invalid_package")
    return Release(version, BASE_URL + version + "/" + PLATFORM + "/" + BINARY, checked_size(item.get("size")),
                   item["checksum"])


def runtime(root: Path) -> Runtime:
    # Read on each use, so a test can patch the module values.
    return Runtime(Path(root), entry(), (entry(),), Record(RELEASE, {entry(): BINARY_SHA256}))


def managed_executable(root: Path) -> Path:
    return runtime(root).executable()
