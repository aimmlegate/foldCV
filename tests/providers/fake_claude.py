#!/usr/bin/env python3
"""Offline Claude Code stand-in that replays the envelopes observed in MP00. All input is synthetic."""

import hashlib
import json
import os
from pathlib import Path
import sys
import time


base = Path(__file__).resolve().parent
config = json.loads((base / "fixture.json").read_text())
case = config.get("case", "valid")
args = sys.argv[1:]
generation = bool(args and args[0] == "-p")
calls = base / "calls"
count = int(calls.read_text()) + 1 if calls.exists() else 1
if generation:
    calls.write_text(str(count))
with (base / "audit.jsonl").open("a") as audit:
    audit.write(json.dumps({"generation": generation, "args": args}) + "\n")
FLAGS = ("--print --output-format --verbose --json-schema --model --effort --restricted --tools "
         "--strict-mcp-config --mcp-config --disable-slash-commands --settings --no-session-persistence "
         "--permission-mode --permission-prompts --system-prompt --allowedTools --include-partial-messages")


def emit(event):
    os.write(1, (json.dumps(event, ensure_ascii=False) + "\n").encode())


def option(name):
    return args[args.index(name) + 1] if name in args else None


if args == ["--version"]:
    print(config.get("version", "2.1.308 (Claude Code)"))
    sys.exit(0)
if args == ["--help"]:
    print(FLAGS if case != "bad_help" else "--print --output-format")
    sys.exit(0)
if args == ["auth", "login", "--claudeai"]:
    if case == "login_code":
        sys.stdout.write("Opening browser to sign in…\nPaste code here if prompted > ")
        sys.stdout.flush()
        if sys.stdin.readline().strip() != "synthetic-code":
            print("Login failed: invalid code")
            sys.exit(1)
    (base / "signed-in").touch()
    print("Login successful.")
    sys.exit(0)
if args == ["auth", "status", "--json"]:
    signed_out = case in {"logged_out", "login_code"} and not (base / "signed-in").exists()
    status = {"loggedIn": not signed_out and case != "api_key", "authMethod": "claude.ai",
              "apiProvider": "firstParty", "configDirectory": os.environ.get("CLAUDE_CONFIG_DIR", "/fixture"),
              "subscriptionType": "max"}
    if signed_out:
        status.update(authMethod="none", subscriptionType=None)
    if case == "api_key":
        status.update(loggedIn=True, authMethod="api_key")
    print(json.dumps(status, indent=2))
    sys.exit(0 if status["loggedIn"] else 1)
if not generation:
    print("error: unknown command", file=sys.stderr)
    sys.exit(2)

prompt = sys.stdin.buffer.read().decode()
(base / f"prompt-{count}.txt").write_text(prompt)
if case == "bad_schema":
    print("Error: --json-schema is not a valid JSON Schema: data/type must be equal to one of the allowed values",
          file=sys.stderr)
    sys.exit(1)
if case == "unknown_option":
    print("error: unknown option '--restricted'", file=sys.stderr)
    sys.exit(1)

model = option("--model")
structured = "--json-schema" in args
init = {"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": "s-1",
        "tools": ["StructuredOutput"] if structured else [], "mcp_servers": [], "model": model,
        "permissionMode": option("--permission-mode"), "slash_commands": [], "apiKeySource": "none",
        "claude_code_version": "2.1.308", "output_style": "default", "agents": ["Explore"], "skills": [],
        "plugins": [], "capabilities": ["interrupt_receipt_v1"], "analytics_disabled": True}
if case == "init_mcp":
    init["mcp_servers"] = [{"name": "other", "status": "connected"}]
if case == "init_model":
    init["model"] = "claude-other"
if case == "init_plugin":
    init["plugins"] = [{"name": "new-builtin", "path": "builtin", "source": "new-builtin@builtin"}]
if case == "init_key":
    init["apiKeySource"] = "ANTHROPIC_API_KEY"
emit(init)
if case == "hang":
    (base / "ready").touch()
    while True:
        time.sleep(0.01)
if case == "compact":
    emit({"type": "system", "subtype": "compact_boundary"})
emit({"type": "system", "subtype": "api_retry", "attempt": 1, "error": "overloaded"} if case == "retry" else
     {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}})
emit({"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 64, "estimated_tokens_delta": 64})
if case == "unknown_notice":
    emit({"type": "system", "subtype": "new_notice"})
usage = {"input_tokens": 12, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 5, "output_tokens": 7}


def result(**fields):
    emit({"type": "result", "subtype": "success", "is_error": False, "num_turns": 2, "session_id": "s-1",
          "usage": usage, "permission_denials": [], "total_cost_usd": 0.01, **fields})


errors = {"auth": ("authentication_failed", "Not logged in · Please run /login"),
          "rate_limit": ("rate_limit", "Rate limited, try again"),
          "quota": ("rate_limit", "You've hit your usage limit · resets 5pm"),
          "model": ("model_not_found", "There's an issue with the selected model"),
          "billing": ("billing_error", "Credit balance is too low")}
if case == "renewal" and count == 1:
    case = "auth"
if case in errors:
    kind, text = errors[case]
    emit({"type": "assistant", "error": kind, "is_api_error_message": True, "parent_tool_use_id": None,
          "message": {"role": "assistant", "model": "<synthetic>", "content": [{"type": "text", "text": text}]}})
    result(is_error=True, result=text, terminal_reason="api_error")
    sys.exit(1)
if case == "max_retries":
    result(subtype="error_max_structured_output_retries", is_error=True, errors=["validation failed"])
    sys.exit(1)
if case == "denied":
    result(permission_denials=[{"tool_name": "Bash", "tool_use_id": "t-9"}],
           structured_output=config["value"], result="")
    sys.exit(0)

value = config["value"]
if case == "relay":
    # The test leaves each request's answer under its prompt's hash, so concurrent processes answer independently.
    value = json.loads((base / "answers" / (hashlib.sha256(prompt.encode()).hexdigest() + ".json")).read_text())
if case == "repair" and count == 1:
    value = config["invalid"]
if structured:
    tool = "Bash" if case == "tool" else "StructuredOutput"
    emit({"type": "assistant", "parent_tool_use_id": None,
          "message": {"role": "assistant", "model": model, "content": [
              {"type": "thinking", "thinking": "", "signature": "x"},
              {"type": "tool_use", "id": "t-1", "name": tool, "input": value}]}})
    emit({"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t-1", "content": "Structured output provided successfully"}]}})
    if case == "subagent":
        emit({"type": "assistant", "parent_tool_use_id": "t-1",
              "message": {"role": "assistant", "content": [{"type": "text", "text": "x"}]}})
    if case == "incomplete":
        sys.exit(0)
    result(result="", structured_output=None if case == "no_output" else value)
else:
    text = config.get("text", "plain answer")
    emit({"type": "assistant", "parent_tool_use_id": None,
          "message": {"role": "assistant", "model": model, "content": [{"type": "text", "text": text}]}})
    result(result=text)
