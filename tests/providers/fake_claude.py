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
    audit.write(json.dumps({"generation": generation, "args": args, "config": os.environ.get("CLAUDE_CONFIG_DIR"),
                            "uncached": os.environ.get("DISABLE_PROMPT_CACHING")}) + "\n")
# A sign-in leaves `signed-in` with the account's email, if the fixture names one; a sign-out leaves `signed-out`.
signed_in, signed_out_marker = base / "signed-in", base / "signed-out"
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
        sys.stdout.write("Opening browser to sign in…\nIf the browser didn't open, visit: https://claude.com/cai/oauth/"
                         "authorize?code=true&state=synthetic-state\nPaste code here if prompted > ")
        sys.stdout.flush()
        if sys.stdin.readline().strip() != "synthetic-code":
            print("Login failed: invalid code")
            sys.exit(1)
    signed_in.write_text(config.get("login_email", ""))
    signed_out_marker.unlink(missing_ok=True)
    print("Login successful.")
    sys.exit(0)
if args == ["auth", "--help"]:
    print("Usage: claude auth [options] [command]\n\nManage authentication\n\nCommands:\n"
          "  login [options]   Sign in to your Anthropic account\n"
          + ("" if case == "no_logout" else "  logout            Log out from your Anthropic account\n")
          + "  status [options]  Show authentication status")
    sys.exit(0)
if args == ["auth", "logout"]:
    if case == "logout_fails":
        print("Failed to log out: synthetic keychain error", file=sys.stderr)
        sys.exit(1)
    if case == "slow_logout":
        (base / "logout_ready").touch()
        for _ in range(1000):
            if (base / "logout_release").exists():
                break
            time.sleep(0.01)
    if case != "logout_ignored":
        signed_in.unlink(missing_ok=True)
        signed_out_marker.touch()
    print("Successfully logged out from your Anthropic account.")
    sys.exit(0)
if args == ["auth", "status", "--json"]:
    signed_out = (case in {"logged_out", "login_code"} and not signed_in.exists()) or signed_out_marker.exists()
    status = {"loggedIn": not signed_out and case != "api_key", "authMethod": "claude.ai",
              "apiProvider": "firstParty", "configDirectory": os.environ.get("CLAUDE_CONFIG_DIR", "/fixture"),
              "subscriptionType": config.get("subscription", "max"),
              "email": (signed_in.read_text() if signed_in.exists() else "") or config.get("email", "fictional@example.invalid"),
              "orgName": config.get("org", "Fictional Team")}
    if signed_out:
        status.update(authMethod="none", subscriptionType=None, email=None, orgName=None)
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
    init["plugins"] = [{"name": "other", "path": "/plugins/other", "source": "other@market"}]
if case == "init_key":
    init["apiKeySource"] = "ANTHROPIC_API_KEY"
if case == "early_notice":
    emit({"type": "system", "subtype": "new_notice"})
emit(init)
if case == "second_init":
    emit(init)
if case == "hang":
    (base / "ready").touch()
    while True:
        time.sleep(0.01)
if case == "compact":
    emit({"type": "system", "subtype": "compact_boundary"})
# The cost details 2.1.308 sends beside the counts (T0.1); `detail` sends them malformed.
detail = config.get("detail", "valid")
windows = {"valid": {"five_hour": {"utilization": 0.25, "resetsAt": 1800000000},
                     "seven_day": {"utilization": 0.05, "resetsAt": 1800500000}},
           "malformed": {"five_hour": {"utilization": "high", "resetsAt": -1}, "seven_day": [0.05]}}.get(detail)
emit({"type": "system", "subtype": "api_retry", "attempt": 1, "error": "overloaded"} if case == "retry" else
     {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed",
                                                      **({"unifiedWindows": windows} if windows else {})}})
emit({"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 64, "estimated_tokens_delta": 64})
if case == "unknown_notice":
    for _ in range(2):
        emit({"type": "system", "subtype": "new_notice", "detail": "synthetic-secret"})
        emit({"type": "new_event", "detail": "synthetic-secret"})
usage = {"input_tokens": 12, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 5, "output_tokens": 7}
costs = {"num_turns": 2, "total_cost_usd": 0.01}
if detail == "valid":
    usage.update(cache_creation={"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 3},
                 output_tokens_details={"thinking_tokens": 2})
if detail == "malformed":
    usage.update(cache_creation={"ephemeral_5m_input_tokens": None, "ephemeral_1h_input_tokens": "3"},
                 output_tokens_details=[2])
    costs = {"num_turns": True, "total_cost_usd": "0.01"}


def result(**fields):
    emit({"type": "result", "subtype": "success", "is_error": False, "session_id": "s-1",
          "usage": usage, "permission_denials": [], **costs, **fields})


errors = {"auth": ("authentication_failed", "Not logged in · Please run /login"),
          "rate_limit": ("rate_limit", "Rate limited, try again"),
          "quota": ("rate_limit", "You've hit your usage limit · resets 5pm"),
          "model": ("model_not_found", "There's an issue with the selected model"),
          "billing": ("billing_error", "Credit balance is too low"),
          "overloaded": ("overloaded", "API Error: Overloaded"),
          "server_error": ("server_error", "API Error: Internal server error")}
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
    extra = {"new_block": [{"type": "new_block"}], "server_tool": [{"type": "server_tool_use"}]}.get(case, [])
    emit({"type": "assistant", "parent_tool_use_id": None,
          "message": {"id": "msg-1", "role": "assistant", "model": model, "content": [
              *extra, {"type": "thinking", "thinking": "", "signature": "x"},
              {"type": "tool_use", "id": "t-1", "name": tool, "input": value}]}})
    emit({"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t-1", "content": "Structured output provided successfully"}]}})
    if case == "subagent":
        emit({"type": "assistant", "parent_tool_use_id": "t-1",
              "message": {"role": "assistant", "content": [{"type": "text", "text": "x"}]}})
    if case == "incomplete":
        sys.exit(0)
    result(result="", structured_output=None if case == "no_output" else value)
    if case == "late_notice":
        emit({"type": "system", "subtype": "new_notice"})
else:
    text = config.get("text", "plain answer")
    emit({"type": "assistant", "parent_tool_use_id": None,
          "message": {"id": "msg-1", "role": "assistant", "model": model, "content": [{"type": "text", "text": text}]}})
    result(result=text)
