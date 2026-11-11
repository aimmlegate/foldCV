"""What a CLI prints while it signs in: the address of its sign-in page, which Settings offers when the browser the CLI
opens does not appear (seen on Windows), and a local log of each run that the user can send; sign-outs and clearings
are logged there too."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import re
from urllib.parse import urlsplit

from packages.resume_core import host
from resume_api.app_log import failure, masked


# The pages each CLI sends the user to; no other address from the output becomes a link.
HOSTS = {"claude_cli": frozenset({"claude.com", "claude.ai", "platform.claude.com"}),
         "codex_cli": frozenset({"auth.openai.com"})}
# Only an address the CLI finished printing: whitespace follows it.
ADDRESS = re.compile(rb"https://[!-~]+(?=\s)")
MAX_URL = 4096
LOG_NAME = "sign-in.log"
LOG_BYTES = 262_144
# A subcommand as both CLIs list it in their help. A CLI without `logout` would take the word as a prompt (Codex).
LOGOUT = re.compile(rb"^[ \t]+logout\b", re.MULTILINE)


def lists_logout(help_text: bytes) -> bool:
    return LOGOUT.search(help_text) is not None


def sign_in_url(kind: str, raw: str) -> str | None:
    if len(raw) > MAX_URL or any(character in raw for character in "\"'<>\\`"):
        return None
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        return None
    if (parts.scheme != "https" or parts.hostname not in HOSTS.get(kind, ()) or port is not None
            or parts.username is not None or parts.password is not None):
        return None
    return raw


class SignInOutput:
    """One sign-in run's output, fed by the runner's reading thread; `url` is set once the page address appears.
    `action` names the run in the log; `outcome`, when set, is logged in place of OK, and `ended` is what was logged."""

    def __init__(self, kind: str, log: Path | None = None, action: str = "sign-in"):
        self.kind, self.log, self.action = kind, log, action
        self.streams = {"stdout": bytearray(), "stderr": bytearray()}
        self.url: str | None = None
        self.outcome: str | None = None
        self.ended: str | None = None
        self.notes: list[str] = []

    def feed(self, stream: str, chunk: bytes) -> None:
        buffer = self.streams[stream]
        buffer.extend(chunk)
        if self.url is not None:
            return
        for match in ADDRESS.finditer(buffer):
            url = sign_in_url(self.kind, match.group().decode("ascii"))
            if url is not None:
                self.url = url
                return

    @contextmanager
    def recording(self):
        """Logs the run with its outcome: OK, or the code of the failure that ended it."""
        try:
            yield
        except BaseException as error:
            self.write(failure(error))
            raise
        self.write(self.outcome or "OK")

    def write(self, outcome: str) -> None:
        self.ended = outcome
        if self.log is None:
            return
        lines = [f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {self.kind} {self.action}: {outcome}",
                 f"system: {platform.platform()}"]
        if self.action == "sign-in":
            lines.append(f"page address found: {'yes' if self.url else 'no'}")
        lines += self.notes
        for name, buffer in self.streams.items():
            if buffer:
                text = masked(buffer.decode("utf-8", "replace")).rstrip()
                lines += [f"--- {name}", text]
        entry = ("\n".join(lines) + "\n\n").encode()
        # A log that cannot be written changes nothing about the sign-in.
        try:
            self.log.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.log.is_file() and self.log.stat().st_size + len(entry) > LOG_BYTES:
                host.replace(self.log, self.log.with_name(self.log.name + ".1"))
            descriptor = os.open(self.log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | host.O_NOFOLLOW | host.O_BINARY,
                                 0o600)
            try:
                os.write(descriptor, entry)
            finally:
                os.close(descriptor)
        except OSError:
            pass
