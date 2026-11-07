"""Install the newest Codex and Claude releases into an empty data root, with the capability checks the desktop service
runs before a release goes in place, then check each connection as Settings does; prints a JSON report. No model call,
so a working CLI must stop at sign-in; its sign-in then starts as in Settings and must print the sign-in page that
Settings offers (D151) before it is cancelled. Exits 1 otherwise.

Usage (check_helper.py --cli runs it): `<helper>/python/python.exe -X utf8 cli_probe.py <empty data root>`.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from resume_api import release_checks
from resume_api.app_log import masked
from resume_api.providers.codex.profile import ExperimentalCliProfile
from resume_api.cli.installation import ClaudeInstallation, CliInstallation
from resume_api.cli.process_runner import ProcessExit, ProcessRunner
from resume_api.providers.claude import profile as claude
from resume_api.providers.codex.connection import ConnectionAdapter
from resume_api.providers.base import ConnectionFailure
from resume_api.providers.claude.connection import ClaudeConnectionAdapter
from resume_api.providers.sign_in import SignInOutput
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


def processes() -> dict[int, str]:
    """Running programs by id (Windows): what a sign-in leaves behind shows how the CLI opened the browser."""
    if sys.platform != "win32":
        return {}
    listing = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=30).stdout
    return {int(row[1]): row[0] for row in csv.reader(io.StringIO(listing)) if len(row) > 1 and row[1].isdigit()}


def sign_in(kind: str, adapter, operations: Path) -> dict:
    """The address Settings would offer: the sign-in runs until the CLI printed it, at most a minute, then is cancelled
    and must stop within a minute."""
    output, cancel, before = SignInOutput(kind), threading.Event(), processes()
    started = time.monotonic()

    def login():
        with OperationFiles(operations).open() as files:
            try:
                adapter.login(files, cancel, output=output)
            except (ConnectionFailure, SpikeError):
                pass

    # A worker stuck in cleanup must not keep the probe from reporting.
    worker = threading.Thread(target=login, daemon=True)
    worker.start()
    deadline = time.monotonic() + 60
    while output.url is None and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(0.2)
    cancel.set()
    worker.join(60)
    time.sleep(1)
    left = sorted({name for pid, name in processes().items() if pid not in before})
    return {"page": output.url.split("?", 1)[0] if output.url else None, "stopped": not worker.is_alive(),
            "seconds": round(time.monotonic() - started), "started programs left": left,
            "output": {name: masked(bytes(buffer).decode("utf-8", "replace"))[-400:] for name, buffer in output.streams.items()}}


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
            if entry["connection"] == SIGNED_OUT:
                entry["sign-in"] = sign_in(name + "_cli", adapter_for(profile), operations)
        signed = entry.get("sign-in", {})
        passed = passed and entry.get("connection") == SIGNED_OUT and signed.get("page") is not None and signed["stopped"]
        report[name] = entry
    print(json.dumps(report))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
