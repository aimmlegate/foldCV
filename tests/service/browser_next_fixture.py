"""API-served built recovery entry with controlled creation replies only."""

import asyncio
from pathlib import Path
import socket
import sys

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from resume_api.app import create_app
from tests.recovery.generation_fixtures import CreationProvider, frozen_now


async def main():
    root, dist = Path(sys.argv[1]), Path(sys.argv[2])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = create_app(origin=origin, secret="synthetic-next-secret-0123456789",
            temp_root=root / "operations", data_root=root / "FoldCV", dist=dist,
            gui_provider=CreationProvider(), gui_clock=frozen_now)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
            proxy_headers=False, access_log=False, log_level="critical", timeout_graceful_shutdown=2))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("Controlled entry server failed")
            await asyncio.sleep(0.01)
        print(origin, flush=True)
        await task


if __name__ == "__main__":
    asyncio.run(main())
