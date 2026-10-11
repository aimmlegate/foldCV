"""Loopback fixture for the real import/editor rewrite path."""

import asyncio
import json
from pathlib import Path
import socket
import sys

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from packages.resume_core.rewriting import RewriteProposal, rewrite_input, validate_rewrite
from resume_api.app import create_app


class ForbiddenRunner:
    async def run(self, kind, request, files):
        (Path(sys.argv[1]) / "generation-attempt").touch()
        raise AssertionError("unexpected generic generation")


class Rewrite:
    def run(self, request, files, cancel):
        prompt = json.loads(rewrite_input(request))
        root = Path(sys.argv[1])
        (root / "rewrite-payload.json").write_text(json.dumps(prompt, ensure_ascii=False, indent=2))
        (root / "rewrite-calls").write_text(str(int((root / "rewrite-calls").read_text()) + 1
                                                   if (root / "rewrite-calls").exists() else 1))
        proposal = RewriteProposal(blockId=request.block_id,
            replacementText="Rewritten: " + request.current_text,
            factIds=[fact["id"] for fact in prompt["facts"]])
        return validate_rewrite(request, proposal), {"logicalAttempts": 1, "inputTokens": 10,
                                                    "outputTokens": 10, "inferenceCount": None}


async def main():
    root = Path(sys.argv[1])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = create_app(origin=origin, secret="synthetic-browser-secret-0123456789",
                         temp_root=root / "operations", dist=Path(sys.argv[2]), runner=ForbiddenRunner(),
                         rewrite_runner=Rewrite())
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
