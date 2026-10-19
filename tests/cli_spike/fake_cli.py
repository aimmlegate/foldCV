#!/usr/bin/env python3
"""Offline executable fixture. Its files and all input are synthetic."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


base = Path(__file__).resolve().parent
config = json.loads((base / "fixture.json").read_text())
case = config.get("case", "valid")
args = sys.argv[1:]
generation = bool(args and args[0] == "exec" and "--help" not in args)
with (base / "audit.jsonl").open("a") as audit:
    audit.write(json.dumps({"generation": generation, "args": args}) + "\n")


def emit(event):
    os.write(1, (json.dumps(event, ensure_ascii=False) + "\n").encode())


def wait_release():
    (base / "ready").touch()
    while not (base / "release").exists():
        time.sleep(0.005)


if args == ["--version"]:
    if case == "slow_probe":
        wait_release()
    print(config.get("version", "codex-cli 0.162.0-alpha.2-fixture"))
    sys.exit(0)
if args == ["exec", "--help"]:
    print("--ephemeral --ignore-user-config --ignore-rules --json --output-schema --skip-git-repo-check" if case != "bad_help" else "unsupported")
    sys.exit(0)
if args == ["login", "status"]:
    if case == "missing_login":
        print("Not logged in", file=sys.stderr)
        sys.exit(1)
    if case == "login_failure":
        print("synthetic-secret unknown failure", file=sys.stderr)
        sys.exit(7)
    print("Logged in using an API key: synthetic-secret" if case == "api_key" else "Logged in using ChatGPT", file=sys.stderr)
    sys.exit(0)
if args and args[0] == "app-server":
    if config.get("agent"):
        from fake_agent import serve
        serve(config, base)
        sys.exit(0)
    for raw in sys.stdin:
        event = json.loads(raw)
        method = event["method"]
        if method == "initialize":
            if case == "metadata_error":
                emit({"id": event["id"], "error": {"message": "synthetic-secret " + config["prompt"]}})
                continue
            emit({"id": event["id"], "result": {"userAgent": "synthetic/fixture"}})
            if case == "metadata_initial_only":
                sys.exit(0)
            if case == "metadata_tool":
                emit({"method": "item/started", "params": {"type": "command_execution"}})
            emit({"method": "remoteControl/status/changed", "params": {"status": "disabled"}})
        elif method == "initialized":
            continue
        elif method == "account/read":
            assert event["params"] == {"refreshToken": False}
            emit({"method": "account/updated", "params": {"authMode": "apikey" if case == "metadata_api_key" else "chatgpt"}})
            emit({"id": event["id"], "result": {"account": {"type": "chatgpt", "email": "fictional@example.invalid"}}})
            if case == "metadata_account_only":
                sys.exit(0)
        elif method == "model/list":
            emit({"id": event["id"], "result": {"data": [{"model": "gpt-6-luna", "supportedReasoningEfforts": [{"reasoningEffort": e} for e in config.get("efforts", ["low", "medium", "high"])], "defaultReasoningEffort": "medium"}], "nextCursor": None}})
            if case == "metadata_duplicate_catalog":
                emit({"id": event["id"], "result": {"data": [{"model": "gpt-6-luna"}], "nextCursor": None}})
        else:
            sys.exit(92)
    sys.exit(0)
if not generation:
    sys.exit(90)

required = ["--strict-config", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check", "--json"]
assert all(flag in args for flag in required)
assert args[-1] == "-"
assert args[args.index("--sandbox") + 1] == "read-only"
settings = [args[i + 1] for i, arg in enumerate(args) if arg == "--config"]
for value in ['forced_login_method="chatgpt"', 'model_provider="openai"', 'history.persistence="none"', 'web_search="disabled"', 'project_doc_max_bytes=0', 'mcp_servers={}']:
    assert value in settings
for name in ["shell_tool", "unified_exec", "browser_use", "computer_use", "apps", "plugins", "hooks", "memories", "multi_agent", "image_generation", "goals", "daemon_auto_start"]:
    assert "features." + name + "=false" in settings
assert not any(key.startswith(("OPENAI_", "CODEX_", "T3CODE_", "PYTHON", "HTTP_PROXY", "HTTPS_PROXY")) for key in os.environ)
for key in ["TMPDIR", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"]:
    assert Path(os.environ[key]).is_relative_to(Path.cwd())
if config.get("plain_text"):
    assert "--output-schema" not in args and not Path("schema.json").exists()
    schema = {}
else:
    schema = json.loads(Path(args[args.index("--output-schema") + 1]).read_text())
    assert schema["required"] == config.get("schema_required", ["summary"]) and schema["additionalProperties"] is False


def schema_error(node):
    if "oneOf" in node or "discriminator" in node:
        return "Unsupported exclusive union"
    if node.get("type") == "object":
        if node.get("additionalProperties") is not False:
            return "Object must be closed"
        missing = set(node.get("properties", {})) - set(node.get("required", []))
        if missing:
            return "Missing required property: " + sorted(missing)[0]
    children = list(node.get("properties", {}).values()) + list(node.get("$defs", {}).values())
    children += node.get("anyOf", [])
    if isinstance(node.get("items"), dict):
        children.append(node["items"])
    return next((error for child in children if (error := schema_error(child))), None)


problem = schema_error(schema)
if problem or case == "schema_rejected":
    emit({"type": "error", "message": json.dumps({"type": "error", "status": 400,
          "error": {"type": "invalid_request_error", "code": "invalid_json_schema",
                    "message": problem or "synthetic-secret schema rejected", "param": "text.format.schema"}})})
    sys.exit(1)
prompt = sys.stdin.read()
attempt = sum(json.loads(line).get("generation", False) for line in (base / "audit.jsonl").read_text().splitlines())
if prompt != config["prompt"]:
    assert prompt.startswith(config["prompt"] + "\n\n")
    assert "invalid JSON or did not match the schema" in prompt
assert prompt not in json.dumps(args)
with (base / "audit.jsonl").open("a") as audit:
    audit.write(json.dumps({"stdin_match": True, "restrictions_checked": True}) + "\n")
# Deliberate CLI content write tests operation cleanup, not real CLI retention.
Path("synthetic-content.txt").write_text(prompt)

if case == "tree":
    child_code = "import signal,time,sys; from pathlib import Path; p=Path(sys.argv[1]); signal.signal(signal.SIGTERM,lambda *_:(p/'term_seen').touch()); (p/'child_ready').touch(); time.sleep(30)"
    child = subprocess.Popen([sys.executable, "-c", child_code, str(base)])
    (base / "child_pid").write_text(str(child.pid))
    while not (base / "child_ready").exists():
        time.sleep(0.005)
    wait_release()
if case == "fork_race":
    worker_code = (
        "import signal,subprocess,sys,time; from pathlib import Path; "
        "p=Path(sys.argv[1]); signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "(p/'worker_ready').touch(); "
        "\nwhile not (p/'fork_now').exists(): time.sleep(0.005)\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'], "
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        "(p/'forked_pid').write_text(str(child.pid)); time.sleep(30)"
    )
    worker = subprocess.Popen([sys.executable, "-c", worker_code, str(base)],
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    (base / "leader_pid").write_text(str(os.getpid()))
    (base / "worker_pid").write_text(str(worker.pid))
    while not (base / "worker_ready").exists():
        time.sleep(0.005)
if case == "hang":
    wait_release()
if case in ("quota", "model_denied", "expired"):
    message = {"quota": "Quota exhausted", "model_denied": "Model not supported", "expired": "Authentication token expired"}[case]
    code = {"quota": "rate_limit_exceeded", "model_denied": "model_not_supported", "expired": "authentication_error"}[case]
    emit({"type": "error", "error": {"code": code, "message": message + " " + prompt + " synthetic-secret"}})
    sys.exit(1)
if case == "bad_error_code":
    emit({"type": "error", "error": {"code": ["rate_limit_exceeded"], "message": prompt}})
    sys.exit(1)
if case == "nonzero":
    print(prompt + " synthetic-secret", file=sys.stderr)
    sys.exit(7)
if case in ("excessive", "excessive_stderr"):
    os.write(1 if case == "excessive" else 2, b"x" * 300000)
    sys.exit(0)

events = [json.loads(line) for line in (base / "success.jsonl").read_text().splitlines()]
if "result_text" in config:
    events[2]["item"]["text"] = config["result_text"]
if case == "malformed_event":
    os.write(1, b"{bad json}\n")
    sys.exit(0)
if case == "invalid_utf8":
    os.write(1, b"\xff\n")
    sys.exit(0)
if case == "malformed_result":
    events[2]["item"]["text"] = "{bad json}"
if case == "repair" and attempt == 1:
    events[2]["item"]["text"] = '{"summary":23}'
if case == "repair_second_nonzero" and prompt == config["prompt"]:
    events[2]["item"]["text"] = '{"summary":23}'
if case == "schema":
    events[2]["item"]["text"] = '{"summary":23}'
if case == "extra_field":
    events[2]["item"]["text"] = '{"summary":"synthetic","extra":true}'
if case == "duplicate_field":
    events[2]["item"]["text"] = '{"summary":"a","summary":"b"}'
if case == "nonfinite":
    events[-1]["usage"]["input_tokens"] = float("nan")
if case == "missing_usage":
    events[-1].pop("usage")
if case == "bad_usage":
    events[-1]["usage"]["input_tokens"] = True
if case == "fragmented":
    events[2]["item"]["text"] = '{"summary":"Вымышленный инженер ☃"}'
    events[2]["optional_new_field"] = {"safe": True}
if case == "tool":
    events[2] = {"type": "item.started", "item": {"type": config.get("tool_type", "command_execution"), "command": "synthetic"}}
if case == "incomplete":
    events.pop()
if case == "duplicate_completion":
    events.append(events[-1])
if case == "duplicate_message":
    events.insert(3, events[2])
if case == "intermediate_message":
    events.insert(2, {"type": "item.completed", "item": {
        "id": "synthetic-progress", "type": "agent_message", "text": "Checking synthetic facts."}})
if case in ("startup_warning", "invalid_startup_warning"):
    events.insert(1, {"type": "item.completed", "item": {
        "id": "synthetic-warning", "type": "error", "message":
        "An optional synthetic feature is unavailable." if case == "startup_warning" else 42}})
if case == "intermediate_invalid_final":
    events.insert(2, {"type": "item.completed", "item": {
        "id": "synthetic-progress", "type": "agent_message", "text": '{"summary":"Earlier synthetic response"}'}})
    events[3]["item"]["text"] = '{"summary":42}'
if case == "out_of_order":
    events.reverse()
if case == "unknown_event":
    events[2] = {"type": "unknown.event"}
raw = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events).encode()
if case in ("utf16", "utf32"):
    encoding = "utf-16-le" if case == "utf16" else "utf-32-le"
    raw = b"".join(json.dumps(event, ensure_ascii=False).encode(encoding) + b"\n" for event in events)
if case == "unterminated":
    raw = raw[:-1]
if case == "fragmented":
    for byte in raw:
        os.write(1, bytes([byte]))
else:
    os.write(1, raw)
if case == "late":
    wait_release()
if case == "nonzero_after_complete" or (case == "repair_second_nonzero" and prompt != config["prompt"]):
    sys.exit(7)
