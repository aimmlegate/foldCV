"""Synthetic loopback servers for the real uvicorn checks; every file stays under the root given as the first argument.

`launcher`: the real launcher on a temporary data root and operation root.
`child`: the app whose status job starts a real child process and waits until it is cancelled."""

import asyncio
from pathlib import Path
import socket
import sys

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from resume_api.app import create_app
from resume_api.connection import ConnectionAdapter, ConnectionFailure

SECRET = "synthetic-startup-secret-0123456789"


class HeldConnection(ConnectionAdapter):
    def __init__(self, root: Path):
        super().__init__()
        self.root = root

    def inspect(self, files, cancel, *, full=True):
        process = files.spawn(Path(sys.executable), ("-c", "import signal; signal.pause()"))
        (self.root / "worker-pgid").write_text(str(process.pid), encoding="utf-8")
        cancel.wait()
        (self.root / "cancelled").touch()
        raise ConnectionFailure("CANCELLED")


async def child(root: Path):
    dist = root / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("synthetic shell", encoding="utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = create_app(origin=origin, secret=SECRET, temp_root=root / "operations", dist=dist,
                         data_root=root / "data", connection_adapter=HeldConnection(root))
        # A short grace lets SIGTERM cancel the held request instead of waiting for it.
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, proxy_headers=False,
                                                access_log=False, log_level="critical", timeout_graceful_shutdown=0.1))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("Fixture server failed")
            await asyncio.sleep(0.01)
        print(origin, flush=True)
        await task


def launcher(root: Path):
    from resume_api import launcher as module
    module.trusted_temp_root = lambda: root / "operations"
    # The launcher needs a frontend build; this check is not about the real one.
    module.ROOT = root
    (root / "apps/web/dist").mkdir(parents=True)
    (root / "apps/web/dist/index.html").write_text("<title>FoldCV</title>", encoding="utf-8")
    sys.argv = ["launcher", "--no-open"]
    module.main()


if __name__ == "__main__":
    base = Path(sys.argv[1])
    if sys.argv[2] == "launcher":
        launcher(base)
    else:
        asyncio.run(child(base))
