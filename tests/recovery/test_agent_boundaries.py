"""Exact raw limits and cross-process ownership protect the native boundary."""

import asyncio
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.storage import private_directory
from resume_api.inference_admission import InferenceAdmission, AdmissionBlocked, AdmissionTimeout
from resume_api.profile_ownership import native_profile, recover_profile
from tests.recovery.test_agent_runtime import input_value, script, complete_events, runtime, notification


def widen_fragments(tmp_path):
    path = tmp_path / "peer/fixture.json"
    data = json.loads(path.read_text())
    data["fragmentBytes"] = 65536
    path.write_text(json.dumps(data))


@pytest.mark.parametrize("extra", [0, 1])
@pytest.mark.asyncio
async def test_native_raw_frame_exact_limit_and_one_over_including_ignored_reasoning(tmp_path, extra):
    value = input_value()
    ignored = notification("item/reasoning/textDelta", itemId="reasoning_1", delta="")
    overhead = len(json.dumps(ignored, ensure_ascii=False).encode())
    ignored["params"]["delta"] = "r" * (2 * 1024 * 1024 - overhead + extra)
    steps = script(value, turn_events=[ignored, *complete_events()[:-2]])
    driver = runtime(tmp_path, value, steps)
    widen_fragments(tmp_path)
    result = await driver.run(value, threading.Event(), lambda *_: None)
    if extra:
        assert result.error == "AGENT_OUTPUT_LIMIT" and result.truncated
    else:
        assert result.state == "completed" and result.error is None
    assert "rrrrrrrrrrrr" not in result.text
    assert not any((tmp_path / "operations").iterdir())


def outgoing_bytes(steps):
    identifiers = {"initialize": 0, "model/list": 2, "thread/start": 3, "mcpServerStatus/list": 4, "turn/start": 5}
    total = 0
    for step in steps:
        for item in step.get("send", []):
            message = {**item}
            if message.get("id") == "$id":
                message["id"] = identifiers[step["method"]]
            total += len((json.dumps(message, ensure_ascii=False) + "\n").encode())
    return total


@pytest.mark.parametrize("extra", [0, 1])
@pytest.mark.asyncio
async def test_native_stdout_aggregate_exact_limit_and_one_over_counts_ignored_events(tmp_path, extra):
    value = input_value()
    ignored = [notification("item/reasoning/textDelta", itemId="reasoning_1", delta="") for _ in range(5)]
    steps = script(value, turn_events=[*ignored, *complete_events()[:-2]])
    remaining = 8 * 1024 * 1024 - outgoing_bytes(steps) + extra
    for item in ignored:
        size = min(remaining, 2 * 1024 * 1024 - 1024)
        item["params"]["delta"] = "r" * size
        remaining -= size
    assert remaining == 0 and outgoing_bytes(steps) == 8 * 1024 * 1024 + extra
    driver = runtime(tmp_path, value, steps)
    widen_fragments(tmp_path)
    result = await driver.run(value, threading.Event(), lambda *_: None)
    assert (result.error == "AGENT_OUTPUT_LIMIT") if extra else (result.state == "completed" and result.error is None)
    assert "rrrrrrrrrrrr" not in result.text


@pytest.mark.parametrize("extra", [0, 1])
@pytest.mark.asyncio
async def test_native_stderr_has_an_independent_exact_limit_and_no_raw_diagnostic_leak(tmp_path, extra):
    value = input_value()
    steps = script(value, turn_events=complete_events()[:-2])
    steps[3]["stderr"] = "PRIVATE_CANARY".ljust(256 * 1024 + extra, "x")
    driver = runtime(tmp_path, value, steps)
    widen_fragments(tmp_path)
    result = await driver.run(value, threading.Event(), lambda *_: None)
    assert (result.error == "AGENT_OUTPUT_LIMIT") if extra else (result.state == "completed" and result.error is None)
    assert "PRIVATE_CANARY" not in repr(result)


@pytest.mark.asyncio
async def test_cleanup_failure_blocks_the_permit_before_another_waiter_can_enter(tmp_path):
    permit = InferenceAdmission()
    value = input_value(close_tools=lambda _seconds: (_ for _ in ()).throw(OSError("PRIVATE_CANARY")))
    driver = runtime(tmp_path, value, script(value, turn_events=complete_events()[:-2]), admission=permit)
    result = await driver.run(value, threading.Event(), lambda *_: None)
    assert result.error == "AGENT_CLEANUP_FAILED" and permit.blocked
    assert not permit.acquire(blocking=False)
    with pytest.raises(AdmissionBlocked):
        with permit.hold(threading.Event()):
            pytest.fail("cleanup-blocked permit entered")
    assert "PRIVATE_CANARY" not in repr(result)


def profile(root):
    private_directory(root)
    return SimpleNamespace(root=root, prepare=lambda: None)


