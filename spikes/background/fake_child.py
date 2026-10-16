"""A pipe-only synthetic child; no runtime imports, credentials or network."""

import json
import sys

print(json.dumps({"type": "ready", "protocol": "NB00a-pipe-v1"}), flush=True)
for line in sys.stdin:
    command = json.loads(line)
    if command == {"command": "stop"}:
        print('{"type":"stopped"}', flush=True)
        break
    if command == {"command": "probe"}:
        print('{"type":"alive"}', flush=True)
    else:
        raise SystemExit("unsupported synthetic command")
