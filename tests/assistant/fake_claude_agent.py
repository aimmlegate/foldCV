#!/usr/bin/env python3
"""Offline Claude Code stand-in for assistant runs: the stream-json envelopes of MP00 and the probe of MP06a, and a
real MCP handshake and tool call against the run's FoldCV listener. All input is synthetic."""

import json
import os
from pathlib import Path
import signal
import sys
import time
import urllib.error
import urllib.request

base = Path(__file__).resolve().parent
case = json.loads((base / "fixture.json").read_text())["case"]
args = sys.argv[1:]
runs = len((base / "audit.jsonl").read_text().splitlines()) + 1 if (base / "audit.jsonl").exists() else 1
if case == "renewal":
    case = "auth" if runs == 1 else "complete"
with (base / "audit.jsonl").open("a") as audit:
    audit.write(json.dumps({"args": args, "environment": sorted(os.environ)}) + "\n")


def emit(event):
    os.write(1, (json.dumps(event, ensure_ascii=False) + "\n").encode())


def option(name):
    return args[args.index(name) + 1] if name in args else None


config = json.loads(Path(option("--mcp-config")).read_text())["mcpServers"]["foldcv"]
token = config["headers"]["Authorization"].replace("${FOLDCV_AGENT_MCP_CAPABILITY}",
                                                   os.environ.get("FOLDCV_AGENT_MCP_CAPABILITY", ""))
if case == "wrong_token":
    token = "Bearer wrong"
version = None


def rpc(method, params, identifier=1):
    headers = {"Authorization": token, "Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if version:
        headers["MCP-Protocol-Version"] = version
    request = urllib.request.Request(config["url"], method="POST", headers=headers, data=json.dumps(
        {"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}).encode())
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())["result"]


try:
    initialized = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "stand-in", "version": "1"}})
    version = initialized["protocolVersion"]
    listed = [tool["name"] for tool in rpc("tools/list", {}, 2)["tools"]]
    status = "connected"
except (urllib.error.URLError, KeyError, ValueError):
    listed, status = [], "failed"

prompt = sys.stdin.buffer.read().decode()
(base / "prompt.txt").write_text(prompt)
model = option("--model")
tools = ["mcp__foldcv__" + name for name in listed] + (["Bash"] if case == "init_extra" else [])
emit({"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": "s-1", "tools": tools,
      "mcp_servers": [{"name": "foldcv", "status": status, "source": "dynamic"}], "model": model,
      "permissionMode": option("--permission-mode"), "slash_commands": [], "apiKeySource": "none",
      "claude_code_version": "2.1.308", "output_style": "default", "agents": [], "skills": [], "plugins": [],
      "capabilities": ["interrupt_receipt_v1"], "analytics_disabled": True})
emit({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}})
emit({"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 64, "estimated_tokens_delta": 64})
usage = {"input_tokens": 100, "cache_creation_input_tokens": 20, "cache_read_input_tokens": 30, "output_tokens": 40}


def result(**fields):
    emit({"type": "result", "subtype": "success", "is_error": False, "num_turns": 2, "session_id": "s-1",
          "usage": usage, "permission_denials": [], "result": "", **fields})


def say(text):
    emit({"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "message_start"}})
    emit({"type": "stream_event", "parent_tool_use_id": None, "event": {
        "type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}})
    emit({"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "model": model,
                                                                        "content": [{"type": "text", "text": text}]}})


if case in {"hang", "stubborn"}:
    def interrupted(_number, _frame):
        emit({"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
            {"type": "text", "text": "[Request interrupted by user]"}]}})
        result(subtype="error_during_execution", is_error=True, terminal_reason="aborted_streaming")
        sys.exit(0)
    signal.signal(signal.SIGINT, signal.SIG_IGN if case == "stubborn" else interrupted)
    (base / "ready").touch()
    while True:
        time.sleep(0.01)

notices = {"compact": "compact_boundary", "fallback": "model_fallback", "unknown": "new_notice",
           "permission": "permission_denied"}
if case in notices:
    emit({"type": "system", "subtype": notices[case]})
if case == "subagent":
    emit({"type": "assistant", "parent_tool_use_id": "toolu_0", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "x"}]}})
if case in {"auth", "quota"}:
    kind, text = (("authentication_failed", "Not logged in · Please run /login") if case == "auth"
                  else ("rate_limit", "You've hit your usage limit · resets 5pm"))
    emit({"type": "assistant", "error": kind, "parent_tool_use_id": None, "message": {
        "role": "assistant", "model": "<synthetic>", "content": [{"type": "text", "text": text}]}})
    result(is_error=True, result=text)
    sys.exit(1)
if case == "big":
    say("x" * (70 * 1024))

say("Читаю резюме.")
tool = "Bash" if case == "builtin" else "mcp__foldcv__read_resume"
emit({"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "model": model, "content": [
    {"type": "thinking", "thinking": "Сначала прочитаю резюме.", "signature": "x"},
    {"type": "tool_use", "id": "toolu_1", "name": tool, "input": {}}]}})
called = rpc("tools/call", {"name": tool.removeprefix("mcp__foldcv__"), "arguments": {}}, 3)
emit({"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "toolu_1", "is_error": called.get("isError", False),
     "content": called["content"]}]}})
if case == "max_turns":
    result(subtype="error_max_turns", is_error=True)
    sys.exit(1)
say("Готово: резюме прочитано.")
if case == "denied":
    result(result="Готово: резюме прочитано.", permission_denials=[{"tool_name": "Bash", "tool_use_id": "t-9"}])
else:
    result(result="Готово: резюме прочитано.", **({"usage": None} if case == "no_usage" else {}))