def test_profile_ownership_excludes_another_process_and_is_cancellable(tmp_path):
    owned = profile(tmp_path / "native-profile")
    path = owned.root / ".foldcv-inference.lock"
    child = subprocess.Popen([sys.executable, "-c",
        "import fcntl,os,sys,time; fd=os.open(sys.argv[1],os.O_RDWR|os.O_CREAT,0o600); "
        "fcntl.flock(fd,fcntl.LOCK_EX); print('ready',flush=True); time.sleep(10)", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(AdmissionTimeout):
            with native_profile(owned, threading.Event(), deadline=time.monotonic() + 1, blocking=False):
                pytest.fail("foreign profile owner admitted")
    finally:
        child.terminate()
        child.communicate(timeout=2)
    with native_profile(owned, threading.Event(), deadline=time.monotonic() + 1):
        assert path.stat().st_mode & 0o777 == 0o600


def profile_free(owned):
    """Whether an owner without a share key could take the profile right now."""
    try:
        with native_profile(owned, threading.Event(), deadline=time.monotonic() + 1, blocking=False):
            return True
    except AdmissionTimeout:
        return False


def test_calls_under_one_share_key_hold_the_profile_together_and_the_last_one_releases_it(tmp_path):
    # CT10: blocks of one import run at once under the job's permit; another owner still waits for all of them.
    owned, permit = profile(tmp_path / "native-profile"), object()
    together, first_out, second_out = threading.Barrier(2, timeout=2), threading.Event(), threading.Event()
    errors = []
    def call(leave):
        try:
            with native_profile(owned, threading.Event(), deadline=time.monotonic() + 2, share=permit):
                together.wait()
                leave.wait(2)
        except Exception as error:
            errors.append(error)
    threads = [threading.Thread(target=call, args=(event,)) for event in (first_out, second_out)]
    for thread in threads:
        thread.start()
    time.sleep(0.2)
    assert not profile_free(owned)
    first_out.set()
    threads[0].join(2)
    assert not profile_free(owned)
    second_out.set()
    threads[1].join(2)
    assert not errors and profile_free(owned)


def test_another_share_key_waits_for_the_shared_hold(tmp_path):
    owned, inside, leave = profile(tmp_path / "native-profile"), threading.Event(), threading.Event()
    def hold():
        with native_profile(owned, threading.Event(), deadline=time.monotonic() + 2, share="first-import"):
            inside.set()
            leave.wait(2)
    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert inside.wait(2)
        with pytest.raises(AdmissionTimeout):
            with native_profile(owned, threading.Event(), deadline=time.monotonic() + 0.2, share="second-import"):
                pytest.fail("a second import joined the first one's profile hold")
    finally:
        leave.set()
        thread.join(2)
    with native_profile(owned, threading.Event(), deadline=time.monotonic() + 1, share="second-import"):
        pass


def test_a_joiner_takes_the_profile_itself_when_the_first_call_could_not(tmp_path):
    owned, permit = profile(tmp_path / "native-profile"), object()
    path = owned.root / ".foldcv-inference.lock"
    child = subprocess.Popen([sys.executable, "-c",
        "import fcntl,os,sys,time; fd=os.open(sys.argv[1],os.O_RDWR|os.O_CREAT,0o600); "
        "fcntl.flock(fd,fcntl.LOCK_EX); print('ready',flush=True); time.sleep(0.6)", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    outcomes = {}
    def call(name, seconds, delay):
        time.sleep(delay)
        try:
            with native_profile(owned, threading.Event(), deadline=time.monotonic() + seconds, share=permit):
                outcomes[name] = "entered"
        except AdmissionTimeout:
            outcomes[name] = "timeout"
    try:
        assert child.stdout.readline().strip() == "ready"
        threads = [threading.Thread(target=call, args=("first", 0.3, 0)), threading.Thread(target=call, args=("joiner", 3, 0.1))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
    finally:
        child.communicate(timeout=3)
    assert outcomes == {"first": "timeout", "joiner": "entered"}


def test_a_cleanup_failure_inside_a_shared_hold_still_blocks_the_profile(tmp_path):
    owned = profile(tmp_path / "native-profile")
    operations = tmp_path / "operations"
    private_directory(operations)
    with pytest.raises(AgentFailure, match="AGENT_CLEANUP_FAILED"):
        with native_profile(owned, threading.Event(), deadline=time.monotonic() + 1, operations_root=operations, share="import"):
            raise AgentFailure("AGENT_CLEANUP_FAILED")
    with pytest.raises(AdmissionBlocked):
        with native_profile(owned, threading.Event(), deadline=time.monotonic() + 1, share="import"):
            pytest.fail("a blocked profile admitted a shared call")


def test_profile_cleanup_marker_requires_its_own_verified_operation_root(tmp_path):
    owned = profile(tmp_path / "native-profile")
    operations = tmp_path / "operations"
    private_directory(operations)
    with pytest.raises(AgentFailure, match="AGENT_CLEANUP_FAILED"):
        with native_profile(owned, threading.Event(), deadline=time.monotonic() + 1, operations_root=operations):
            raise AgentFailure("AGENT_CLEANUP_FAILED")
    with pytest.raises(AdmissionBlocked):
        with native_profile(owned, threading.Event(), deadline=time.monotonic() + 1):
            pytest.fail("unrecovered profile admitted")
    assert recover_profile(owned, tmp_path / "foreign-root")
    assert not recover_profile(owned, operations)
    with native_profile(owned, threading.Event(), deadline=time.monotonic() + 1):
        pass
