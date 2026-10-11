"""Continuous synthetic import, text operations and render fixture."""

import asyncio
from pathlib import Path
import socket
import sys

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from browser_draft_fixture import Draft, Semantic
from browser_rewrite_fixture import ForbiddenRunner, Rewrite
from resume_api.app import create_app


async def main():
    root = Path(sys.argv[1])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = create_app(origin=origin, secret="synthetic-browser-secret-0123456789",
                         temp_root=root / "operations", dist=Path(sys.argv[2]), runner=ForbiddenRunner(),
                         semantic_runner=Semantic(), draft_runner=Draft(), rewrite_runner=Rewrite(),
                         fixture_generation_ready=True)
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


if __name__ == "__main__":
    asyncio.run(main())
