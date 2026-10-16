"""Owned T3 proof service; all inference uses verified synthetic pipe peers."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import signal
import socket
from unittest.mock import patch

import uvicorn

from spikes.background.writer_bridge import Bridge


async def main(args):
    root = args.root.resolve()
    prefix = "foldcv-" + (args.proof_slice or ("nb05" if args.fixed_operations else "nb03")) + "-"
    if root.parent != Path("/private/tmp") or not root.name.startswith(prefix) or root.exists():
        raise ValueError("Use a new owned /private/tmp proof root")
    root.mkdir(mode=0o700)
    listener = socket.socket()
    listener.bind(("127.0.0.1", args.port)); listener.listen(128)
    origin = "http://127.0.0.1:" + str(listener.getsockname()[1])
    bridge = Bridge(root, dist=args.dist.resolve(), origin=origin)
    bridge.send = lambda value: None
    with patch("resume_api.app.ConnectionAdapter", side_effect=AssertionError("Native connection reached")), \
         patch("resume_api.app.CodexCliProvider", side_effect=AssertionError("Native content reached")), \
         patch("resume_api.app.CodexAgentRuntime", side_effect=AssertionError("Native agent reached")):
        await bridge.start()
        await serve(args, root, listener, origin, bridge)


async def serve(args, root, listener, origin, bridge):
    # HTTP submissions use the same script as the pipe-driven API integration.
    def factory(job, model):
        if job.submission.kind != "agent":
            from resume_api.jobs.fixed_runtime import FixedRuntime
            return FixedRuntime(bridge.service, job, model)
        bridge.script(job.submission.identity.request_id, "Scripted background edit")
        return bridge.factory(job, model)
    bridge.service.supervisor.factory = factory
    if args.fixed_operations:
        from spikes.background.fixed_fixtures import FixedProofProvider
        bridge.fixed_provider = FixedProofProvider()
        bridge.service.projects.provider_factory = lambda: (bridge.fixed_provider, "processing-model")
    names = ["scripted_model_ready"] + (["fixed_model_ready"] if args.fixed_operations else [])
    tokens = ["t3-controlled-" + name for name in names]
    if args.hold_model:
        def reached(value):
            if value.get("event") == "hook" and value.get("token") in tokens:
                (root / "model-gate.json").write_text(json.dumps({"name": value["name"],
                    "job": value["job"], "status": "reached"}, indent=2) + "\n")
        bridge.send = reached
        for name, token in zip(names, tokens):
            await bridge.handle({"kind": "hold", "name": name, "family": "job", "token": token})
    other = await bridge.handle({"kind": "clone"})
    secret = secrets.token_urlsafe(32)
    bridge.application.session, bridge.application.secret = None, secret
    launch = {"origin": origin, "url": origin + "/?project=" + bridge.project + "#secret=" + secret,
        "project": bridge.project, "otherProject": other["project"], "pid": os.getpid()}
    path = root / "launch.json"; path.write_text(json.dumps(launch)); path.chmod(0o600)
    info = {"root": str(root), "origin": origin, "pid": os.getpid(), "project": bridge.project,
        "otherProject": other["project"], "backgroundEnabled": True, "parallelEnabled": False,
        "capacity": 1, "nativeStarts": 0, "providers": ["MetadataAdapter", "ScriptedAgentRuntime", "PipeExecutions"]
            + (["FixedProofProvider"] if args.fixed_operations else []),
        "dist": str(args.dist.resolve()), "status": "running", "holdModel": args.hold_model,
        "stopSignal": "SIGUSR1", "releaseModelSignal": "SIGUSR2" if args.hold_model else None,
        "fixedOperations": args.fixed_operations}
    isolation = root / "isolation.json"; isolation.write_text(json.dumps(info, indent=2) + "\n")
    server = uvicorn.Server(uvicorn.Config(bridge.application, host="127.0.0.1", port=listener.getsockname()[1],
        log_level="warning", lifespan="off"))
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGUSR1, setattr, server, "should_exit", True)
    if args.hold_model:
        async def release():
            for token in tokens:
                with bridge.lock:
                    held = token in bridge.holds
                if held:
                    await bridge.handle({"kind": "release", "token": token})
            path = root / "model-gate.json"
            value = json.loads(path.read_text()) if path.exists() else {"name": "scripted_model_ready"}
            path.write_text(json.dumps({**value, "status": "released"}, indent=2) + "\n")
        loop.add_signal_handler(signal.SIGUSR2, lambda: asyncio.create_task(release()))
    print(origin + "/?project=" + bridge.project, flush=True)
    try:
        await server.serve(sockets=[listener])
    finally:
        try:
            await bridge.close()
        except BaseException:
            info.update(status="cleanup_failed", syntheticStarts=len(bridge.factory.calls))
            raise
        else:
            info.update(status="stopped", syntheticStarts=len(bridge.factory.calls), verifiedChildrenDead=True,
                fixedSyntheticStarts=len(getattr(getattr(bridge, "fixed_provider", None), "calls", [])))
        finally:
            listener.close()
            isolation.write_text(json.dumps(info, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--hold-model", action="store_true")
    parser.add_argument("--fixed-operations", action="store_true")
    parser.add_argument("--proof-slice", choices=("nb03", "nb05", "nb06"))
    asyncio.run(main(parser.parse_args()))
