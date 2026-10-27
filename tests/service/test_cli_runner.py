"""resume_api.cli.runner: the POSIX operation directory, process-group cleanup and reaper, driven through its Runner
over a fake CLI. No account or provider network."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import pytest

from resume_api.cli.runner import OWNER, Runner, SpikeError, group_members, operation, reap_owned
from tests.providers.fixtures import install_fake_cli


PROMPT = "T00B_SYNTHETIC_CANARY — Alex Example; quotes '\" $() ; `inert` ☃"


class Fake:
    def __init__(self, base: Path):
        self.base = base
        self.fixture = base / "fake CLI 'quoted' Юникод $(inert)"
        self.fixture.mkdir()
        self.cli = install_fake_cli(self.fixture)
        self.root = base / "operations with spaces ' ☃ $()"
        self.root.mkdir()
        self.unrelated = self.root / "keep.txt"
        self.unrelated.write_text("unrelated synthetic fixture")
        self.configure()
        self.runner = Runner(self.cli, root=self.root)

    def configure(self, case="valid", **extra):
        (self.fixture / "fixture.json").write_text(json.dumps({"case": case, "prompt": PROMPT, **extra}))

    def audit(self):
        path = self.fixture / "audit.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def starts(self):
        return sum(item.get("generation", False) for item in self.audit())

    def assert_clean(self):
        assert list(self.root.iterdir()) == [self.unrelated]
        assert self.unrelated.read_text() == "unrelated synthetic fixture"

    def generate(self, **kwargs):
        return self.runner.generate(PROMPT, model="gpt-6-luna", **kwargs)

    def failure(self, case, code, **config):
        self.configure(case, **config)
        with pytest.raises(SpikeError) as raised:
            self.generate(timeout=60)
        assert str(raised.value) == code
        assert PROMPT not in str(raised.value) and "synthetic-secret" not in str(raised.value)
        assert PROMPT not in json.dumps(self.runner.last_metadata)
        assert "synthetic-secret" not in json.dumps(self.runner.last_metadata)
        assert self.runner.last_metadata["usage"] is None
        self.assert_clean()

    @contextmanager
    def background(self, **kwargs):
        outcome = []

        def run():
            try:
                outcome.append(self.generate(**kwargs))
            except SpikeError as error:
                outcome.append(error.code)

        thread = threading.Thread(target=run)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not (self.fixture / "ready").exists():
                if not thread.is_alive() or time.monotonic() >= deadline:
                    pytest.fail("Fake did not signal readiness")
                time.sleep(0.005)
            yield outcome
        finally:
            thread.join(2)
            if thread.is_alive():
                (self.fixture / "release").touch()
                thread.join(2)
            assert not thread.is_alive(), "Runner did not stop"


@pytest.fixture
def fake(tmp_path):
    return Fake(tmp_path)


def stale_directory(root, identifier, *, owner=OWNER):
    stale = root / ("op-" + identifier)
    stale.mkdir()
    (stale / ".owner").write_text(json.dumps({"owner": owner, "id": identifier}))
    (stale / ".lock").touch()
    return stale


def stopped(pid):
    state = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True).stdout.strip()
    return not state or state.startswith("Z")


def test_valid_result_usage_and_one_start(fake):
    result = fake.generate()
    assert result.summary == "Fictional engineer builds small services."
    assert result.usage == {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 12}
    assert result.generation_starts == 1 and result.internal_inference_count is None
    assert fake.starts() == 1
    fake.assert_clean()


@pytest.mark.parametrize("case,code", [
    ("malformed_event", "INVALID_RESULT"), ("invalid_utf8", "INVALID_RESULT"),
    ("utf16", "INVALID_RESULT"), ("utf32", "INVALID_RESULT"),
    ("malformed_result", "INVALID_RESULT"), ("schema", "INVALID_RESULT"),
    ("extra_field", "INVALID_RESULT"), ("duplicate_field", "INVALID_RESULT"),
    ("nonfinite", "INVALID_RESULT"), ("bad_usage", "INVALID_RESULT"),
    ("incomplete", "INCOMPLETE_STREAM"), ("unterminated", "INCOMPLETE_STREAM"),
    ("duplicate_completion", "INVALID_RESULT"), ("duplicate_message", "INVALID_RESULT"),
    ("out_of_order", "INVALID_RESULT"), ("unknown_event", "INVALID_RESULT"),
    ("nonzero_after_complete", "CLI_FAILED"),
    ("nonzero", "CLI_FAILED"), ("quota", "RATE_LIMITED"), ("model_denied", "MODEL_DENIED"), ("expired", "AUTH_REQUIRED"),
])
def test_protocol_and_provider_failures_are_sanitized_without_retry(fake, case, code):
    fake.failure(case, code)
    assert fake.starts() == 1


def test_fragmented_unicode_and_unknown_optional_field(fake):
    fake.configure("fragmented")
    assert fake.generate().summary == "Вымышленный инженер ☃"
    fake.assert_clean()


def test_missing_usage_is_unknown(fake):
    fake.configure("missing_usage")
    assert fake.generate().usage is None


@pytest.mark.parametrize("case", ["excessive", "excessive_stderr"])
def test_output_caps_include_stderr(fake, case):
    fake.failure(case, "OUTPUT_TOO_LARGE")


@pytest.mark.parametrize("case,code,extra", [
    ("valid", "CLI_UNSUPPORTED", {"version": "codex-cli 0.0.1"}),
    ("bad_help", "CLI_PROFILE_UNSAFE", {}),
    ("missing_login", "AUTH_REQUIRED", {}),
    ("api_key", "AUTH_MODE_MISMATCH", {}),
    ("valid", "CLI_PROFILE_UNSAFE", {"version": "codex-cli 0.162.0-alpha.2"}),
])
def test_version_profile_and_auth_fail_before_generation(fake, case, code, extra):
    fake.failure(case, code, **extra)
    assert fake.starts() == 0


def test_missing_executable(fake):
    with pytest.raises(SpikeError, match="CLI_MISSING"):
        Runner(fake.base / "missing", root=fake.root).probe()
    fake.assert_clean()


def test_startup_status_metadata_and_idle_do_not_generate(fake):
    assert fake.runner.probe().generation_ready
    assert fake.runner.metadata() == {"auth_mode": "chatgpt", "models": ["gpt-6-luna"], "catalog_complete": True}
    # Idle is passive: no timer, thread, server, or generation was created.
    assert fake.starts() == 0
    fake.assert_clean()


@pytest.mark.parametrize("case,code", [
    ("metadata_error", "METADATA_FAILED"), ("metadata_tool", "UNEXPECTED_METADATA_EVENT"),
    ("metadata_api_key", "AUTH_MODE_MISMATCH"), ("metadata_initial_only", "INCOMPLETE_STREAM"),
    ("metadata_account_only", "INCOMPLETE_STREAM"), ("metadata_duplicate_catalog", "METADATA_FAILED"),
])
def test_metadata_errors_and_auth_changes_are_safe(fake, case, code):
    fake.configure(case)
    with pytest.raises(SpikeError) as raised:
        fake.runner.metadata()
    assert str(raised.value) == code
    assert fake.starts() == 0
    fake.assert_clean()


def test_stdin_argv_environment_and_safe_logs(fake):
    environment = {key: "synthetic-secret" for key in (
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN",
        "CODEX_HOME", "CODEX_MODEL", "T3CODE_CODEX_LAUNCH_ARGS", "PYTHONPATH", "HTTPS_PROXY",
    )}
    with patch.dict(os.environ, environment):
        result = fake.generate()
    assert any(entry.get("stdin_match") for entry in fake.audit())
    assert PROMPT not in json.dumps(fake.audit()) and "synthetic-secret" not in json.dumps(fake.audit())
    assert result.summary not in json.dumps(result.metadata())
    fake.assert_clean()
    assert not (fake.base / "inert").exists()


@pytest.mark.parametrize("kind", ["command_execution", "mcp_tool_call", "web_search", "file_change", "image_generation",
                                  "collab_tool_call", "unknown_tool"])
def test_every_unexpected_tool_item_is_rejected(fake, kind):
    fake.failure("tool", "UNEXPECTED_TOOL_ACTIVITY", tool_type=kind)


def test_invalid_limits_input_and_model_do_not_spawn(fake):
    for value in (0, -1, 61, float("inf"), float("nan"), True, None, "60"):
        with pytest.raises(SpikeError, match="INVALID_LIMIT"):
            fake.generate(timeout=value)
    with pytest.raises(SpikeError, match="INPUT_TOO_LARGE"):
        fake.runner.generate("☃" * 3000, model="gpt-6-luna")
    with pytest.raises(SpikeError, match="INVALID_INPUT"):
        fake.runner.generate("", model="gpt-6-luna")
    with pytest.raises(SpikeError, match="MODEL_DENIED"):
        fake.runner.generate(PROMPT, model="--evil")
    assert fake.audit() == []


def test_prompt_words_in_stderr_do_not_relabel_exit(fake):
    prompt = "Designed an authentication service with a quota and a model not available."
    fake.configure("nonzero", prompt=prompt)
    with pytest.raises(SpikeError, match="CLI_FAILED"):
        fake.runner.generate(prompt, model="gpt-6-luna")
    assert prompt not in json.dumps(fake.runner.last_metadata)
    fake.assert_clean()


def test_deadline_expired_after_schema_write_does_not_spawn(fake):
    offset = [0]
    fake.runner.clock = lambda: time.monotonic() + offset[0]
    original = Path.write_text

    def write_text(path, data, *args, **kwargs):
        result = original(path, data, *args, **kwargs)
        if path.name == "schema.json":
            offset[0] = 61
        return result

    with patch.object(Path, "write_text", write_text):
        with pytest.raises(SpikeError, match="DEADLINE_EXCEEDED"):
            fake.generate(timeout=60)
    assert fake.runner.generation_starts == 0 and fake.runner.last_metadata["generation_starts"] == 0
    assert fake.starts() == 0
    fake.assert_clean()


@pytest.mark.parametrize("record", [b"", b"{bad", b'{"pid":0}', b'{"pid":2,"extra":true}'])
def test_corrupt_worker_record_is_quarantined(fake, record):
    stale = stale_directory(fake.root, "f" * 32)
    (stale / ".worker").write_bytes(record)
    (stale / "canary").write_text(PROMPT)
    Runner(fake.cli, root=fake.root)
    assert (stale / ".worker").read_bytes() == record
    assert (stale / "canary").read_text() == PROMPT
    assert (stale / ".cleanup-blocked").exists()


def test_symlinked_worker_record_is_quarantined(fake):
    stale = stale_directory(fake.root, "f" * 32)
    (stale / ".worker").symlink_to(stale / "missing-worker")
    Runner(fake.cli, root=fake.root)
    assert (stale / ".worker").is_symlink()
    assert (stale / ".cleanup-blocked").exists()


def test_fallback_reinspects_same_group_fork(fake):
    fake.configure("fork_race")
    real_killpg = os.killpg
    inspected = [0]
    marker = fake.fixture / "leader_pid"

    def killpg(group_id, sig):
        if marker.exists() and group_id == int(marker.read_text()):
            raise PermissionError()
        return real_killpg(group_id, sig)

    def members(group_id):
        if marker.exists() and group_id == int(marker.read_text()):
            inspected[0] += 1
            snapshot = group_members(group_id)
            if inspected[0] == 2:
                (fake.fixture / "fork_now").touch()
                deadline = time.monotonic() + 15
                while not (fake.fixture / "forked_pid").exists():
                    if time.monotonic() >= deadline:
                        pytest.fail("Worker did not fork")
                    time.sleep(0.005)
            return snapshot
        return group_members(group_id)

    try:
        with patch("resume_api.cli.runner.os.killpg", side_effect=killpg), patch(
            "resume_api.cli.runner.group_members", side_effect=members
        ):
            assert fake.generate().summary == "Fictional engineer builds small services."
        assert inspected[0] >= 3
        assert stopped(int((fake.fixture / "forked_pid").read_text()))
        fake.assert_clean()
    finally:
        if marker.exists():
            try:
                real_killpg(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_unverified_group_cleanup_quarantines_operation(fake):
    def members(group_id):
        if fake.starts():
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        return group_members(group_id)

    with patch("resume_api.cli.runner.group_members", side_effect=members):
        with pytest.raises(SpikeError, match="PROCESS_CLEANUP_FAILED"):
            fake.generate()
    directories = [path for path in fake.root.iterdir() if path.is_dir()]
    assert len(directories) == 1
    assert (directories[0] / ".worker").exists() and (directories[0] / ".cleanup-blocked").exists()
    assert (directories[0] / "synthetic-content.txt").read_text() == PROMPT


def test_cancel_before_spawn(fake):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(SpikeError, match="CANCELLED"):
        fake.generate(cancel=cancel)
    assert fake.audit() == []


def test_cancellation_discards_already_completed_stream(fake):
    fake.configure("late")
    cancel = threading.Event()
    with fake.background(cancel=cancel) as outcome:
        cancel.set()
    assert outcome == ["CANCELLED"] and fake.starts() == 1
    fake.assert_clean()


def test_deadline_discards_delayed_completion(fake):
    fake.configure("late")
    advanced = threading.Event()
    fake.runner.clock = lambda: time.monotonic() + (61 if advanced.is_set() else 0)
    with fake.background(timeout=60) as outcome:
        advanced.set()
    assert outcome == ["DEADLINE_EXCEEDED"]
    fake.assert_clean()


def test_deadline_also_bounds_status_probes(fake):
    fake.configure("slow_probe")
    advanced = threading.Event()
    fake.runner.clock = lambda: time.monotonic() + (61 if advanced.is_set() else 0)
    with fake.background(timeout=60) as outcome:
        advanced.set()
    assert outcome == ["DEADLINE_EXCEEDED"] and fake.starts() == 0
    fake.assert_clean()


def test_child_ignoring_term_is_stopped_on_cancel(fake):
    fake.configure("tree")
    cancel = threading.Event()
    with fake.background(cancel=cancel) as outcome:
        pid = int((fake.fixture / "child_pid").read_text())
        cancel.set()
    assert outcome == ["CANCELLED"]
    assert (fake.fixture / "term_seen").exists()
    assert stopped(pid), "Child still running"
    fake.assert_clean()


def test_cancel_during_generation_without_completion(fake):
    fake.configure("hang")
    cancel = threading.Event()
    with fake.background(cancel=cancel) as outcome:
        cancel.set()
    assert outcome == ["CANCELLED"] and fake.starts() == 1
    fake.assert_clean()


def test_child_is_stopped_on_deadline(fake):
    fake.configure("tree")
    advanced = threading.Event()
    fake.runner.clock = lambda: time.monotonic() + (61 if advanced.is_set() else 0)
    with fake.background(timeout=60) as outcome:
        pid = int((fake.fixture / "child_pid").read_text())
        advanced.set()
    assert outcome == ["DEADLINE_EXCEEDED"]
    assert stopped(pid)
    assert (fake.fixture / "term_seen").exists()
    fake.assert_clean()


def test_failed_process_cleanup_preserves_quarantined_directory(fake):
    with pytest.raises(SpikeError, match="PROCESS_CLEANUP_FAILED"):
        with operation(fake.root) as directory:
            (directory / "synthetic-content").write_text(PROMPT)
            raise SpikeError("PROCESS_CLEANUP_FAILED")
    Runner(fake.cli, root=fake.root)
    assert (directory / "synthetic-content").read_text() == PROMPT
    assert (directory / ".cleanup-blocked").exists()


def test_restart_reaps_only_marked_inactive_directories(fake):
    stale = stale_directory(fake.root, "a" * 32)
    (stale / "canary").write_text(PROMPT)
    other = stale_directory(fake.root, "b" * 32, owner="unrelated")
    link = fake.root / ("op-" + "c" * 32)
    link.symlink_to(fake.fixture, target_is_directory=True)
    with operation(fake.root) as active:
        (active / "canary").write_text(PROMPT)
        assert reap_owned(fake.root) == 1
        assert active.exists()
    assert not stale.exists() and other.exists() and link.is_symlink()
    assert fake.unrelated.exists() and fake.cli.exists()


def test_startup_automatically_reaps_owned_crash_directory(fake):
    stale = stale_directory(fake.root, "d" * 32)
    (stale / "canary").write_text(PROMPT)
    Runner(fake.cli, root=fake.root)
    fake.assert_clean()
    assert fake.audit() == []


def test_spawn_marker_precedes_launch_and_failed_launch_cleans_up(fake):
    original_popen = subprocess.Popen
    markers = []

    def checked_popen(*args, **kwargs):
        if args[0][0] == str(fake.cli):
            markers.append(json.loads((Path(kwargs["cwd"]) / ".worker").read_text()))
        return original_popen(*args, **kwargs)

    with patch("resume_api.cli.runner.subprocess.Popen", side_effect=checked_popen):
        fake.runner.probe()
    assert markers == [{"state": "spawning"}] * 3
    fake.assert_clean()
    with patch("resume_api.cli.runner.subprocess.Popen", side_effect=FileNotFoundError):
        with pytest.raises(SpikeError, match="CLI_MISSING"):
            fake.runner.probe()
    fake.assert_clean()


def test_restart_quarantines_crash_during_spawn_with_live_worker(fake):
    stale = stale_directory(fake.root, "6" * 32)
    (stale / ".worker").write_text('{"state":"spawning"}')
    (stale / "canary").write_text(PROMPT)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=stale, start_new_session=True)
    try:
        Runner(fake.cli, root=fake.root)
        assert child.poll() is None
        assert (stale / "canary").read_text() == PROMPT
        assert (stale / ".cleanup-blocked").exists()
        assert json.loads((stale / ".worker").read_text()) == {"state": "spawning"}
    finally:
        child.kill()
        child.wait(timeout=2)


def test_malformed_owner_does_not_block_independent_cleanup(fake):
    bad_id, good_id = "7" * 32, "8" * 32
    bad, good = fake.root / ("op-" + bad_id), fake.root / ("op-" + good_id)
    for path in (bad, good):
        path.mkdir()
        (path / ".lock").touch()
        (path / "canary").write_text(PROMPT)
    (bad / ".owner").write_text("{bad")
    (good / ".owner").write_text(json.dumps({"owner": OWNER, "id": good_id}))
    Runner(fake.cli, root=fake.root)
    assert (bad / "canary").read_text() == PROMPT
    assert not good.exists()
    assert fake.audit() == []


def test_restart_preserves_directory_with_surviving_worker(fake):
    stale = stale_directory(fake.root, "e" * 32)
    (stale / "canary").write_text(PROMPT)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    (stale / ".worker").write_text(json.dumps({"pid": child.pid}))
    try:
        Runner(fake.cli, root=fake.root)
        assert stale.exists()
    finally:
        child.kill()
        child.wait(timeout=2)
    Runner(fake.cli, root=fake.root)
    fake.assert_clean()
    assert fake.audit() == []


def test_symlink_temp_root_is_rejected(fake):
    link = fake.base / "root-link"
    link.symlink_to(fake.fixture, target_is_directory=True)
    with pytest.raises(SpikeError, match="UNSAFE_TEMP_ROOT"):
        Runner(fake.cli, root=link).probe()
    assert fake.audit() == []


def test_unusable_temp_root_has_sanitized_error(fake):
    with pytest.raises(SpikeError, match="TEMP_FAILED"):
        Runner(fake.cli, root=fake.unrelated).probe()
    assert fake.audit() == []
