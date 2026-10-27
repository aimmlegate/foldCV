"""Preflight for the tested personal local developer run."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
from pathlib import Path
import selectors
import signal
import shutil
import subprocess
import sys
import threading
import time

from tools.process_groups import signal_group

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/gui/local-version-manifest.json"


class ReadinessError(Exception):
    pass


def check_local() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if platform.system() != "Darwin" or platform.machine() != "arm64" or platform.mac_ver()[0] != manifest["macos"]:
        raise ReadinessError(f"This local run is verified only on macOS {manifest['macos']} arm64.")
    if platform.python_version() != manifest["python"]:
        raise ReadinessError(f"Use project Python {manifest['python']} in .venv; see docs/gui/local-setup.md.")
    for package, expected in manifest["pythonPackages"].items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        if actual != expected:
            raise ReadinessError(f"Python dependency {package} must be {expected}; install requirements-dev.txt.")
    if not (ROOT / "apps/web/dist/index.html").is_file():
        raise ReadinessError("Frontend build is missing; run npm ci and npm run build in apps/web.")
    from packages.resume_core.rendering.template import RenderFailure, require_template

    try:
        require_template()
    except RenderFailure as error:
        remedies = {
            "CONVERTER_UNAVAILABLE": "Run tools/install-local-renderer.sh.",
            "CONVERTER_MISMATCH": "Install the pinned LibreOffice with tools/install-local-renderer.sh.",
            "FONT_UNAVAILABLE": "Run tools/install-local-renderer.sh to install app-local fonts.",
            "FONT_MISMATCH": "Restore app-local fonts with tools/install-local-renderer.sh.",
            "ASSET_UNAVAILABLE": "Restore the checked-in template assets.",
            "ASSET_MISMATCH": "Restore the checked-in template assets.",
            "TEMPLATE_UNAVAILABLE": "Restore the checked-in template manifest.",
            "TEMPLATE_MISMATCH": "Restore the checked-in template manifest.",
        }
        raise ReadinessError(f"Renderer {error.code}: {remedies.get(error.code, 'Check local renderer assets.')}") from None


def bounded_version(executable: Path) -> str | None:
    safe_env = {key: value for key, value in os.environ.items()
                if not key.startswith(("OPENAI_", "CODEX_", "T3CODE_", "ANTHROPIC_", "GEMINI_", "AZURE_OPENAI_"))
                and key != "GOOGLE_API_KEY"}
    try:
        process = subprocess.Popen([str(executable), "--version"], cwd=ROOT, env=safe_env,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
    except OSError:
        return None
    output = bytearray()
    complete = False
    cleanup_failed = False
    try:
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + 5
            while len(output) <= 256:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    break
                chunk = os.read(process.stdout.fileno(), 257 - len(output))
                if not chunk:
                    complete = True
                    break
                output.extend(chunk)
    finally:
        # Keep the leader unreaped until its process group has been stopped.
        try:
            if signal_group(process.pid, 0):
                signal_group(process.pid, signal.SIGKILL)
        except OSError:
            cleanup_failed = True
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            cleanup_failed = True
        if process.stdout is not None:
            process.stdout.close()
    if cleanup_failed:
        raise ReadinessError("CLI version process cleanup failed; inspect owned processes before launching.")
    if not complete or len(output) > 256 or process.returncode != 0:
        return None
    try:
        return output.decode("utf-8", "strict").strip()
    except UnicodeError:
        return None


def check_cli(executable: Path | None = None) -> str:
    from resume_api.cli.profile import VERSION

    selected = executable or shutil.which("codex")
    if selected is None or not Path(selected).is_file():
        return "CLI absent; manual editing and rendering are ready."
    version = bounded_version(Path(selected))
    if version is None:
        return "CLI version unavailable; manual editing and rendering are ready."
    if version != VERSION:
        return "CLI version is outside the pinned profile; manual editing and rendering are ready."

    from resume_api.connection import ConnectionAdapter, ConnectionFailure
    from resume_api.launcher import trusted_temp_root
    from resume_api.lifecycle import OperationFiles, SpikeError

    try:
        with OperationFiles(trusted_temp_root()).open() as files:
            metadata = ConnectionAdapter(executable).inspect(files, threading.Event())
        return f"CLI metadata ready ({metadata.version}); generation remains closed by D004."
    except ConnectionFailure as error:
        if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
            raise ReadinessError("CLI metadata process cleanup failed; inspect owned operations before launching.") from None
        messages = {
            "CLI_MISSING": "CLI absent; manual editing and rendering are ready.",
            "UNSUPPORTED_VERSION": "CLI version is outside the pinned profile; manual editing and rendering are ready.",
            "LOGIN_REQUIRED": "CLI native login is absent; manual editing and rendering are ready.",
            "API_KEY_MODE": "CLI is not in native ChatGPT login mode; manual editing and rendering are ready.",
        }
        return messages.get(error.code, f"CLI metadata unavailable ({error.code}); manual editing and rendering are ready.")
    except SpikeError as error:
        if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
            raise ReadinessError("CLI metadata process cleanup failed; inspect owned operations before launching.") from None
        return "CLI metadata unavailable; manual editing and rendering are ready."
    except OSError:
        return "CLI metadata unavailable; manual editing and rendering are ready."


def check_experimental_cli() -> str:
    from resume_api.cli.experimental_profile import installed_profile, ExperimentalProfileError
    from resume_api.connection import ConnectionAdapter, ConnectionFailure
    from resume_api.launcher import trusted_temp_root
    from resume_api.lifecycle import OperationFiles, SpikeError

    profile = installed_profile(Path.home() / "Library/Application Support/FoldCV/cli-experiment")
    try:
        profile.prepare_directories()
        if not profile.executable.is_file():
            return "Personal CLI is not installed; install Codex from the app's connection settings."
        with OperationFiles(trusted_temp_root()).open() as files:
            metadata = ConnectionAdapter(profile.executable, experimental_profile=profile).inspect(files, threading.Event())
        return f"Personal CLI profile ready ({metadata.version}); choose a model in the app."
    except ExperimentalProfileError as error:
        raise ReadinessError(f"Personal CLI profile unavailable ({error}); check the dedicated profile.") from None
    except ConnectionFailure as error:
        if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
            raise ReadinessError("CLI process cleanup failed; inspect owned operations before launching.") from None
        if error.code == "LOGIN_REQUIRED":
            return "Personal CLI profile ready; separate ChatGPT sign-in is required in the app."
        raise ReadinessError(f"Personal CLI profile unavailable ({error.code}); use the default manual mode.") from None
    except SpikeError as error:
        if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
            raise ReadinessError("CLI process cleanup failed; inspect owned operations before launching.") from None
        raise ReadinessError(f"Personal CLI profile unavailable ({error.code}); use the default manual mode.") from None


def preflight(executable: Path | None = None, *, experimental_cli: bool = False) -> str:
    check_local()
    return check_experimental_cli() if experimental_cli else check_cli(executable)


def main() -> None:
    try:
        print(preflight(), file=sys.stderr)
    except ReadinessError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
