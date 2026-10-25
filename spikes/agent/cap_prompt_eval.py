"""Serve the exact CAP model inputs to an external agent and run its tool calls through the real tools.

Each sample seeds the wordy synthetic CV, opens a protocol-mode session and runs the standard read phase.
GET /transcript/<n> returns what the application sends to the model. POST /call/<n> sends one tool
call through the session's authenticated MCP endpoint, with the same preflight. GET /verify/<n> compares
the latest draft with its baseline. No model call happens here.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

from spikes.agent.cap_live_proof import REQUEST, WORDY


async def open_sample(root, edits):
    import httpx
    from packages.resume_core.agent_store import run_in
    from packages.resume_core.assistant_proposals import content_digest
    from packages.resume_core.models.rich_document import StyledText
    from resume_api.agent.capabilities import proposal_instructions
    from resume_api.agent.runtime import BASE_INSTRUCTIONS
    from resume_api.agent.service import RunControl
    from resume_api.agent.tools import ToolSession
    from tests.recovery.test_agent_tools import Fetcher
    from tests.support.assistant_fidelity import environment
    service, _, projects, workspace, seed_session = environment(root)
    await seed_session.close()
    old = run_in(service.store.load(workspace.project_id), seed_session.run.id)[2].request
    service.store.finish(workspace.project_id, seed_session.run.id, "interrupted", error="AGENT_INTERRUPTED")
    current = projects.workspaces[workspace.project_id]
    for block in current.project.document.blocks():
        if block.id in WORDY:
            block.content = [StyledText(type="text", text=WORDY[block.id], styles={})]
    assert projects.persist(workspace.project_id) == "durable"
    baseline = content_digest(projects.read(workspace.project_id))
    from packages.resume_core.models.agent import AgentRunRequest
    lease = service.leases.leases[workspace.project_id]
    request = AgentRunRequest.model_validate({**old.model_dump(by_alias=True), "clientRequestId": "eval_" + str(int(time.time() * 1000)),
        "owner": {"epoch": lease.epoch, "token": lease.token}, "allowEdits": edits, "allowWeb": False, "message": REQUEST})
    run, _ = service.submit(workspace.project_id, request)
    # Agent rounds through T3 take minutes; the application's 180-second active turn would end the run.
    from datetime import datetime, timedelta, timezone
    def extend(state):
        record = run_in(state, run.id)[1]
        record.deadline = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        return record.deadline
    service.store.update(workspace.project_id, extend)
    run = run_in(service.store.load(workspace.project_id), run.id)[1]
    control = RunControl(workspace.project_id, run.id, run.owner_epoch, run.connection_epoch, time.monotonic())
    session = ToolSession(service, control, run, Fetcher())
    _, run, journal = run_in(service.store.load(workspace.project_id), run.id)
    prompt = session.book.initial(run, journal)
    session.application = session.sdk.streamable_http_app()
    lifespan = session.application.router.lifespan_context(session.application)
    await lifespan.__aenter__()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=session), base_url="http://" + session.host,
        headers={"Authorization": "Bearer " + session.token, "Accept": "application/json, text/event-stream"})
    listed = (await client.post("/mcp", json={"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}})).json()
    sample = {"service": service, "projects": projects, "workspace": workspace, "session": session, "client": client,
        "lifespan": lifespan, "baseline": baseline, "id": 1, "calls": []}
    sample["transcript"] = {"baseInstructions": BASE_INSTRUCTIONS, "developerInstructions": proposal_instructions(),
        "tools": listed["result"]["tools"], "userTurn": prompt, "allowEdits": edits, "calls": sample["calls"]}
    return sample


async def call(sample, tool, arguments):
    sample["id"] += 1
    reply = await sample["client"].post("/mcp", json={"jsonrpc": "2.0", "id": sample["id"], "method": "tools/call",
        "params": {"name": tool, "arguments": arguments}})
    body = reply.json()
    result = body.get("result") or {}
    text = "".join(part.get("text", "") for part in result.get("content") or [])
    entry = {"tool": tool, "arguments": arguments, "isError": bool(result.get("isError")), "result": text,
        "rpcError": body.get("error")}
    sample["calls"].append(entry)
    return entry


async def read_phase(sample):
    await call(sample, "get_project_resources", {"task": {"protocolVersion": 1, "taskId": "rewrite_resume"}})
    for tool, kind in (("get_resume_context", "context"), ("get_resume_context", "document"), ("get_working_facts", "facts")):
        entry = await call(sample, tool, {"query": {"kind": kind}})
        while True:
            cursor = (json.loads(entry["result"]).get("snapshot") or {}).get("nextCursor") if entry["result"] else None
            if not cursor:
                break
            entry = await call(sample, tool, {"query": {"kind": kind, "cursor": cursor}})


def verify(sample):
    from spikes.agent.cap_live_verify import verify as compare
    values = sample["service"].proposals.list(sample["workspace"].project_id)
    if not values:
        return {"proposal": None}
    value = values[-1]
    report = compare(value.baseline.model_dump(mode="json", by_alias=True), value.candidate.model_dump(mode="json", by_alias=True), list(WORDY))
    report.update({"proposal": value.proposal.id, "state": value.proposal.state,
        "coverage": {state: sum(unit.state == state for unit in value.proposal.coverage) for state in ("changed", "unchanged", "unresolved")}})
    return report


async def main(root, samples, edits, port):
    import uvicorn
    root.mkdir(mode=0o700)
    opened = {}
    async def keep_owner():
        # The mounted UI renews the owner lease every few seconds; this host does the same between rounds.
        from types import SimpleNamespace
        while True:
            for sample in opened.values():
                project = sample["workspace"].project_id
                lease = sample["service"].leases.leases[project]
                try:
                    sample["service"].leases.renew(project, SimpleNamespace(epoch=lease.epoch, token=lease.token))
                except Exception as error:
                    print(json.dumps({"leaseRenewalFailed": str(error)}), flush=True)
            await asyncio.sleep(5)
    renewal = asyncio.create_task(keep_owner())
    for index in range(1, samples + 1):
        (root / f"sample-{index}").mkdir(mode=0o700)
        opened[index] = await open_sample(root / f"sample-{index}", edits)
        await read_phase(opened[index])


    async def app(scope, receive, send):
        if scope["type"] != "http":
            return
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        parts = scope["path"].strip("/").split("/")
        status, payload = 404, {"error": "not found"}
        try:
            index = int(parts[1]) if len(parts) > 1 else None
            if parts[0] == "transcript" and index in opened:
                status, payload = 200, opened[index]["transcript"]
            elif parts[0] == "call" and index in opened:
                request = json.loads(body)
                status, payload = 200, await call(opened[index], request["tool"], request.get("arguments") or {})
            elif parts[0] == "verify" and index in opened:
                status, payload = 200, verify(opened[index])
        except Exception as error:
            status, payload = 500, {"error": type(error).__name__, "detail": str(error)[:500]}
        data = json.dumps(payload, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": data})

    (root / "eval.json").write_text(json.dumps({"port": port, "pid": os.getpid(), "samples": samples, "allowEdits": edits}))
    print(json.dumps({"port": port, "root": str(root), "samples": samples}), flush=True)
    await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical", access_log=False)).serve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--edits", choices=("on", "off"), default="on")
    parser.add_argument("--port", type=int, required=True)
    options = parser.parse_args()
    if not str(options.root.absolute()).startswith("/private/tmp/foldcv-cap-eval-") or options.root.exists():
        raise SystemExit("A new /private/tmp/foldcv-cap-eval-* root is required")
    asyncio.run(main(options.root.absolute(), options.samples, options.edits == "on", options.port))
