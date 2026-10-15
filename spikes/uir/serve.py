"""Owned loopback proof service. All providers are explicit scripts."""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

import httpx
from fastapi import HTTPException, Request
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
import uvicorn

from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.rich_presentation import authored_text
from resume_api.agent.runtime import ScriptedAgentRuntime
from resume_api.app import create_app
from spikes.uir.fixtures import FIXTURES, HANDOFF, NOW, ALIASES, sample, structured, demo_from_workspace, write_json
from spikes.uir.providers import ScriptedConnection, ScriptedContent, StoredWeb, scripted_agent


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def build_hash(directory):
    files = {str(path.relative_to(directory)): digest(path) for path in sorted(directory.rglob("*")) if path.is_file()}
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), files


async def freeze(app, origin, secret, content):
    FIXTURES.mkdir(parents=True, exist_ok=True)
    assert not (FIXTURES / "manifest.json").exists(), "Frozen fixtures must not be overwritten"
    demo = sample(); workspace, originals, mapping = structured(demo)
    write_json(FIXTURES / "block-mapping.json", {"fieldAliases": ALIASES,
        "email": "candidate.email -> detail(kind=email).value", "rows": mapping,
        "ownerWrappers": ["owner-job-1", "owner-job-2"], "gaps": []})
    RichProjectStore(app.app.state.rich_projects.storage.root).save(workspace, originals, {})
    write_json(FIXTURES / "structured.demo.json", {"format": "foldcv-design-demo", "version": 1, "project": demo})
    (FIXTURES / "structured-source.txt").write_text(demo["original"])
    (FIXTURES / "import-source.txt").write_text(demo["original"])
    proof, projects = [], {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin, headers={"Origin": origin}) as client:
        exchange = await client.post("/v1/session/exchange", json={"secret": secret}); exchange.raise_for_status()
        status = await client.post("/v1/host/status", json={}); status.raise_for_status()
        assert status.json()["experimentalMode"] is False
        selected = await client.post("/v1/rich/projects/input", files={"file": ("import-source.txt", (FIXTURES / "import-source.txt").read_bytes(), "text/plain")})
        selected.raise_for_status(); identifier = selected.json()["workspace"]["projectId"]
        started = await client.post(f"/v1/rich/projects/{identifier}/generation", json={}); started.raise_for_status()
        service = app.app.state.rich_projects
        tasks = [task for (pid, _), task in service.tasks.items() if pid == identifier]
        await asyncio.wait_for(asyncio.gather(*tasks), 40)
        fresh = service.read(identifier)
        assert fresh.project is not None, service.response(identifier).model_dump()
        assert not fresh.project.document.regions[0].blocks and not fresh.project.document.regions[1].blocks
        units = sorted(fresh.project.sources[0].units, key=lambda unit: unit.order)
        assert [authored_text(block) for block in fresh.project.document.regions[2].blocks] == [unit.text for unit in units]
        write_json(FIXTURES / "fresh-import.demo.json", {"format": "foldcv-design-demo", "version": 1, "project": demo_from_workspace(fresh)})
        for name, pid in [("structured", workspace.project_id), ("fresh-import", identifier)]:
            response = await client.get(f"/v1/rich/projects/{pid}"); response.raise_for_status()
            before = response.json()["workspace"]
            export = await client.post(f"/v1/rich/projects/{pid}/archive", json={"projectRevision": before["projectRevision"], "documentRevision": before["documentRevision"]})
            export.raise_for_status(); (FIXTURES / f"{name}.foldcv").write_bytes(export.content)
            opened = await client.post("/v1/rich/projects/archive", files={"file": (f"{name}.foldcv", export.content, "application/zip")})
            opened.raise_for_status(); after = opened.json()["workspace"]; new_id = after["projectId"]
            assert after["project"]["document"] == before["project"]["document"]
            assert after["project"]["facts"] == before["project"]["facts"]
            assert after["project"]["sources"] == before["project"]["sources"]
            reexport = await client.post(f"/v1/rich/projects/{new_id}/archive", json={"projectRevision": after["projectRevision"], "documentRevision": after["documentRevision"]})
            reexport.raise_for_status()
            proof.append({"fixture": name, "projectId": pid, "reopenedProjectId": new_id, "routeImport": opened.status_code,
                "documentExact": True, "factsExact": True, "sourceExact": True, "reexportBytes": len(reexport.content)})
            projects[name] = pid
    write_json(FIXTURES / "recipe.json", {"timestamp": NOW, "source": "spikes/uir/fixtures.py",
        "referenceInput": "spikes/uir/reference-input.mjs; sampleProject only, no browser runtime",
        "structured": "Existing WorkspaceV6/ProjectV5/RichDocumentV1/WorkingFacts models -> RichProjectStore -> real archive route",
        "freshImport": "POST input -> POST generation -> real assessment/extraction/import -> archive route",
        "clock": NOW, "assetInputs": [], "template": workspace.project.template.model_dump(by_alias=True),
        "providerMode": "scripted", "providerCalls": content.calls,
        "nativeStarts": 0, "projects": projects})
    files = {str(path.relative_to(FIXTURES)): {"sha256": digest(path), "bytes": path.stat().st_size} for path in sorted(FIXTURES.iterdir()) if path.is_file()}
    write_json(FIXTURES / "manifest.json", {"schemaVersion": 1, "archiveSchemaVersion": 6, "projectSchemaVersion": 5,
        "documentSchemaVersion": 1, "templateId": workspace.project.template.id, "files": files,
        "sourceSha256": digest(FIXTURES / "import-source.txt"), "projects": projects,
        "identities": {name: {"regions": [r.id for r in service.read(pid).project.document.regions],
            "blocks": [b.id for b in service.read(pid).project.document.blocks()],
            "records": [r.id for r in service.read(pid).project.facts.records],
            "visibleText": [authored_text(b) for b in service.read(pid).project.document.blocks()]} for name, pid in projects.items()}})
    write_json(HANDOFF / "evidence/uir00-round-trip.json", proof)


