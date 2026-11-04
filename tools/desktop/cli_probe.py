"""Install the newest Codex and Claude releases into an empty data root, with the capability checks the desktop service
runs before a release goes in place, then check each connection as Settings does; prints a JSON report. No sign-in, no
model call, so a working CLI must stop at sign-in. Exits 1 otherwise.

Usage (check_helper.py --cli runs it): `<helper>/python/python.exe -X utf8 cli_probe.py <empty data root>`.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time

from resume_api import release_checks
from resume_api.cli.experimental_profile import ExperimentalCliProfile
from resume_api.cli.installation import ClaudeInstallation, CliInstallation
from resume_api.cli.process_runner import ProcessExit, ProcessRunner
from resume_api.cli.profiles import claude
from resume_api.connection import ConnectionAdapter, ConnectionFailure
from resume_api.connection_claude import ClaudeConnectionAdapter
from resume_api.lifecycle import OperationFiles, SpikeError

# Signed out, a CLI that passes every check stops here (D146: a codesign-only check had refused every Windows binary).
SIGNED_OUT = "LOGIN_REQUIRED"


def run(profile, executable: Path, operations: Path, arguments) -> dict:
    with OperationFiles(operations).open() as files:
        arguments = arguments(files.path) if callable(arguments) else arguments
        try:
            stdout, stderr = ProcessRunner(executable, launch=profile.launch,
                                           workdir=getattr(profile, "workdir", None)).run(
                files, tuple(arguments), cancel=threading.Event(), deadline=time.monotonic() + 120)
            code = 0
        except ProcessExit as error:
            stdout, stderr, code = error.stdout, error.stderr, "nonzero"
        except SpikeError as error:
            return {"error": error.code}
    return {"exit": code, "stdout": stdout.decode("utf-8", "replace")[-600:],
            "stderr": stderr.decode("utf-8", "replace")[-600:]}


def connection(adapter, operations: Path) -> str:
    with OperationFiles(operations).open() as files:
        try:
            adapter.inspect(files, threading.Event())
            return "connected"
        except ConnectionFailure as error:
            return error.code


def main(root: Path) -> int:
    operations = root / "operations"
    codex_root, claude_root = root / "cli-profile", root / ("cli-profile-" + claude.KIND)
    codex_profile = lambda executable: ExperimentalCliProfile(codex_root, executable)  # noqa: E731
    claude_profile = lambda executable: claude.ClaudeCliProfile(claude_root, executable)  # noqa: E731
    cases = (
        ("codex", CliInstallation(root / "cli-runtime", qualify=release_checks.codex(codex_root)), codex_profile,
         lambda profile: ConnectionAdapter(profile.executable, experimental_profile=profile),
         (("--version",), ("exec", "--help"), ("login", "status"),
          lambda operation: ("features", "list", *codex_profile(None).config(operation)))),
        ("claude", ClaudeInstallation(root / ("cli-runtime-" + claude.KIND), qualify=release_checks.claude(claude_root)),
         claude_profile, ClaudeConnectionAdapter, (("--version",), ("--help",), ("auth", "status", "--json"))),
    )
    report, passed = {}, True
    for name, installation, profile_for, adapter_for, probes in cases:
        started = time.monotonic()
        with OperationFiles(operations).open() as files:
            executable = installation.install(files)
        state = installation.snapshot()
        entry = {"install": state["state"], "error": state["error"], "version": state["installed"],
                 "seconds": round(time.monotonic() - started)}
        if executable is not None:
            profile = profile_for(executable)
            for arguments in probes:
                label = "features list" if callable(arguments) else " ".join(arguments)
                entry[label] = run(profile, executable, operations, arguments)
            entry["connection"] = connection(adapter_for(profile), operations)
        passed = passed and entry.get("connection") == SIGNED_OUT
        report[name] = entry
    print(json.dumps(report))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
