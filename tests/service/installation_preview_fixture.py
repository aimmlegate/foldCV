"""Isolated setup server for manual T3 checks; no credentials or inference."""

import argparse
import asyncio
from pathlib import Path
import socket
import sys

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from resume_api.app import create_app
from resume_api.cli.distribution import managed_executable
from resume_api.cli.experimental_profile import ExperimentalCliProfile


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    options = parser.parse_args()
    root = options.root.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile = ExperimentalCliProfile(root / "store/cli-experiment", managed_executable(root / "store/cli-runtime"))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        origin = "http://127.0.0.1:" + str(listener.getsockname()[1])
        secret = "synthetic-cli-setup-preview-0123456789"
        app = create_app(origin=origin, secret=secret, temp_root=root / "operations", data_root=root / "store",
            dist=ROOT / "apps/web/dist", experimental_profile=profile)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", proxy_headers=False,
            access_log=False, server_header=False, log_level="critical"))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if task.done():
                await task
            await asyncio.sleep(0.02)
        print(origin + "/#secret=" + secret, flush=True)
        await task


if __name__ == "__main__":
    asyncio.run(main())
