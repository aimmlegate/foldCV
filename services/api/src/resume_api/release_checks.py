"""What a new managed release must do before it replaces the installed one (D146): the checks a connection runs
before it reads the account, on the new files. A release that fails them stays out; the installed one keeps working."""

from __future__ import annotations

from pathlib import Path
import time

from .providers.codex.host_profile import check_host
from .providers.codex.profile import ExperimentalCliProfile, ExperimentalProfileError
from .cli.installation import InstallationFailure
from .providers.claude.profile import ClaudeCliProfile
from .providers.codex.connection import ConnectionAdapter
from .providers.base import ConnectionFailure
from .lifecycle import SpikeError
from .providers.claude.content import ClaudeCliProvider
from .providers.content import ContentFailure

# A first start of a new binary may wait for the antivirus scan on Windows.
SECONDS = 180
# What the CLI itself refused; anything else (a stop, a timeout, the profile folder) says nothing about the release.
INCOMPATIBLE = frozenset({"UNSUPPORTED_VERSION", "CLI_UNSUPPORTED", "CLI_FAILED"})


def _refuse(code: str) -> None:
    if code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
        raise SpikeError(code)
    raise InstallationFailure("cancelled" if code == "CANCELLED" else "incompatible_release" if code in INCOMPATIBLE
                              else "install_failed")


def codex(profile_root: Path):
    def qualify(files, executable: Path, version: str, cancel) -> None:
        profile = ExperimentalCliProfile(profile_root, executable)
        adapter = ConnectionAdapter(executable, experimental_profile=profile)
        deadline = time.monotonic() + SECONDS
        try:
            if adapter.version(files, cancel, deadline) != "codex-cli " + version:
                raise InstallationFailure("incompatible_release")
            adapter.check_profile(files, cancel, deadline)
            check_host(profile.package_root, managed=True)
        except ConnectionFailure as error:
            _refuse(error.code)
        except ExperimentalProfileError as error:
            _refuse("CLI_UNSUPPORTED" if str(error) == "AGENT_CODE_MODE_HOST_UNSUPPORTED" else str(error))
    return qualify


def claude(profile_root: Path):
    def qualify(files, executable: Path, version: str, cancel) -> None:
        provider = ClaudeCliProvider(executable, profile=ClaudeCliProfile(profile_root, executable))
        try:
            found, _status = provider.capabilities(files, cancel, time.monotonic() + SECONDS)
        except ContentFailure as error:
            _refuse(error.code)
        if str(found) != version:
            raise InstallationFailure("incompatible_release")
    return qualify
