"""MP05 live proof on Claude (D098 item 5): a dispatch-free schema gate, the canary run and one Generic import.

Each live run is written to native-attempts.json before it dispatches; a failed run stops the work. The import's CV,
project, replies and DOCX stay in a new /private/tmp root; evidence keeps only models, timings, counts and codes.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import functools
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

from pydantic import BaseModel, ConfigDict  # noqa: E402

from resume_api.cli.process_runner import ProcessExit, ProcessRunner  # noqa: E402
from resume_api.cli.profiles import claude  # noqa: E402
from resume_api.launcher import claude_slot  # noqa: E402
from resume_api.lifecycle import OperationFiles, SpikeError  # noqa: E402
from resume_api.providers.content import ContentFailure, ContentInput, GenerationPolicy  # noqa: E402

DATA = Path.home() / "Library/Application Support/FoldCV"
EVIDENCE = ROOT / "docs/gui/handoffs/MULTI-PROVIDER/mp05"
LEDGER = ROOT / "docs/gui/handoffs/MULTI-PROVIDER/native-attempts.json"
# Sonnet at its catalog default effort, which an import captures.
MODEL, EFFORT = "claude-sonnet-5-5", "high"
# CV-B of the D097 live imports (LIVE-02, LIVE-11, LIVE-14, LIVE-15 on Codex).
CV_B = "3a2cb324ec603c053c820afd1731024a97b0fd1b16fb2dda30380296cb4b90d9"
EXPECTED = {"answer": "ready", "count": 3, "items": ["alpha", "beta", "gamma"]}
# MP06a-1: a read-only request; the evidence keeps no answer text.
ASSISTANT_PROMPT = ("Проверь резюме по текущему шаблону и назови до трёх самых важных замечаний. Ничего не меняй.")


class Synthetic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    count: int
    items: list[str]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(name: str, value: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(value, indent=2, ensure_ascii=False)[:4000])


def fresh_root(label: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"foldcv-mp05-{label}-", dir="/private/tmp"))


class Refused(logging.Handler):
    """Collects the stream events the provider refused, by kind only."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.kinds = Counter()
        logging.getLogger("resume_api.providers.claude_cli").addHandler(self)

    def emit(self, record):
        self.kinds[record.getMessage()] += 1


def ledger() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def charge(entry: dict, *, after: str | None) -> dict:
    """Record the run before it dispatches; refuse past the cap, a repeat, or after a failed run that the user has
    not asked to retry (the retry names it in `retryOf`)."""
    book = ledger()
    attempts = book["attempts"]
    if book["spent"] >= book["cap"] or any(item["id"] == entry["id"] for item in attempts):
        raise SystemExit(f"{entry['id']}: allowance used or run already recorded")
    retried = {item.get("retryOf") for item in attempts if item["status"] == "completed"}
    failed = [item["id"] for item in attempts if item["status"] != "completed" and item["id"] not in retried]
    if failed and failed != [entry.get("retryOf")]:
        raise SystemExit("a recorded run did not complete; live work stops (decision 5)")
    if after is not None and not any(item["status"] == "completed" and after in (item["id"], item.get("retryOf"))
                                     for item in attempts):
        raise SystemExit(f"{entry['id']} needs {after} first")
    attempts.append(entry)
    book["spent"] += 1
    LEDGER.write_text(json.dumps(book, indent=1) + "\n", encoding="utf-8")
    return book


def settle(entry_id: str, **fields) -> None:
    book = ledger()
    next(item for item in book["attempts"] if item["id"] == entry_id).update(fields)
    LEDGER.write_text(json.dumps(book, indent=1) + "\n", encoding="utf-8")


def scan(profile: claude.ClaudeCliProfile, roots: tuple[Path, ...], needle: str) -> list[str]:
    found = []
    for base in (profile.root, *roots):
        for path in base.rglob("*"):
            if path.is_file() and not path.is_symlink() and needle.encode() in path.read_bytes():
                found.append(str(path))
    return found


