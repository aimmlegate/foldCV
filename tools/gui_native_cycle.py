"""Run the real native GUI in an explicitly selected private test store."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

from packages.resume_core.rules import HEADER, RulesStore
from packages.resume_core.storage import atomic_write, private_file

MARKER = ".foldcv-ne-store"


def private_path(path: Path, *, directory: bool) -> Path:
    path = path.absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("CYCLE_UNSAFE_PATH")
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
        raise ValueError("CYCLE_UNSAFE_PATH")
    if directory != path.is_dir():
        raise ValueError("CYCLE_UNSAFE_PATH")
    return path


def verified_bytes(path: Path, sha256: str) -> bytes:
    private_path(path, directory=False)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != sha256:
        raise ValueError("CYCLE_HASH_MISMATCH")
    return content


def optional_portable(path: Path | None, sha256: str | None) -> bytes | None:
    if path is None and sha256 is None:
        return None
    if path is None or sha256 is None:
        raise ValueError("CYCLE_PORTABLE_CONFIG")
    if private_path(path, directory=False).stat().st_size > 64 * 1024 * 1024:
        raise ValueError("CYCLE_PORTABLE_LIMIT")
    return verified_bytes(path, sha256)


def select_store(root: Path, rules_path: Path, rules_sha256: str, model: str,
                 profile: Path, *, reuse: bool) -> Path:
    root = Path(os.path.abspath(root))
    normal = Path.home() / "Library/Application Support/FoldCV"
    if root == normal or root.is_relative_to(normal) or normal.is_relative_to(root):
        raise ValueError("CYCLE_NORMAL_STORE_DENIED")
    private_path(profile, directory=True)
    private_file(rules_path)
    raw = rules_path.read_bytes()
    match = HEADER.match(raw.decode("utf-8"))
    if match is None or hashlib.sha256(raw[match.end():]).hexdigest() != rules_sha256:
        raise ValueError("CYCLE_RULES_MISMATCH")
    marker = {"version": 1, "model": model, "profile": str(profile.absolute()), "rulesSha256": rules_sha256}
    if reuse:
        private_path(root, directory=True)
        private_path(root / MARKER, directory=False)
        if json.loads((root / MARKER).read_text()) != marker:
            raise ValueError("CYCLE_STORE_MISMATCH")
        if RulesStore(root).load().sha256 != rules_sha256:
            raise ValueError("CYCLE_RULES_MISMATCH")
        return root
    if root.exists():
        raise ValueError("CYCLE_STORE_EXISTS")
    private_path(root.parent, directory=True)
    root.mkdir(mode=0o700)
    atomic_write(root / "rules.md", raw)
    atomic_write(root / "preferences.json", json.dumps({"schemaVersion": 1, "selectedModel": model,
                 "automaticAnalysis": True, "theme": "system"}).encode())
    atomic_write(root / MARKER, json.dumps(marker).encode())
    if RulesStore(root).load().sha256 != rules_sha256:
        raise ValueError("CYCLE_RULES_MISMATCH")
    return root


async def serve(args: argparse.Namespace) -> None:
    import uvicorn
    from fastapi.responses import Response
    from resume_api.app import create_app
    from resume_api.cli.experimental_profile import ExperimentalCliProfile
    from resume_api.providers.codex_cli import CodexCliProvider

    source = verified_bytes(args.source, args.source_sha256)
    portable = optional_portable(args.portable, args.portable_sha256)
    store = select_store(args.store, args.rules, args.rules_sha256, args.model, args.profile,
                         reuse=args.reuse_store)
    evidence = private_path(args.evidence, directory=True)
    started, calls = time.monotonic(), 0

    def emit(**fields: object) -> None:
        row = {"seconds": round(time.monotonic() - started, 3), **fields}
        path = evidence / "events.jsonl"
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a") as output:
            output.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)

    original_generate = CodexCliProvider._generate

    def generate(provider, request, files, cancel):
        nonlocal calls
        calls += 1
        number = calls
        emit(nativeCall=number, kind=request.result_type.__name__, status="started", selectedModel=request.policy.model)
        original_run = provider.process.run

        def capture(files, arguments, **kwargs):
            accept = kwargs.get("on_line")
            if arguments[0] == "exec" and "--help" not in arguments and accept:
                def line(raw):
                    try:
                        event = json.loads(raw)
                    except (ValueError, UnicodeError):
                        return accept(raw)
                    item = event.get("item") if isinstance(event, dict) else None
                    if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                        atomic_write(evidence / f"provider-{number}.json", item["text"].encode())
                    return accept(raw)
                kwargs["on_line"] = line
            return original_run(files, arguments, **kwargs)

        provider.process.run = capture
        try:
            result = original_generate(provider, request, files, cancel)
            emit(nativeCall=number, status="completed", elapsedSeconds=round(result.elapsed_seconds, 2),
                 logicalAttempts=result.logical_attempts)
            return result
        except Exception as error:
            emit(nativeCall=number, status="failed", code=getattr(error, "code", type(error).__name__))
            raise
        finally:
            provider.process.run = original_run

    CodexCliProvider._generate = generate
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        secret = secrets.token_urlsafe(32)
        app = create_app(origin=origin, secret=secret, temp_root=evidence / "operations",
                         dist=ROOT / "apps/web/dist", experimental_profile=ExperimentalCliProfile(args.profile),
                         data_root=store)

        @app.app.get("/v1/operator/source")
        async def original_source():
            return Response(source, media_type=args.mime, headers={"Cache-Control": "no-store"})

        route = app.app.router.routes.pop()
        app.app.router.routes.insert(0, route)
        if portable is not None:
            @app.app.get("/v1/operator/portable")
            async def portable_source():
                return Response(portable, media_type="application/zip", headers={"Cache-Control": "no-store"})

            route = app.app.router.routes.pop()
            app.app.router.routes.insert(0, route)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", access_log=False, server_header=False,
                                             log_level="critical", timeout_graceful_shutdown=2))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("CYCLE_START_FAILED")
            await asyncio.sleep(0.05)
        meta = {"pid": os.getpid(), "origin": origin, "url": origin + "/#secret=" + secret,
                "store": str(store), "sourceSha256": args.source_sha256, "rulesSha256": args.rules_sha256,
                "model": args.model, "profile": str(args.profile), "helper": str(Path(__file__).resolve())}
        atomic_write(evidence / "startup.json", json.dumps(meta).encode())
        emit(ready=True, origin=origin, evidence=str(evidence), pid=os.getpid())
        await task


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "store", "rules", "profile", "evidence"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("source-sha256", "rules-sha256", "model"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--portable", type=Path)
    parser.add_argument("--portable-sha256")
    parser.add_argument("--mime", choices=("application/pdf",), required=True)
    parser.add_argument("--reuse-store", action="store_true")
    asyncio.run(serve(parser.parse_args()))


if __name__ == "__main__":
    main()
