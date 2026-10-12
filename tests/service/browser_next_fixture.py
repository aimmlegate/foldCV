"""API-served built recovery entry with controlled creation replies only."""

import asyncio
from pathlib import Path
import socket
import sys
import json

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from resume_api.app import create_app
from tests.recovery.generation_fixtures import CreationProvider, frozen_now


def retain_evidence(root, store, example):
    for id, workspace in store.workspaces.items():
        if workspace.project is None:
            continue
        evidence = root / "evidence" / id
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "workspace.json").write_text(workspace.model_dump_json(by_alias=True, indent=2) + "\n")
        for (pid, source_id), content in store.originals.items():
            if pid == id:
                (evidence / (source_id + ".txt")).write_bytes(content)
        for snapshot in workspace.project.renders:
            content = store.artifacts.get((id, snapshot.id))
            if content is not None:
                (evidence / (snapshot.id + ".docx")).write_bytes(content)
        (evidence / "test-evidence.json").write_text(json.dumps({
            "controlledProvidersOnly": True, "nativeInference": False,
            "frozenClock": "2026-10-11T12:00:00+00:00", "example": example,
        }, indent=2) + "\n")


async def main():
    root, dist = Path(sys.argv[1]), Path(sys.argv[2])
    example = sys.argv[3] if len(sys.argv) > 3 else "E1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = create_app(origin=origin, secret="synthetic-next-secret-0123456789",
            temp_root=root / "operations", data_root=root / "FoldCV", dist=dist,
            gui_provider=CreationProvider(example.split("-")[0], remove_focus=example.endswith("-focus")), gui_clock=frozen_now)
        store = app.app.state.gui_projects
        run = store._run
        async def run_retained(*args):
            await run(*args)
            retain_evidence(root, store, example)
        store._run = run_retained
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
