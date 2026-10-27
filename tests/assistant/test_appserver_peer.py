"""The scripted app-server peer that the runtime tests drive keeps RPC ids across fragmented frames."""

import json
import subprocess
import sys

from tests.support.appserver import fake_agent_cli


def test_scripted_peer_preserves_fragmented_rpc_ids_and_real_interrupt_exchange(tmp_path):
    executable = fake_agent_cli(tmp_path / "peer", [
        {"method": "initialize", "send": [{"id": "$id", "result": {"userAgent": "fixture"}}]},
        {"method": "initialized"},
        {"method": "thread/start", "send": [{"id": "$id", "result": {"thread": {"id": "thread_1"}}}]},
        {"method": "turn/start", "send": [{"id": "$id", "result": {"turn": {"id": "turn_1", "status": "inProgress"}}},
            {"method": "turn/started", "params": {"threadId": "thread_1", "turn": {"id": "turn_1", "status": "inProgress"}}}]},
        {"method": "turn/interrupt", "params": {"threadId": "thread_1", "turnId": "turn_1"},
            "send": [{"id": "$id", "result": {}}, {"method": "turn/completed", "params": {
                "threadId": "thread_1", "turn": {"id": "turn_1", "status": "interrupted"}}}]},
    ], fragment_bytes=1)
    frames = [{"id": 7, "method": "initialize", "params": {}}, {"method": "initialized"},
        {"id": 11, "method": "thread/start", "params": {}}, {"id": 12, "method": "turn/start", "params": {}},
        {"id": 13, "method": "turn/interrupt", "params": {"threadId": "thread_1", "turnId": "turn_1"}}]
    completed = subprocess.run([sys.executable, str(executable), "app-server"],
        input="".join(json.dumps(frame) + "\n" for frame in frames), capture_output=True, text=True, timeout=5)
    assert completed.returncode == 0 and completed.stderr == ""
    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [frame["id"] for frame in replies if "id" in frame] == [7, 11, 12, 13]
    assert replies[-1]["params"]["turn"]["status"] == "interrupted"