def schemas(_args) -> None:
    """Every schema the Generic import sends, from the offline stand-in import, then the real CLI with network denied:
    an invalid schema fails at startup, a valid one reaches `system/init` and only retries the network."""
    from tests.providers.claude_relay import audit, relay_import
    root = fresh_root("schemas")
    _fixture, result, directory = asyncio.run(relay_import(root))
    found = {}
    for args in audit(directory):
        if args[:1] == ["-p"]:
            schema = args[args.index("--json-schema") + 1]
            found.setdefault(schema, 0)
            found[schema] += 1
    slot = claude_slot(DATA)
    profile = slot.profile
    profile.prepare()
    operations = root / "cli-operations"
    operations.mkdir(mode=0o700)
    checked = []
    for schema, uses in found.items():
        cancel = threading.Event()
        lines = []
        runner = ProcessRunner(profile.executable, launch=functools.partial(profile.launch, network=False))
        args = profile.structured_arguments(schema, MODEL, EFFORT)
        files = OperationFiles(operations)
        stderr = b""
        with files.open():
            try:
                runner.run(files, args, data=b"Synthetic schema check.", deadline=time.monotonic() + 6, cancel=cancel,
                           on_line=lines.append)
            except ProcessExit as error:
                stderr = error.stderr
            except SpikeError:
                pass
        init = any(b'"subtype":"init"' in line.replace(b" ", b"") for line in lines)
        checked.append({"schemaSha256": sha(schema.encode()), "bytes": len(schema.encode()), "uses": uses,
                        "init": init, "schemaError": b"not a valid JSON Schema" in stderr,
                        "stderr": stderr.decode("utf-8", "replace")[:300]})
    profile.wipe()
    write("schemas.json", {"at": now(), "root": str(root), "importState": result.state, "calls": sum(found.values()),
                           "distinctSchemas": len(found), "accepted": sum(item["init"] and not item["schemaError"]
                                                                          for item in checked),
                           "network": "denied for every real CLI run", "checks": checked})


def canary(args) -> None:
    """MP05-1: the synthetic structured task through the launcher's Claude provider, as the app runs it."""
    run_id = "MP05-1b" if args.retry else "MP05-1"
    retry = {"retryOf": "MP05-1", "instruction": args.retry} if args.retry else {}
    slot = claude_slot(DATA)
    provider, profile = slot.provider, slot.profile
    root = fresh_root("canary")
    operations = root / "operations"
    operations.mkdir(mode=0o700)
    mark = "FOLDCV-CANARY-" + secrets.token_hex(8)
    prompt = (f"Reference {mark}. This is a synthetic connectivity check with no personal data. Return answer set to "
              "the word ready, count set to 3 and items set to alpha, beta and gamma in that order.")
    request = ContentInput(prompt, Synthetic, GenerationPolicy(MODEL, timeout_seconds=120, allow_repair=False,
                                                               reasoning_effort=EFFORT))
    charge({"id": run_id, "slice": "MP05", "model": MODEL, "effort": EFFORT, "allowRepair": False,
            "path": "ClaudeCliProvider.generate from the launcher's Claude slot", **retry, "status": "dispatched",
            "startedAt": now()}, after="MP00-1")
    started, code, result, refused = time.monotonic(), None, None, Refused()
    with OperationFiles(operations).open() as files:
        try:
            result = provider.generate(request, files, threading.Event())
        except ContentFailure as error:
            code = error.code
    elapsed = round(time.monotonic() - started, 2)
    passed = result is not None and result.cleanup_verified is True
    settle(run_id, status="completed" if passed else "failed", finishedAt=now(), elapsedSeconds=elapsed,
           **({"code": code} if code else {}))
    write(("live-1b.json" if args.retry else "live-1.json"), {
        "at": now(), "passed": passed, "code": code, "elapsedSeconds": elapsed, "executable": str(profile.executable),
        "value": result.value.model_dump() if result else None,
        "matchesExpected": bool(result) and result.value.model_dump() == EXPECTED,
        "cliVersion": result.cli_version if result else None, "effort": result.reasoning_effort if result else None,
        "attempts": result.logical_attempts if result else None, "refusedEvents": dict(refused.kinds),
        "usage": result.usage.__dict__ if result else None, "cleanupVerified": result.cleanup_verified if result else None,
        "profileFiles": sorted(path.name for path in profile.config_dir.iterdir()),
        "canaryHits": scan(profile, (operations,), mark)})


