"""Local synthetic connection preview for native visual checks."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import socket
import sys
import time

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from resume_api.app import create_app
from resume_api.connection import ConnectionAdapter, ConnectionFailure
from spikes.cli.profile import VERSION
from tests.service.test_connection import SCRIPT


class HeldCleanupAdapter(ConnectionAdapter):
    def inspect(self, files, cancel, *, full=True):
        if not cancel.wait(10):
            raise ConnectionFailure("METADATA_FAILED")
        time.sleep(0.75)
        raise ConnectionFailure("PROCESS_CLEANUP_FAILED")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("valid", "missing_login", "api_key", "no_quota", "quota",
                                           "unauthorized_quota", "failed_quota", "slow_login", "valid_login",
                                           "bad_model", "wrong_version", "missing_cli", "launcher_unsupported",
                                           "held_cleanup"), default="valid")
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    base = args.root.resolve()
    base.mkdir(parents=True, exist_ok=True)
    cli = base / "synthetic codex"
    cli.write_text(("#!/usr/bin/env node\n" if args.case == "launcher_unsupported" else
                    "#!" + sys.executable + "\n" + SCRIPT))
    cli.chmod(0o700)
    (base / "config.json").write_text(json.dumps({"case": args.case,
                                                  "version": "codex-cli 0.0.1" if args.case == "wrong_version" else VERSION + "-fixture"}))
    dist = ROOT / "apps/web/dist"
    if not (dist / "index.html").is_file():
        raise RuntimeError("Build apps/web first")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        adapter = (HeldCleanupAdapter(cli) if args.case == "held_cleanup" else
                   ConnectionAdapter(base / "missing codex" if args.case == "missing_cli" else cli,
                                     allow_fixture=True,
                                     node_executable=base / "missing node" if args.case == "launcher_unsupported" else None))
        app = create_app(origin=origin, secret="synthetic-preview-secret-0123456789",
                         temp_root=base / "operations", dist=dist,
                         connection_adapter=adapter)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                                proxy_headers=False, access_log=False,
                                                server_header=False, log_level="critical"))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("Preview server did not start")
            await asyncio.sleep(0.01)
        print(f"{origin}/#secret=synthetic-preview-secret-0123456789", flush=True)
        await task


if __name__ == "__main__":
    asyncio.run(main())
