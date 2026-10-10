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

import uvicorn

from .app import create_app
from .contracts import HostLaunchOptions
from .lifecycle import require_supported_host


ROOT = Path(__file__).resolve().parents[4]
STARTUP_TIMEOUT_SECONDS = 5
SHUTDOWN_TIMEOUT_SECONDS = 5


def trusted_temp_root() -> Path:
    result = subprocess.run(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"],
                            capture_output=True, text=True, check=True, timeout=2)
    base = Path(result.stdout.strip()).resolve(strict=True)
    if not base.is_dir() or not str(base).startswith("/private/var/folders/"):
        raise RuntimeError("Trusted macOS temporary directory is unavailable")
    return base / "foldcv-service"


async def launch(*, port: int = 0, open_browser: bool = True,
                 cli_executable: Path | None = None) -> None:
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
        app = create_app(origin=origin, secret=secret, temp_root=temp_root, dist=dist,
                         cli_executable=cli_executable)
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
    parser.add_argument("--codex-executable", type=Path,
                        default=Path(os.environ["FOLDCV_CODEX_EXECUTABLE"]) if os.environ.get("FOLDCV_CODEX_EXECUTABLE") else None)
    options = parser.parse_args()
    try:
        selected = HostLaunchOptions(openBrowser=not options.no_open, port=options.port)
    except ValueError:
        parser.error("port must be between 0 and 65535")
    asyncio.run(launch(port=selected.port, open_browser=selected.openBrowser,
                       cli_executable=options.codex_executable))


if __name__ == "__main__":
    main()
