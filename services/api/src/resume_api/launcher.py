"""Start the personal local service on an ephemeral loopback port."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import webbrowser

from pydantic import Field
import uvicorn

from .agent.claude_runtime import ClaudeAgentRuntime
from .app import ProviderSlot, create_app
from .host_models import Transport
from .lifecycle import require_supported_host, tune_garbage_collector
from .cli.experimental_profile import installed_profile
from .cli.installation import ClaudeInstallation
from .cli.profiles import claude
from .cli.profiles.claude import ClaudeCliProfile
from .connection_claude import ClaudeConnectionAdapter
from .providers.claude_cli import ClaudeCliProvider


ROOT = Path(__file__).resolve().parents[4]
STARTUP_TIMEOUT_SECONDS = 5
SHUTDOWN_TIMEOUT_SECONDS = 5
# Template import is the default flow; the cap bounds one import's model calls (the CT06 live runs used 60; D117 adds
# an outline, its review and two calls per entry of a block extracted entry by entry).
TEMPLATE_IMPORT_CALL_CAP = 150


class HostLaunchOptions(Transport):
    openBrowser: bool = True
    port: int = Field(default=0, ge=0, le=65535)


def trusted_temp_root() -> Path:
    result = subprocess.run(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"],
                            capture_output=True, text=True, check=True, timeout=2)
    base = Path(result.stdout.strip()).resolve(strict=True)
    if not base.is_dir() or not str(base).startswith("/private/var/folders/"):
        raise RuntimeError("Trusted macOS temporary directory is unavailable")
    return base / "foldcv-service"


def bind_claude(slot: ProviderSlot, executable: Path) -> ProviderSlot:
    profile = ClaudeCliProfile(slot.profile.root, executable)
    runtime = ClaudeAgentRuntime(profile, slot.runtime.temp_root) if slot.runtime is not None else None
    return ProviderSlot(ClaudeConnectionAdapter(profile), ClaudeCliProvider(executable, profile=profile), profile,
                        slot.installation, runtime, rebind=bind_claude)


def claude_slot(data_root: Path, temp_root: Path | None = None, *, managed_only: bool = False) -> ProviderSlot:
    """Claude next to Codex; it stays unlisted until its parity matrix passes (MP07), so it runs nothing.
    FoldCV's managed runtime comes first, then a native install, else the managed path that Settings installs into;
    the desktop app passes managed_only. Without `temp_root` the slot has no assistant runtime."""
    installation = ClaudeInstallation(data_root / ("cli-runtime-" + claude.KIND))
    managed = installation.executable
    executable = managed if managed_only or managed.is_file() else claude.installed_executable() or managed
    profile = ClaudeCliProfile(data_root / ("cli-profile-" + claude.KIND), executable)
    runtime = ClaudeAgentRuntime(profile, temp_root) if temp_root is not None else None
    return bind_claude(ProviderSlot(None, profile=profile, installation=installation, runtime=runtime), executable)


async def launch(*, port: int = 0, open_browser: bool = True,
                 cli_executable: Path | None = None,
                 experimental_cli: bool = False) -> None:
    require_supported_host()
    dist = ROOT / "apps/web/dist"
    if not (dist / "index.html").is_file():
        raise RuntimeError("Frontend build is missing; run npm run build in apps/web")
    temp_root = trusted_temp_root()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        actual_port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{actual_port}"
        secret = secrets.token_urlsafe(32)
        profile = (installed_profile(Path.home() / "Library/Application Support/FoldCV/cli-experiment")
                   if experimental_cli else None)
        app = create_app(origin=origin, secret=secret, temp_root=temp_root, dist=dist,
                         cli_executable=profile.executable if profile else cli_executable,
                         experimental_profile=profile, template_import_call_cap=TEMPLATE_IMPORT_CALL_CAP,
                         provider_slots={"claude_cli": claude_slot(Path.home() / "Library/Application Support/FoldCV",
                                                                   temp_root)}
                         if experimental_cli else None)
        tune_garbage_collector()
        config = uvicorn.Config(app, host="127.0.0.1", port=actual_port, proxy_headers=False,
                                access_log=False, server_header=False, log_level="critical",
                                timeout_graceful_shutdown=2)
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            startup_deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("Service failed to start")
                if time.monotonic() >= startup_deadline:
                    raise RuntimeError("Service startup timed out")
                await asyncio.sleep(0.02)
            print(origin, flush=True)
            if open_browser:
                webbrowser.open(f"{origin}/#secret={secret}")
            while not task.done() and not server.should_exit:
                await asyncio.sleep(0.05)
            if not task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=SHUTDOWN_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    raise RuntimeError("Service shutdown timed out") from None
            else:
                await task
        finally:
            server.should_exit = True
            if not task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=SHUTDOWN_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    task.cancel()
                    await asyncio.wait((task,), timeout=0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FoldCV locally")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--experimental-cli", action="store_true")
    parser.add_argument("--codex-executable", type=Path,
                        default=Path(os.environ["FOLDCV_CODEX_EXECUTABLE"]) if os.environ.get("FOLDCV_CODEX_EXECUTABLE") else None)
    options = parser.parse_args()
    if options.experimental_cli and options.codex_executable is not None:
        parser.error("--experimental-cli uses the pinned native CLI; omit --codex-executable")
    try:
        selected = HostLaunchOptions(openBrowser=not options.no_open, port=options.port)
    except ValueError:
        parser.error("port must be between 0 and 65535")
    asyncio.run(launch(port=selected.port, open_browser=selected.openBrowser,
                       cli_executable=options.codex_executable,
                       experimental_cli=options.experimental_cli))


if __name__ == "__main__":
    main()