async def run_import(args) -> None:
    """MP05-2: CV-B through the app's routes with Claude active, the bundled Generic template and rewriting on."""
    import httpx
    from packages.resume_core.project_repository import decode_project
    from packages.resume_core.template_import import cleanup_verified, spent_calls
    from resume_api.app import create_app
    from resume_api.providers.registry import ProviderRegistry

    source = Path(args.source).read_bytes()
    if sha(source) != CV_B:
        raise SystemExit("not CV-B")
    root = fresh_root("import")
    dist = root / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("MP05")
    origin, secret = "http://127.0.0.1:39305", secrets.token_urlsafe(32)
    slot, refused = claude_slot(DATA, root / "operations"), Refused()
    wrapped = create_app(origin=origin, secret=secret, temp_root=root / "operations", dist=dist, data_root=root / "data",
                         template_import_call_cap=60, provider_registry=ProviderRegistry(frozenset({"claude_cli"})),
                         provider_slots={"claude_cli": slot})
    app = wrapped.app
    steps = {}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url=origin,
                                     headers={"Origin": origin}, timeout=120) as client:
            assert (await client.post("/v1/session/exchange", json={"secret": secret})).status_code == 200
            assert (await client.post("/v1/host/select-provider", json={"provider": "claude_cli"})).json()["provider"] == "claude_cli"
            status = (await client.post("/v1/host/status", json={})).json()
            if status["state"] != "connected" or MODEL not in status["models"]:
                raise SystemExit("Claude is not connected: " + status["state"])
            selected = await client.post("/v1/host/select", json={"model": MODEL})
            assert selected.status_code == 200, selected.text
            created = await client.post("/v1/rich/projects/template-input",
                                        files={"file": ("CV-B.pdf", source, "application/pdf")})
            assert created.status_code == 201, created.text[:300]
            workspace = created.json()["workspace"]
            project, warnings = workspace["projectId"], workspace["preDraft"]["warnings"]
            if "NO_USABLE_TEXT" in warnings:
                raise SystemExit("no usable text; nothing dispatched")
            run_id = "MP05-2b" if args.retry else "MP05-2"
            retry = {"retryOf": "MP05-2", "instruction": args.retry} if args.retry else {}
            charge({"id": run_id, "slice": "MP05", "model": MODEL, "effort": EFFORT, "allowRepair": False,
                    "path": "app routes: template-input upload, /v2 import task, Claude active",
                    "source": "CV-B", "sourceSha256": CV_B, "template": "bundled Generic", "rewrite": True,
                    "root": root.name, **retry, "status": "dispatched", "startedAt": now()}, after="MP05-1")
            began = time.monotonic()
            started = await client.post("/v2/projects/" + project + "/import",
                                        json={"kind": "start", "clientRequestId": "mp05-import", "allowTextRewrite": True})
            assert started.status_code == 202, started.text[:300]
            task = started.json()
            runner = app.state.projects.imports.runners.get(task["id"])
            if runner is not None:
                await runner
            steps["importSeconds"] = round(time.monotonic() - began, 1)
            listed = (await client.get("/v2/projects/" + project + "/tasks")).json()["tasks"]
            final = next(value for value in listed if value["id"] == task["id"])
            directory = app.state.projects.repository.open(project).directory
            saved = decode_project(directory, (directory / "workspace.json").read_bytes(), history=True)
            owner = saved.project or saved.pre_draft
            [operation] = owner.template_operations
            published = operation.state == "published" and saved.project is not None
            codes = Counter(attempt.error_code for attempt in operation.attempts if attempt.error_code)
            # Source fallbacks also publish; the proof needs every model reply accepted.
            passed = published and not codes
            if saved.project is not None:
                began = time.monotonic()
                opened = (await client.post("/v2/projects/" + project + "/open", json={})).json()
                exported = await client.post("/v2/projects/" + project + "/export", json={
                    "schemaVersion": 1, "editorToken": opened["editorToken"], "snapshot": opened["response"]["snapshot"]})
                steps["exportSeconds"] = round(time.monotonic() - began, 1)
                steps["exportStatus"] = exported.status_code
                if exported.status_code == 200:
                    (root / "CV-B.docx").write_bytes(exported.content)
            settle(run_id, status="completed" if passed else "failed", finishedAt=now(),
                   elapsedSeconds=steps["importSeconds"], calls=spent_calls(operation),
                   **({"code": codes.most_common(1)[0][0]} if codes else {}))
            if passed and args.assistant:
                await run_assistant(client, project, refused)
    seconds = []
    for attempt in operation.attempts:
        if attempt.dispatched_at and attempt.returned_at:
            seconds.append(round((datetime.fromisoformat(attempt.returned_at)
                                  - datetime.fromisoformat(attempt.dispatched_at)).total_seconds(), 1))
    usage = Counter()
    for attempt in operation.attempts:
        for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
            usage[key] += getattr(attempt.usage, key) or 0
    write("live-2b.json" if args.retry else "live-2.json", {
        "at": now(), "passed": passed, "published": published, "task": {key: final.get(key) for key in ("state", "stage", "error")},
        "operationState": operation.state, **steps, "calls": spent_calls(operation),
        "cleanupVerified": cleanup_verified(operation),
        "tasks": dict(Counter(task.state for task in operation.tasks)),
        "taskKinds": dict(Counter(task.kind for task in operation.tasks)),
        "attemptSlots": dict(Counter(attempt.slot for attempt in operation.attempts)),
        "outcomes": dict(Counter(attempt.outcome or "none" for attempt in operation.attempts)),
        "codes": dict(codes), "refusedEvents": dict(refused.kinds),
        "efforts": dict(Counter(attempt.model.effort for attempt in operation.attempts)),
        "callSeconds": {"count": len(seconds), "max": max(seconds, default=None),
                        "median": sorted(seconds)[len(seconds) // 2] if seconds else None, "total": round(sum(seconds), 1)},
        "usage": dict(usage), "issues": sum(len(task.issue_ids) for task in operation.tasks),
        "profileFiles": sorted(path.name for path in slot.profile.config_dir.iterdir())})
    slot.profile.wipe()


async def run_assistant(client, project, refused) -> None:
    """MP06a-1: one read-only assistant run on the imported project through the app's routes, Claude active."""
    from packages.resume_core.models.assistant import TERMINAL
    base = "/v2/projects/" + project + "/assistant"
    current = (await client.get("/v1/settings/assistant")).json()
    saved = await client.put("/v1/settings/assistant", json={"expectedRevision": current["revision"], "enabled": True,
                                                             "selectedAgentModel": MODEL, "reasoningEffort": None})
    assert saved.status_code == 200, saved.text[:300]
    capabilities = (await client.get(base + "/capabilities")).json()
    if not capabilities["ready"]:
        raise SystemExit("assistant not ready: " + json.dumps(capabilities.get("unavailable")))
    conversation = (await client.post(base + "/conversations")).json()["id"]
    charge({"id": "MP06a-1", "slice": "MP06a", "model": MODEL, "effort": EFFORT, "allowRepair": False,
            "path": "assistant run through the app routes on the MP05 import, Claude active, read-only",
            "status": "dispatched", "startedAt": now()}, after="MP05-2")
    began, after, kinds, tools = time.monotonic(), 0, Counter(), Counter()
    started = await client.post(base + "/conversations/" + conversation + "/runs", json={
        "clientRequestId": "mp06a-1", "message": ASSISTANT_PROMPT, "allowEdits": False, "allowWeb": False})
    assert started.status_code == 201, started.text[:300]
    run = started.json()
    while True:
        reply = (await client.get(base + "/runs/" + run["id"] + "/events/" + str(after))).json()
        for event in reply["events"]:
            kinds[event["type"]] += 1
            if event["type"] == "tool.started":
                tools[event["payload"]["name"]] += 1
        after, run = reply["next"], reply["run"]
        if run["state"] in TERMINAL:
            break
    seconds = round(time.monotonic() - began, 1)
    messages = (await client.get(base + "/conversations/" + conversation + "/messages")).json()["messages"]
    answer = next((item for item in reversed(messages) if item["role"] == "assistant"), None)
    error = (run.get("error") or {}).get("code")
    passed = run["state"] == "completed" and bool(tools) and bool(answer and answer["text"].strip())
    settle("MP06a-1", status="completed" if passed else "failed", finishedAt=now(), elapsedSeconds=seconds,
           **({"code": error} if error else {}))
    directory = EVIDENCE.parent / "mp06a"
    directory.mkdir(exist_ok=True)
    value = {"at": now(), "passed": passed, "state": run["state"], "error": error, "seconds": seconds,
             "events": dict(kinds), "tools": dict(tools), "usage": run.get("usage"),
             "answerChars": len(answer["text"]) if answer else 0, "refusedEvents": dict(refused.kinds)}
    (directory / "live-1.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schemas")
    canary_run = commands.add_parser("canary")
    canary_run.add_argument("--retry", metavar="INSTRUCTION", help="the user's instruction to repeat the failed MP05-1")
    importing = commands.add_parser("import")
    importing.add_argument("source")
    importing.add_argument("--retry", metavar="INSTRUCTION", help="the user's instruction to repeat the failed MP05-2")
    importing.add_argument("--assistant", action="store_true", help="then MP06a-1 on the imported project")
    args = parser.parse_args()
    if args.command == "import":
        asyncio.run(run_import(args))
    else:
        {"schemas": schemas, "canary": canary}[args.command](args)


if __name__ == "__main__":
    os.umask(0o077)
    main()
