"""A scripted app-server peer run as a child process; it reads its steps from fixture.json next to it."""

import json
import os
from pathlib import Path
import sys


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
        for frame in step.get("send", []):
            frame = {**frame, **({"id": request["id"]} if frame.get("id") == "$id" else {})}
            data = (json.dumps(frame, ensure_ascii=False) + "\n").encode()
            width = max(1, config.get("fragmentBytes", len(data)))
            for start in range(0, len(data), width):
                os.write(1, data[start:start + width])
        if "stderr" in step:
            os.write(2, step["stderr"].encode())


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    serve(json.loads((here / "fixture.json").read_text()), here)
