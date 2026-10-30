"""Serve FoldCV for the desktop app (macOS and Windows): its Electron shell starts this process and opens the page.

The shell passes the data root as the only argument. When the service listens, it writes one JSON line with the
origin and the startup secret to stdout. Closing stdin, or SIGTERM, stops it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import secrets
import socket
import sys
import threading
import time

import uvicorn

from packages.resume_core import host
from packages.resume_core.storage import atomic_write, private_directory
from .app import create_app
from .cli.experimental_profile import installed_profile, use_system_certificates
from .launcher import TEMPLATE_IMPORT_CALL_CAP, claude_slot
from .lifecycle import require_supported_host, tune_garbage_collector

PORT_FILE = "desktop-port"
# A first start of a fresh install also waits for the system's scan of the bundle.
STARTUP_TIMEOUT_SECONDS = 60


def frontend() -> Path:
    # The frozen helper carries the built frontend at the checkout's relative path.
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[4])) / "apps/web/dist"


def listen(root: Path) -> socket.socket:
    """Take the last run's port when it is free: the page keeps its origin and so the unsent edits it stores."""
    saved = root / PORT_FILE
    try:
        preferred = int(saved.read_text(encoding="ascii"))
    except (OSError, ValueError):
        preferred = 0
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Connections of the last run may still hold the port in TIME_WAIT. On Windows the option would also let
        # this socket share a port that another one listens on, and TIME_WAIT does not block the bind there.
        if not host.WINDOWS:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", preferred if 1024 <= preferred <= 65535 else 0))
        except OSError:
            listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        if port != preferred:
            atomic_write(saved, f"{port}\n".encode("ascii"))
        return listener
    except BaseException:
        listener.close()
        raise


async def serve(root: Path, control=None, output=None) -> None:
    control = control or sys.stdin.buffer
    output = output or sys.stdout
    require_supported_host()
    if not (frontend() / "index.html").is_file():
        raise RuntimeError("Frontend build is missing")
    private_directory(root)
    use_system_certificates()
    profile = installed_profile(root / "cli-profile", managed_only=True)
    with listen(root) as listener:
        port = listener.getsockname()[1]
        origin, secret = f"http://127.0.0.1:{port}", secrets.token_urlsafe(32)
        # Operations stay in the data root: a service reaps its operations root at startup, so roots must not be shared.
        operations = root / "operations"
        app = create_app(origin=origin, secret=secret, temp_root=operations, dist=frontend(),
                         cli_executable=profile.executable, experimental_profile=profile, data_root=root,
                         template_import_call_cap=TEMPLATE_IMPORT_CALL_CAP,
                         provider_slots={"claude_cli": claude_slot(root, operations, managed_only=True)})
        tune_garbage_collector()
        # Fixed implementations: the frozen helper bundles only these.
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, http="h11", ws="none", loop="asyncio",
                                               lifespan="on", proxy_headers=False, access_log=False, server_header=False,
                                               log_level="critical", timeout_graceful_shutdown=2))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        loop = asyncio.get_running_loop()

        def watch():
            control.read()
            loop.call_soon_threadsafe(setattr, server, "should_exit", True)

        threading.Thread(target=watch, daemon=True).start()
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("Service failed to start")
            if time.monotonic() >= deadline:
                # A stuck lifespan startup does not see should_exit.
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise RuntimeError("Service startup timed out")
            await asyncio.sleep(0.02)
        output.write(json.dumps({"origin": origin, "secret": secret}) + "\n")
        output.flush()
        await task


def check() -> int:
    """Build check of the frozen helper: every file the service reads at run time is in place."""
    from packages.resume_core.rendering.captured_docx import renderer_identity
    from packages.resume_core.rendering.layout import ASSETS
    from packages.resume_core.rendering.rich_docx import renderer_sha256
    from packages.resume_core.rules import DEFAULT_RULES
    from packages.resume_core.templates.store import BUNDLED_TEMPLATES
    from .assistant.skills import SKILLS, read_skill

    missing = [str(path) for path in (frontend() / "index.html", ASSETS, *BUNDLED_TEMPLATES.values())
               if not path.exists()]
    skills = [read_skill(skill.id, resource)["resource"] for skill in SKILLS for resource in skill.resources]
    if missing or not DEFAULT_RULES:
        raise RuntimeError("Missing resources: " + ", ".join(missing))
    print(json.dumps({"renderer": renderer_identity().sha256, "richRenderer": renderer_sha256(),
                      "templates": sorted(BUNDLED_TEMPLATES), "skills": len(skills)}))
    return 0


def main(arguments: list[str]) -> int:
    if len(arguments) != 1 or not Path(arguments[0]).is_absolute():
        sys.stderr.write("usage: serve <absolute data root>\n")
        return 64
    asyncio.run(serve(Path(arguments[0])))
    return 0
