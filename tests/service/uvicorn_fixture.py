"""Synthetic loopback server for the real ASGI disconnect test."""

import asyncio
from pathlib import Path
import socket
import sys

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from resume_api.app import create_app


class WaitingRunner:
    async def run(self, _kind, _request, files):
        assert files.path is not None
        (files.path / "active").touch()
        process = None
        if len(sys.argv) > 2 and sys.argv[2] == "child":
            process = files.spawn(Path(sys.executable), ("-c", "import time; time.sleep(30)"))
            (Path(sys.argv[1]) / "worker-pgid").write_text(str(process.pid), encoding="utf-8")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            (Path(sys.argv[1]) / "cancelled").touch()
            if process is not None and all(stream.closed for stream in (process.stdin, process.stdout, process.stderr)):
                (Path(sys.argv[1]) / "pipes-closed").touch()
            raise


async def main():
    root = Path(sys.argv[1])
    dist = root / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("synthetic shell", encoding="utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = create_app(origin=origin, secret="synthetic-startup-secret-0123456789",
                         temp_root=root / "operations", dist=dist, runner=WaitingRunner())
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, proxy_headers=False,
                                                access_log=False, log_level="critical",
                                                timeout_graceful_shutdown=2))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("Fixture server failed")
            await asyncio.sleep(0.01)
        print(origin, flush=True)
        await task


asyncio.run(main())