async def main(args):
    root = args.root.resolve()
    if root.parent != Path("/private/tmp") or not root.name.startswith("foldcv-uir-"):
        raise ValueError("A dedicated /private/tmp/foldcv-uir-* root is required")
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = json.loads((HANDOFF / "state.json").read_text())
    if checkpoint["slices"][args.slice]["status"] == "accepted_with_review_debt" and not args.no_checkpoint:
        raise ValueError("Use --no-checkpoint to open retained proof without changing accepted evidence")
    (HANDOFF / "evidence").mkdir(exist_ok=True)
    dist = args.dist.resolve() if args.dist else root / "uir00-ui"
    if not args.dist:
        dist.mkdir(exist_ok=True); (dist / "index.html").write_text('<div data-app="foldcv-uir00">UIR00 reference inventory</div>')
    assert dist.is_dir()
    data, operations = root / "data", root / "operations"
    PreferencesStore(data).select_model("uir-processing")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", args.port)); listener.listen(128)
    origin = "http://127.0.0.1:" + str(listener.getsockname()[1]); secret = secrets.token_urlsafe(32)
    connection, content, web = ScriptedConnection(), ScriptedContent(), StoredWeb()
    runtime = ScriptedAgentRuntime(scripted_agent)
    # These constructors must remain unreachable even during application creation.
    with patch("resume_api.app.ConnectionAdapter", side_effect=AssertionError("native connection")), \
         patch("resume_api.app.CodexCliProvider", side_effect=AssertionError("native content")), \
         patch("resume_api.app.CodexAgentRuntime", side_effect=AssertionError("native agent")):
        app = create_app(origin=origin, secret=secret, temp_root=operations, data_root=data, dist=dist,
            experimental_profile=None, connection_adapter=connection, gui_provider=content,
            gui_clock=lambda: datetime.fromisoformat(NOW), agent_runtime=runtime)
    app.app.state.agent.tools.fetcher = web
    FIXTURES.mkdir(parents=True, exist_ok=True)
    app.app.router.routes.insert(0, Mount("/reference", app=StaticFiles(directory=ROOT / "design/future-editor", html=True)))
    app.app.router.routes.insert(0, Mount("/reference-inputs", app=StaticFiles(directory=FIXTURES)))
    info = {"schemaVersion": 1, "root": str(root), "dataRoot": str(data), "operationRoot": str(operations),
        "origin": origin, "ownedServicePid": os.getpid(), "buildDirectory": str(dist),
        "buildSha256": build_hash(dist)[0], "providers": {"connection": "ScriptedConnection", "content": "ScriptedContent",
            "agent": "ScriptedAgentRuntime", "web": "StoredWeb"}, "experimentalProfile": None,
        "nativeConstructorGuard": "all three native factory branches guarded; zero calls",
        "serviceState": "running", "sourceSha256": {str(p.relative_to(ROOT)): digest(p) for p in
            [Path(__file__), ROOT / "spikes/uir/providers.py", ROOT / "spikes/uir/fixtures.py", ROOT / "services/api/src/resume_api/app.py"]}}
    def diagnostics():
        return {**info, "callCounts": {"connection": len(connection.calls), "content": len(content.calls),
            "agent": len(runtime.calls), "web": len(web.calls), "nativeStarts": 0},
            "contentTypes": [call.get("task", call.get("kind", "structured")) for call in content.calls],
            "scriptedAttempts": content.attempts, "scriptedGateEntered": content.entered.is_set()}
    @app.app.get("/v1/uir/diagnostics")
    async def read_diagnostics(): return diagnostics()
    app.app.router.routes.insert(0, app.app.router.routes.pop())
    @app.app.post("/v1/uir/control")
    async def control(request: Request):
        value = await request.json()
        if not isinstance(value, dict) or set(value) - {"pauseType", "failKind", "assessment", "release"}:
            raise HTTPException(422)
        for key in ("pauseType", "failKind"):
            if value.get(key) not in {None, "ResumeAssessment", "GuiSemanticProposal"}:
                raise HTTPException(422)
        if value.get("assessment", "likely") not in {"likely", "unlikely", "uncertain"}:
            raise HTTPException(422)
        content.pause_type = value.get("pauseType"); content.fail_kind = value.get("failKind")
        content.assessment = value.get("assessment", "likely")
        content.entered.clear()
        if value.get("release", True): content.release.set()
        else: content.release.clear()
        return diagnostics()
    app.app.router.routes.insert(0, app.app.router.routes.pop())
    @app.app.post("/v1/uir/artifacts/{name}")
    async def retain_download(name: str, request: Request):
        if name not in {"structured.docx", "structured.foldcv", "fresh.docx", "fresh.foldcv"}:
            raise HTTPException(404)
        blob = await request.body()
        if not blob.startswith(b"PK") or len(blob) > 1_048_576:
            raise HTTPException(422)
        directory = root / "downloads"; directory.mkdir(exist_ok=True)
        (directory / name).write_bytes(blob)
        return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
    app.app.router.routes.insert(0, app.app.router.routes.pop())
    if args.freeze: await freeze(app, origin, secret, content)
    else:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin, headers={"Origin": origin}) as client:
            (await client.post("/v1/session/exchange", json={"secret": secret})).raise_for_status()
            (await client.post("/v1/host/status", json={})).raise_for_status()
            service = app.app.state.rich_projects
            service.ensure_loaded()
            if not service.workspaces:
                projects = {}
                for name in ("structured", "fresh-import"):
                    opened = await client.post("/v1/rich/projects/archive", files={"file":
                        (name + ".foldcv", (FIXTURES / (name + ".foldcv")).read_bytes(), "application/zip")})
                    opened.raise_for_status(); projects[name] = opened.json()["workspace"]["projectId"]
                write_json(root / "fixture-projects.json", projects)
    # Session exchange is one-shot. Give the browser its own unspent startup secret.
    app.session = None; app.secret = secret
    projects_path = root / "fixture-projects.json"
    projects = json.loads(projects_path.read_text()) if projects_path.exists() else json.loads((FIXTURES / "manifest.json").read_text())["projects"]
    proof_url = origin + "/uir-proof.html?project=" + projects["structured"] if args.slice != "UIR00" else origin + "/reference/"
    info["proofUrl"] = proof_url
    launch = root / "launch.json"
    write_json(launch, {"origin": origin, "url": proof_url + "#secret=" + secret, "pid": os.getpid()}); launch.chmod(0o600)
    write_json(root / "isolation.json", diagnostics())
    evidence = f"docs/gui/handoffs/PROTOTYPE-ADOPTION/evidence/{args.slice.lower()}-isolation.json"
    if not args.no_checkpoint:
        write_json(ROOT / evidence, diagnostics())
        state_path = HANDOFF / "state.json"; state = json.loads(state_path.read_text()); state["isolation"] = {**info,
            "evidence": evidence}
        write_json(state_path, state)
    print(proof_url, flush=True)
    try:
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=listener.getsockname()[1], proxy_headers=False,
            access_log=False, server_header=False, log_level="warning", timeout_graceful_shutdown=2)).serve(sockets=[listener])
    finally:
        info["serviceState"] = "stopped"
        write_json(root / "final-diagnostics.json", diagnostics())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True); parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--dist", type=Path); parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--slice", choices=[f"UIR{i:02}" for i in range(10)], default="UIR00")
    parser.add_argument("--no-checkpoint", action="store_true")
    asyncio.run(main(parser.parse_args()))
