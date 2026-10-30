"""Metadata-only Claude connection with the same surface as the Codex ConnectionAdapter (MP02)."""

from __future__ import annotations

import threading
import time
from typing import Callable

from resume_api.cli.process_runner import ProcessExit
from resume_api.cli.profiles.claude import ClaudeCliProfile, ClaudeProfileError
from resume_api.connection import ConnectionFailure, Metadata, Quota
from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.providers.claude_cli import ClaudeCliProvider, FixtureTransport
from resume_api.providers.content import ContentFailure


# Provider codes in the connection vocabulary the Settings state machine already knows.
STATES = {"AUTH_REQUIRED": "LOGIN_REQUIRED", "AUTH_MODE_MISMATCH": "API_KEY_MODE",
          "CLI_UNSUPPORTED": "UNSUPPORTED_VERSION", "CLI_PROFILE_UNSAFE": "UNSUPPORTED_VERSION", "CLI_MISSING": "CLI_MISSING",
          "METADATA_FAILED": "METADATA_FAILED", "CANCELLED": "CANCELLED", "DEADLINE_EXCEEDED": "DEADLINE_EXCEEDED",
          "PROCESS_CLEANUP_FAILED": "PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED": "CLEANUP_FAILED",
          "TEMP_FAILED": "TEMP_FAILED"}
# No CLI-mediated usage read exists; credential files are never read for it (decision 15).
NOT_PROVIDED = Quota("not_provided")
LOGIN_SECONDS = 300


class ClaudeConnectionAdapter:
    def __init__(self, profile: ClaudeCliProfile | None, *, fixture_transport: FixtureTransport | None = None):
        self.profile = profile
        self.fixture_transport = fixture_transport

    @property
    def executable(self):
        return self.profile.executable if self.profile is not None else None

    def _provider(self) -> ClaudeCliProvider:
        if self.profile is None and self.fixture_transport is None:
            raise ConnectionFailure("CLI_MISSING")
        try:
            return ClaudeCliProvider(self.fixture_transport.executable if self.fixture_transport else None,
                                     profile=self.profile, fixture_transport=self.fixture_transport)
        except ContentFailure as error:
            raise ConnectionFailure(STATES.get(error.code, "CLI_FAILED")) from None

    def inspect(self, files: OperationFiles, cancel: threading.Event, *, full: bool = True) -> Metadata:
        provider = self._provider()
        if not provider.executable.is_file():
            raise ConnectionFailure("CLI_MISSING")
        try:
            probe = provider.probe(files, cancel, deadline=time.monotonic() + 15)
        except ContentFailure as error:
            raise ConnectionFailure(STATES.get(error.code, "CLI_FAILED"), error.version) from None
        if not full:
            return Metadata(probe.version, (), None, NOT_PROVIDED, version_status=probe.status)
        return Metadata(probe.version, tuple(probe.reasoning), probe.plan, NOT_PROVIDED, dict(probe.reasoning), probe.status)

    def login(self, files: OperationFiles, cancel: threading.Event,
              code: Callable[[], str | None] | None = None) -> None:
        """Without a terminal the CLI waits for the code shown after the browser sign-in;
        `code` returns it once the user pastes it, else None."""
        try:
            self.inspect(files, cancel, full=False)
            return
        except ConnectionFailure as error:
            if error.code != "LOGIN_REQUIRED":
                raise
        provider = self._provider()
        sent = False

        def pasted() -> bytes | None:
            nonlocal sent
            value = code() if code is not None and not sent else None
            if not value:
                return None
            sent = True
            return (value.strip() + "\n").encode()

        # The CLI owns the browser flow and the keychain entry of the FoldCV config directory.
        try:
            provider.process.run(files, ("auth", "login", "--claudeai"), deadline=time.monotonic() + LOGIN_SECONDS,
                                 cancel=cancel, max_output=65_536, interactive=True, poll_input=pasted)
        except ProcessExit:
            raise ConnectionFailure("CLI_FAILED") from None
        except SpikeError as error:
            raise ConnectionFailure(STATES.get(error.code, "CLI_FAILED")) from None
        except ClaudeProfileError as error:
            raise ConnectionFailure(error.code) from None
