"""Install the pinned Codex and Claude runtimes into an empty data root and run each through its profile, as the
desktop service does; prints a JSON report. No sign-in, no model call.

Usage (check_helper.py --cli runs it): `<helper>/python/python.exe -X utf8 cli_probe.py <empty data root>`.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time

from resume_api.cli.experimental_profile import ExperimentalCliProfile
from resume_api.cli.installation import ClaudeInstallation, CliInstallation
from resume_api.cli.process_runner import ProcessExit, ProcessRunner
from resume_api.cli.profiles import claude
from resume_api.lifecycle import OperationFiles, SpikeError


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


def main(root: Path) -> int:
    operations = root / "operations"
    codex_profile = lambda executable: ExperimentalCliProfile(root / "cli-profile", executable)  # noqa: E731
    claude_profile = lambda executable: claude.ClaudeCliProfile(root / ("cli-profile-" + claude.KIND),  # noqa: E731
                                                                executable)
    cases = (
        ("codex", CliInstallation(root / "cli-runtime"), codex_profile,
         (("--version",), ("exec", "--help"), ("login", "status"),
          lambda operation: ("features", "list", *codex_profile(None).config(operation)))),
        ("claude", ClaudeInstallation(root / ("cli-runtime-" + claude.KIND)), claude_profile,
         (("--version",), ("--help",), ("auth", "status", "--json"))),
    )
    report = {}
    for name, installation, profile_for, probes in cases:
        started = time.monotonic()
        with OperationFiles(operations).open() as files:
            executable = installation.install(files)
        state = installation.snapshot()
        entry = {"install": state["state"], "error": state["error"], "seconds": round(time.monotonic() - started)}
        if executable is not None:
            profile = profile_for(executable)
            for arguments in probes:
                label = "features list" if callable(arguments) else " ".join(arguments)
                entry[label] = run(profile, executable, operations, arguments)
        report[name] = entry
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
