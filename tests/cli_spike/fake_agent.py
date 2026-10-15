"""Scripted agent peer sharing the existing synthetic CLI entry point."""

import json
import os
import sys
import time


def serve(config, base):
    steps = iter(config["agent"])
    for raw in sys.stdin:
        request = json.loads(raw)
        step = next(steps)
        assert request.get("method") == step["method"]
        if "params" in step:
            assert request.get("params") == step["params"]
        with (base / "requests.jsonl").open("a") as audit:
            audit.write(json.dumps({"method": request.get("method"), "id": request.get("id")}) + "\n")
        if step.get("ready"):
            (base / step["ready"]).touch()
        if step.get("wait"):
            deadline = time.monotonic() + 5
            while not (base / step["wait"]).exists():
                if time.monotonic() > deadline:
                    raise TimeoutError("fixture wait expired")
                time.sleep(0.005)
        for frame in step.get("send", []):
            frame = {**frame, **({"id": request["id"]} if frame.get("id") == "$id" else {})}
            data = (json.dumps(frame, ensure_ascii=False) + "\n").encode()
            width = max(1, config.get("fragmentBytes", len(data)))
            for start in range(0, len(data), width):
                os.write(1, data[start:start + width])
        if "raw" in step:
            os.write(1, step["raw"].encode())
        if "stderr" in step:
            os.write(2, step["stderr"].encode())
        if "exit" in step:
            sys.exit(step["exit"])
