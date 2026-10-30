"""Cross-process ownership of the native profile: exclusive lock, one shared hold for model calls, cleanup markers."""

import fcntl
import os
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from packages.resume_core.assistant_store import AgentFailure
from packages.resume_core.storage import private_directory
from resume_api.inference_admission import AdmissionBlocked, AdmissionCancelled, AdmissionTimeout
from resume_api.profile_ownership import BLOCKED, native_profile, recover_profile


def profile(root):
    private_directory(root)
    return SimpleNamespace(root=root, prepare=lambda: None)


def deadline(seconds=5):
    return time.monotonic() + seconds


def profile_free(owned):
    """Whether an owner without a share key could take the profile right now."""
    try:
        with native_profile(owned, threading.Event(), deadline=deadline(), blocking=False):
            return True
    except AdmissionTimeout:
        return False


class StopWhenWaiting:
    """A cancel event that records the first wait for a busy lock and cancels it at once instead of sleeping."""

    def __init__(self, on_wait=lambda: None):
        self.waited, self.cancelled, self.on_wait = threading.Event(), False, on_wait

    def is_set(self):
        return self.cancelled

    def wait(self, _seconds=None):
        self.waited.set()
        self.on_wait()
        self.cancelled = True
        return True


def test_profile_ownership_excludes_another_process_and_is_cancellable(tmp_path):
    owned = profile(tmp_path / "native-profile")
    path = owned.root / ".foldcv-inference.lock"
    child = subprocess.Popen([sys.executable, "-c",
        "import fcntl,os,sys; fd=os.open(sys.argv[1],os.O_RDWR|os.O_CREAT,0o600); "
        "fcntl.flock(fd,fcntl.LOCK_EX); print('ready',flush=True); sys.stdin.read()", str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(AdmissionTimeout):
            with native_profile(owned, threading.Event(), deadline=deadline(), blocking=False):
                pytest.fail("foreign profile owner admitted")
        cancel = StopWhenWaiting()
        with pytest.raises(AdmissionCancelled):
            with native_profile(owned, cancel, deadline=deadline()):
                pytest.fail("cancelled waiter entered")
        assert cancel.waited.is_set()
    finally:
        child.communicate("", timeout=5)
    with native_profile(owned, threading.Event(), deadline=deadline()):
        assert path.stat().st_mode & 0o777 == 0o600


def test_shared_calls_hold_the_profile_together_and_the_last_one_cleans_and_releases_it(tmp_path):
    # CT10, D121: model calls of any import, rewrite or turn run at once; an exclusive owner waits for all of them.
    owned = profile(tmp_path / "native-profile")
    together, first_out, second_out = threading.Barrier(3, timeout=5), threading.Event(), threading.Event()
    errors, cleaned = [], []

    def call(leave):
        try:
            with native_profile(owned, threading.Event(), deadline=deadline(), shared=True,
                                cleanup=lambda: cleaned.append(profile_free(owned))):
                together.wait()
                leave.wait(5)
        except Exception as error:
            errors.append(error)
    threads = [threading.Thread(target=call, args=(event,)) for event in (first_out, second_out)]
    for thread in threads:
        thread.start()
    together.wait()
    assert not profile_free(owned)
    first_out.set()
    threads[0].join(5)
    assert not profile_free(owned) and cleaned == []
    second_out.set()
    threads[1].join(5)
    # The cleanup ran once, while the lock was still held.
    assert not errors and cleaned == [False] and profile_free(owned)


def test_an_exclusive_owner_waits_for_the_shared_hold(tmp_path):
    owned, inside, leave = profile(tmp_path / "native-profile"), threading.Event(), threading.Event()

    def hold():
        with native_profile(owned, threading.Event(), deadline=deadline(), shared=True):
            inside.set()
            leave.wait(5)
    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert inside.wait(5)
        cancel = StopWhenWaiting()
        with pytest.raises(AdmissionCancelled):
            with native_profile(owned, cancel, deadline=deadline()):
                pytest.fail("an exclusive owner entered beside a model call")
        assert cancel.waited.is_set()
    finally:
        leave.set()
        thread.join(5)
    assert profile_free(owned)


def test_a_joiner_takes_the_profile_itself_when_the_first_call_could_not(tmp_path):
    owned = profile(tmp_path / "native-profile")
    # A separate open file description holds the lock like a foreign owner would.
    foreign = os.open(owned.root / ".foldcv-inference.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(foreign, fcntl.LOCK_EX)
    joined, outcomes = threading.Event(), {}

    class Joiner:
        def is_set(self):
            joined.set()
            return False

        def wait(self, seconds=None):
            time.sleep(min(seconds or 0, 0.025))
            return False

    def give_up():
        # The first call gives up only after the joiner waits on its hold; the foreign owner then leaves.
        assert joined.wait(5)
        fcntl.flock(foreign, fcntl.LOCK_UN)
        os.close(foreign)
    first_cancel = StopWhenWaiting(on_wait=give_up)

    def call(name, cancel):
        try:
            with native_profile(owned, cancel, deadline=deadline(), shared=True):
                outcomes[name] = "entered"
        except (AdmissionCancelled, AdmissionTimeout):
            outcomes[name] = "gave up"
    first = threading.Thread(target=call, args=("first", first_cancel))
    first.start()
    assert first_cancel.waited.wait(5)
    joiner = threading.Thread(target=call, args=("joiner", Joiner()))
    joiner.start()
    first.join(5)
    joiner.join(5)
    assert outcomes == {"first": "gave up", "joiner": "entered"}


def test_a_cleanup_failure_inside_a_shared_hold_still_blocks_the_profile(tmp_path):
    owned = profile(tmp_path / "native-profile")
    operations = tmp_path / "operations"
    private_directory(operations)
    with pytest.raises(AgentFailure, match="AGENT_CLEANUP_FAILED"):
        with native_profile(owned, threading.Event(), deadline=deadline(), operations_root=operations, shared=True):
            raise AgentFailure("AGENT_CLEANUP_FAILED")
    with pytest.raises(AdmissionBlocked):
        with native_profile(owned, threading.Event(), deadline=deadline(), shared=True):
            pytest.fail("a blocked profile admitted a shared call")


def test_profile_cleanup_marker_requires_its_own_verified_operation_root(tmp_path):
    owned = profile(tmp_path / "native-profile")
    operations = tmp_path / "operations"
    private_directory(operations)
    with pytest.raises(AgentFailure, match="AGENT_CLEANUP_FAILED"):
        with native_profile(owned, threading.Event(), deadline=deadline(), operations_root=operations):
            raise AgentFailure("AGENT_CLEANUP_FAILED")
    with pytest.raises(AdmissionBlocked):
        with native_profile(owned, threading.Event(), deadline=deadline()):
            pytest.fail("unrecovered profile admitted")
    assert recover_profile(owned, tmp_path / "foreign-root")
    assert not recover_profile(owned, operations)
    with native_profile(owned, threading.Event(), deadline=deadline()):
        pass


def test_a_call_cannot_join_a_shared_hold_after_a_blocked_marker(tmp_path):
    owned, cancel = profile(tmp_path / "native-profile"), threading.Event()
    with native_profile(owned, cancel, deadline=deadline(), shared=True, operations_root=tmp_path):
        # Another call of the hold failed cleanup, as `_owned` records it.
        (owned.root / BLOCKED).write_text("{}")
        with pytest.raises(AdmissionBlocked):
            with native_profile(owned, cancel, deadline=deadline(), shared=True, operations_root=tmp_path):
                pytest.fail("a call joined the hold beside a process that may live")
    # The refused call left the hold, so the last one out still released the lock.
    (owned.root / BLOCKED).unlink()
    assert profile_free(owned)
