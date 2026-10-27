"""MP00 feasibility gates for the Claude Code CLI; at most one live dispatch, recorded before it starts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import functools
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

from resume_api.cli import qualification  # noqa: E402
from resume_api.cli.process_runner import ProcessExit, ProcessRunner  # noqa: E402
from resume_api.cli.profiles import claude  # noqa: E402
from resume_api.lifecycle import OperationFiles, SpikeError  # noqa: E402


DATA = Path.home() / "Library/Application Support/FoldCV"
PROFILE_ROOT = DATA / f"cli-profile-{claude.KIND}"
OPERATIONS = DATA / "claude-mp00-operations"
EVIDENCE = ROOT / "docs/gui/handoffs/MULTI-PROVIDER/mp00"
LEDGER = ROOT / "docs/gui/handoffs/MULTI-PROVIDER/native-attempts.json"
LIVE_MODEL = "claude-sonnet-5-5"
LIVE_EFFORT = "low"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer", "count", "items"],
          "properties": {"answer": {"type": "string"}, "count": {"type": "integer"},
                         "items": {"type": "array", "items": {"type": "string"}}}}
EXPECTED = {"answer": "ready", "count": 3, "items": ["alpha", "beta", "gamma"]}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(name: str, value: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(value, indent=2, ensure_ascii=False)[:6000])


def executable(args) -> Path:
    found = args.executable or shutil.which("claude")
    if not found:
        raise SystemExit("CLI_MISSING")
    return qualification.resolve(Path(found))


def profile(args) -> claude.ClaudeCliProfile:
    value = claude.ClaudeCliProfile(PROFILE_ROOT, executable(args))
    value.prepare()
    return value


def run(value: claude.ClaudeCliProfile, args: tuple[str, ...], *, data: bytes = b"", network: bool,
        timeout: float, cancel_after: float | None = None, interrupt_after: float | None = None,
        canary: str | None = None) -> dict:
    """One sandboxed CLI process under the product runner and process-group cleanup."""
    OPERATIONS.mkdir(parents=True, exist_ok=True, mode=0o700)
    cancel = threading.Event()
    runner = ProcessRunner(value.executable, launch=functools.partial(value.launch, network=network))
    files = OperationFiles(OPERATIONS)
    started = time.monotonic()
    outcome: dict = {"argv": [arg if len(arg) < 400 else f"<{len(arg)} bytes sha256 {sha(arg.encode())}>"
                              for arg in args], "network": network}
    timers = []
    with files.open():
        if cancel_after is not None:
            timers.append(threading.Timer(cancel_after, cancel.set))
        if interrupt_after is not None:
            def interrupt():
                if files.process is not None:
                    os.killpg(files.process.pid, signal.SIGINT)
            timers.append(threading.Timer(interrupt_after, interrupt))
        for timer in timers:
            timer.start()
        try:
            stdout, stderr = runner.run(files, args, data=data, deadline=time.monotonic() + timeout,
                                        cancel=cancel, max_output=4 * 1024 * 1024, max_line=4 * 1024 * 1024)
            outcome["exit"] = 0
        except ProcessExit as error:
            stdout, stderr = error.stdout, error.stderr
            outcome["exit"] = "nonzero"
        except SpikeError as error:
            stdout, stderr = b"", b""
            outcome["exit"] = error.code
        finally:
            for timer in timers:
                timer.cancel()
        outcome["operation"] = str(files.path)
        outcome["operationFiles"] = sorted(str(path.relative_to(files.path)) for path in files.path.rglob("*")
                                           if path.is_file() and path.name not in {".lock", ".owner", ".worker"})
        outcome["operationCanaryHits"] = sorted(
            str(path.relative_to(files.path)) for path in files.path.rglob("*")
            if canary and path.is_file() and not path.is_symlink() and canary.encode() in path.read_bytes())
    outcome["cleanupVerified"] = not files.cleanup_failed and files.process is None
    outcome["seconds"] = round(time.monotonic() - started, 2)
    outcome["stdoutSha256"] = sha(stdout)
    outcome["stderr"] = stderr.decode("utf-8", "replace")[:2000]
    outcome["raw"] = stdout
    outcome["events"] = []
    for raw in stdout.splitlines():
        try:
            outcome["events"].append(json.loads(raw))
        except ValueError:
            outcome["events"].append({"unparsed": raw.decode("utf-8", "replace")[:500]})
    return outcome


def scan(canary: str) -> list[str]:
    """Every file under the profile root and the operations root that holds the canary."""
    needle = canary.encode()
    hits = []
    for base in (PROFILE_ROOT, OPERATIONS):
        for path in base.rglob("*"):
            if path.is_file() and not path.is_symlink() and needle in path.read_bytes():
                hits.append(str(path))
    return hits


def schema_valid(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == set(SCHEMA["required"])
            and isinstance(value["answer"], str) and type(value["count"]) is int
            and isinstance(value["items"], list) and all(isinstance(item, str) for item in value["items"]))


def init_check(init: dict | None, version: str, tools: tuple[str, ...]) -> str:
    try:
        claude.check_init(init or {}, model=LIVE_MODEL, version=version, tools=tools)
        return "pass"
    except claude.ClaudeProfileError as error:
        return error.code


def summary(outcome: dict) -> dict:
    events = outcome.pop("events")
    outcome.pop("raw")
    init = next((event for event in events if event.get("type") == "system" and event.get("subtype") == "init"), None)
    result = next((event for event in reversed(events) if event.get("type") == "result"), None)
    kinds = [f"{event.get('type')}/{event.get('subtype') or ''}".rstrip("/") for event in events]
    tool_uses = [block.get("name") for event in events if event.get("type") == "assistant"
                 for block in (event.get("message") or {}).get("content") or [] if block.get("type") == "tool_use"]
    outcome.update({"eventKinds": kinds, "toolUses": tool_uses, "rawInit": init,
                    "init": {key: init.get(key) for key in (
                        "tools", "mcp_servers", "slash_commands", "skills", "plugins", "agents", "permissionMode",
                        "model", "apiKeySource", "claude_code_version", "capabilities", "analytics_disabled",
                        "product_feedback_disabled", "output_style")} if init else None,
                    "result": {key: result.get(key) for key in (
                        "subtype", "is_error", "result", "structured_output", "num_turns", "terminal_reason",
                        "permission_denials", "errors", "api_error_status", "usage", "modelUsage",
                        "total_cost_usd", "stop_reason", "duration_ms", "duration_api_ms")} if result else None,
                    "assistantErrors": [event.get("error") for event in events
                                        if event.get("type") == "assistant" and event.get("error")]})
    return outcome


def inspect(args) -> None:
    binary = executable(args)
    signature = qualification.signature(binary)
    value = claude.ClaudeCliProfile(PROFILE_ROOT, binary)
    value.prepare()
    version_out = run(value, ("--version",), network=False, timeout=30)
    help_out = run(value, ("--help",), network=False, timeout=30)
    text = help_out["raw"].decode("utf-8", "replace")
    version_text = version_out["raw"].decode("utf-8", "replace").strip()
    version = qualification.Version.parse(version_text)
    status = claude.COMPATIBILITY.status(version)
    hidden = qualification.missing_flags(text, claude.HIDDEN_FLAGS)
    write("inspect.json", {
        "at": now(), "executable": str(binary), "sha256": sha(binary.read_bytes()),
        "signature": {"teamId": signature.team_id, "identifier": signature.identifier,
                      "publisherOk": signature.team_id == claude.TEAM_ID and signature.identifier == claude.IDENTIFIER},
        "version": str(version), "versionText": version_text, "compatibility": status,
        "table": {"floor": claude.COMPATIBILITY.floor, "lastTested": claude.COMPATIBILITY.last_tested,
                  "broken": list(claude.COMPATIBILITY.broken)},
        "missingRequiredFlags": list(qualification.missing_flags(text, claude.REQUIRED_FLAGS)),
        "hiddenFlagsAbsentFromHelp": list(hidden), "helpSha256": sha(text.encode()),
        "sandbox": "network denied for --version and --help",
        "cleanupVerified": version_out["cleanupVerified"] and help_out["cleanupVerified"],
    })


def status(args) -> None:
    value = profile(args)
    outcome = run(value, ("auth", "status", "--json"), network=not args.offline, timeout=30)
    try:
        body = json.loads(outcome["raw"])
    except ValueError:
        body = None
    write(f"status-{args.label}.json", {
        "at": now(), "exit": outcome["exit"], "network": outcome["network"], "status": body,
        "configDirectoryMatches": bool(body) and Path(body.get("configDirectory", "")).resolve() == value.config_dir.resolve(),
        "accepted": bool(body) and body.get("loggedIn") is True and body.get("authMethod") == claude.ACCEPTED_AUTH,
        "profileFiles": sorted(path.name for path in value.config_dir.iterdir()),
        "cleanupVerified": outcome["cleanupVerified"], "stderr": outcome["stderr"],
    })


def login(args) -> None:
    value = profile(args)
    outcome = run(value, ("auth", "login", "--claudeai"), network=True, timeout=args.timeout)
    write("login.json", {"at": now(), "exit": outcome["exit"], "seconds": outcome["seconds"],
                         "output": outcome["raw"].decode("utf-8", "replace")[:1000],
                         "stderr": outcome["stderr"][:500], "cleanupVerified": outcome["cleanupVerified"],
                         "profileFiles": sorted(path.name for path in value.config_dir.iterdir())})


def structured(value: claude.ClaudeCliProfile, canary: str, *, schema: str | None = None) -> tuple[tuple[str, ...], bytes]:
    prompt = (f"Reference {canary}. This is a synthetic connectivity check with no personal data. Return answer "
              "set to the word ready, count set to 3 and items set to alpha, beta and gamma in that order.")
    return (value.structured_arguments(schema or json.dumps(SCHEMA, separators=(",", ":")), LIVE_MODEL, LIVE_EFFORT),
            prompt.encode())


def offline(args) -> None:
    """Dispatch-free runs of the real CLI: the sandbox denies all network, so nothing reaches the provider."""
    value = profile(args)
    canary = "FOLDCV-CANARY-" + secrets.token_hex(8)
    schema = '{"type":"object","properties":{"a":{"type":"nosuchtype"}}}' if args.case == "invalid_schema" else None
    argv, prompt = structured(value, canary, schema=schema)
    kwargs = {"cancel_after": args.after} if args.case == "cancel" else (
        {"interrupt_after": args.after} if args.case == "interrupt" else {})
    outcome = summary(run(value, argv, data=prompt, network=False, timeout=args.timeout, canary=canary, **kwargs))
    outcome["initCheck"] = init_check(outcome.pop("rawInit"), "2.1.308", claude.STRUCTURED_TOOLS)
    before = scan(canary)
    removed = value.wipe()
    write(f"offline-{args.case}.json", {"at": now(), "case": args.case, **outcome, "canaryHitsBeforeWipe": before,
                                       "wiped": removed, "canaryHitsAfterWipe": scan(canary)})


def ledger() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    return {"schemaVersion": 1, "cap": 4, "spent": 0,
            "authorization": {"decision": "D098 item 5, D099 item 20", "recordedAt": "2026-10-24",
                              "text": "Live allowance for Claude: three gate dispatches (MP00 synthetic structured task, "
                                      "MP05 synthetic run, one assistant dispatch) plus one Generic import after the "
                                      "canary passes; every run with allow_repair=False; stop after the first failure.",
                              "unit": "one live application-model dispatch; charged at dispatch, including unknown "
                                      "outcomes (D091)"},
            "attempts": []}


def live(args) -> None:
    value = profile(args)
    book = ledger()
    if book["spent"] >= book["cap"] or any(item["id"] == "MP00-1" for item in book["attempts"]):
        raise SystemExit("allowance for MP00 already used")
    canary = "FOLDCV-CANARY-" + secrets.token_hex(8)
    argv, prompt = structured(value, canary)
    entry = {"id": "MP00-1", "slice": "MP00", "model": LIVE_MODEL, "effort": LIVE_EFFORT, "allowRepair": False,
             "status": "dispatched", "startedAt": now()}
    book["attempts"].append(entry)
    book["spent"] += 1
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(book, indent=1) + "\n", encoding="utf-8")
    outcome = summary(run(value, argv, data=prompt, network=True, timeout=180, canary=canary))
    result = outcome["result"] or {}
    produced = result.get("structured_output")
    checked = init_check(outcome.pop("rawInit"), "2.1.308", claude.STRUCTURED_TOOLS)
    passed = (outcome["exit"] == 0 and result.get("subtype") == "success" and result.get("is_error") is False
              and schema_valid(produced) and set(outcome["toolUses"]) <= {"StructuredOutput"} and checked == "pass")
    before = scan(canary)
    removed = value.wipe()
    entry.update({"status": "completed" if passed else "failed", "finishedAt": now(),
                  "elapsedSeconds": outcome["seconds"], "stdoutSha256": outcome["stdoutSha256"]})
    LEDGER.write_text(json.dumps(book, indent=1) + "\n", encoding="utf-8")
    write("live-1.json", {"at": now(), "passed": passed, "initCheck": checked, "matchesExpected": produced == EXPECTED,
                          "expected": EXPECTED, **outcome,
                          "canaryHitsBeforeWipe": before, "wiped": removed, "canaryHitsAfterWipe": scan(canary)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect")
    state = commands.add_parser("status")
    state.add_argument("--label", default="current")
    state.add_argument("--offline", action="store_true")
    sign = commands.add_parser("login")
    sign.add_argument("--timeout", type=float, default=900)
    off = commands.add_parser("offline")
    off.add_argument("case", choices=("auth_missing", "invalid_schema", "failure", "cancel", "interrupt"))
    off.add_argument("--after", type=float, default=5)
    off.add_argument("--timeout", type=float, default=60)
    commands.add_parser("live")
    args = parser.parse_args()
    {"inspect": inspect, "status": status, "login": login, "offline": offline, "live": live}[args.command](args)


if __name__ == "__main__":
    main()
