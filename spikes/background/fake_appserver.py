"""Registered synthetic pipe peer; never invoke a model, shell or network."""

import json
import fcntl
import os
import signal
import sys
from pathlib import Path


def emit(value):
    if config is not None and "method" in value and "id" not in value:
        value.setdefault("emittedAtMs", 1792212715222)
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()


config_path = Path.cwd() / "fixture.json"
config = json.loads(config_path.read_text()) if config_path.exists() else None
threads = {}
turns = {}

for line in sys.stdin:
    message = json.loads(line)
    method, params = message.get("method"), message.get("params", {})
    if method == "fixture/emit":
        for frame in params["frames"]:
            emit(frame)
    elif method == "fixture/partial":
        sys.stdout.write(params["raw"])
        sys.stdout.flush()
        sys.exit(0)
    elif method == "fixture/exit":
        sys.exit(params.get("code", 1))
    elif method == "fixture/profile-lock":
        descriptor = os.open(params["path"], os.O_RDWR | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                acquired = False
            emit({"id": message["id"], "result": {"acquired": acquired, "pid": os.getpid()}})
        finally:
            os.close(descriptor)
    elif method == "fixture/fork-child":
        child = os.fork()
        if child == 0:
            for stream in (sys.stdin, sys.stdout, sys.stderr):
                stream.close()
            for descriptor in (0, 1, 2):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            while True:
                signal.pause()
        emit({"id": message["id"], "result": {"childPid": child}})
    elif method == "fixture/owner-and-orphan":
        descriptor = os.open(params["lockPath"], os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        marker = Path(params["markerPath"])
        marker.write_text(json.dumps({"schemaVersion": 1, "operationsRoot": params["operationsRoot"]}))
        marker.chmod(0o600)
        child = os.fork()
        if child == 0:
            os.close(descriptor)
            for stream in (sys.stdin, sys.stdout, sys.stderr):
                stream.close()
            while True:
                signal.pause()
        emit({"id": message["id"], "result": {"ownerPid": os.getpid(), "childPid": child}})
        os._exit(0)
    elif config is not None:
        if method == "initialized" or method is None:
            continue
        if method == "initialize":
            result = {}
        elif method == "config/read":
            result = config["effectiveConfig"]
        elif method == "model/list":
            result = {"data": [{"model": "gpt-6-luna", "supportedReasoningEfforts": [{"reasoningEffort": "medium"}]}], "nextCursor": None}
        elif method == "thread/start":
            identifier = "thread_" + str(len(threads) + 1)
            threads[identifier] = params
            result = {"thread": {"id": identifier, "ephemeral": True, "path": None}, "model": params["model"], "modelProvider": "openai",
                "approvalPolicy": "never", "approvalsReviewer": "user", "sandbox": {"type": "readOnly", "networkAccess": False},
                "reasoningEffort": "medium", "cwd": params["cwd"], "instructionSources": [], "runtimeWorkspaceRoots": []}
        elif method == "turn/start":
            identifier = "turn_" + params["threadId"]
            turns[params["threadId"]] = identifier
            result = {"turn": {"id": identifier, "status": "inProgress"}}
            emit({"method": "turn/started", "params": {"threadId": params["threadId"], **result}})
        elif method == "turn/interrupt":
            emit({"id": message["id"], "result": {}})
            if config.get("interruptCompletes", True):
                emit({"method": "turn/completed", "params": {"threadId": params["threadId"],
                    "turn": {"id": params["turnId"], "status": "interrupted"}}})
            continue
        else:
            emit({"id": message["id"], "error": {"code": -32601, "message": "Unknown fixture method"}})
            continue
        emit({"id": message["id"], "result": result})
        if method == "initialize":
            emit(config.get("startupFrame", {"method": "remoteControl/status/changed", "params": {"status": "disabled"}}))
        elif method == "turn/start":
            emit({"method": "thread/tokenUsage/updated", "params": {"threadId": params["threadId"],
                "turnId": result["turn"]["id"], "tokenUsage": {"total": {"inputTokens": 1,
                    "cachedInputTokens": 0, "outputTokens": 0, "totalTokens": 1,
                    "cacheWriteInputTokens": 0, "reasoningOutputTokens": 0}}}})
    else:
        emit({"id": message["id"], "result": {"pid": os.getpid(), "echo": params}})
