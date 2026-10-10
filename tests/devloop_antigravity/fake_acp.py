#!/usr/bin/env python3
"""Small ACP server used by the adapter tests."""

import json
import os
import sys
import time


SESSION = "146f8836-28e9-49a5-a377-f340949bd7bc"
MODEL = "gemini-3.8-flash-medium"
SCENARIO = os.environ.get("FAKE_ACP_SCENARIO", "success")


def send(value):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", **value}) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    ident = request.get("id")
    if method == "initialize":
        result = {"protocolVersion": 1, "agentInfo": {"name": "antigravity-acp"},
                  "authMethods": [{"id": "oauth-personal"}]}
    elif method == "authenticate":
        result = {}
    elif method == "session/new":
        result = {"sessionId": SESSION, "configOptions": [{"id": "model", "type": "select",
                  "options": [{"value": MODEL}] if SCENARIO != "model_missing" else []}]}
    elif method == "session/set_config_option":
        config_id = request["params"]["configId"]
        value = request["params"]["value"]
        result = {"configOptions": [{"id": config_id, "currentValue": value}]}
    elif method == "session/prompt":
        if SCENARIO == "wire_limit":
            for _ in range(12):
                send({"method": "session/update", "params": {"sessionId": SESSION,
                      "update": {"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "x" * 200_000}}}})
        if SCENARIO == "timeout":
            time.sleep(3)
        if SCENARIO == "eof":
            sys.exit(0)
        if SCENARIO == "duplicate":
            send({"id": ident - 1, "result": {}})
        if SCENARIO == "callback":
            send({"id": 100, "method": "fs/read_text_file", "params": {"path": "/tmp/private"}})
        if SCENARIO == "tool_update":
            send({"method": "session/update", "params": {"sessionId": SESSION,
                  "update": {"sessionUpdate": "tool_call", "title": "Run command"}}})
        if SCENARIO == "quota":
            send({"id": ident, "error": {"code": -32603, "message": "RESOURCE_EXHAUSTED",
                  "data": {"status": "RESOURCE_EXHAUSTED", "retry_after": "600"}}})
            continue
        content = "RESOURCE_EXHAUSTED" if SCENARIO == "quota_text" else "Review looks fine."
        send({"method": "session/update", "params": {"sessionId": SESSION,
              "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": content}}}})
        result = {"stopReason": "end_turn", "usage": {"inputTokens": 12, "outputTokens": 3, "totalTokens": 15}}
    else:
        send({"id": ident, "error": {"code": -32601, "message": "Unknown method"}})
        continue
    send({"id": ident, "result": result})
