"""Exercise the actual process wrapper, with no account or provider network."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from resume_api.cli.runner import OWNER, Runner, SpikeError, group_members, operation, reap_owned


PROMPT = "T00B_SYNTHETIC_CANARY — Alex Example; quotes '\" $() ; `inert` ☃"


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.fixture = self.base / "fake CLI 'quoted' Юникод $(inert)"
        self.fixture.mkdir()
        self.cli = self.fixture / "codex fixture"
        source = Path(__file__).with_name("fake_cli.py").read_text()
        self.cli.write_text("#!" + sys.executable + "\n" + source.split("\n", 1)[1])
        self.cli.chmod(0o700)
        shutil.copyfile(Path(__file__).with_name("fixtures") / "success.jsonl", self.fixture / "success.jsonl")
        self.root = self.base / "operations with spaces ' ☃ $()"
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
        self.assertEqual(list(self.root.iterdir()), [self.unrelated])
        self.assertEqual(self.unrelated.read_text(), "unrelated synthetic fixture")

    def generate(self, **kwargs):
        return self.runner.generate(PROMPT, model="gpt-6-luna", **kwargs)

    def failure(self, case, code, **config):
        self.configure(case, **config)
        with self.assertRaises(SpikeError) as raised:
            self.generate(timeout=3)
        self.assertEqual(str(raised.exception), code)
        self.assertNotIn(PROMPT, str(raised.exception))
        self.assertNotIn("synthetic-secret", str(raised.exception))
        self.assertNotIn(PROMPT, json.dumps(self.runner.last_metadata))
        self.assertNotIn("synthetic-secret", json.dumps(self.runner.last_metadata))
        self.assertIsNone(self.runner.last_metadata["usage"])
        self.assert_clean()

    def test_valid_result_usage_and_one_start(self):
        result = self.generate()
        self.assertEqual(result.summary, "Fictional engineer builds small services.")
        self.assertEqual(result.usage, {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 12})
        self.assertEqual(result.generation_starts, 1)
        self.assertIsNone(result.internal_inference_count)
        self.assertEqual(self.starts(), 1)
        self.assert_clean()

    def test_protocol_failures(self):
        for case, code in [
            ("malformed_event", "INVALID_RESULT"), ("invalid_utf8", "INVALID_RESULT"),
            ("utf16", "INVALID_RESULT"), ("utf32", "INVALID_RESULT"),
            ("malformed_result", "INVALID_RESULT"), ("schema", "INVALID_RESULT"),
            ("extra_field", "INVALID_RESULT"), ("duplicate_field", "INVALID_RESULT"),
            ("nonfinite", "INVALID_RESULT"), ("bad_usage", "INVALID_RESULT"),
            ("incomplete", "INCOMPLETE_STREAM"), ("unterminated", "INCOMPLETE_STREAM"),
            ("duplicate_completion", "INVALID_RESULT"), ("duplicate_message", "INVALID_RESULT"),
            ("out_of_order", "INVALID_RESULT"), ("unknown_event", "INVALID_RESULT"),
            ("nonzero_after_complete", "CLI_FAILED"),
        ]:
            with self.subTest(case=case):
                before = self.starts()
                self.failure(case, code)
                self.assertEqual(self.starts() - before, 1)

    def test_fragmented_unicode_and_unknown_optional_field(self):
        self.configure("fragmented")
        self.assertEqual(self.generate().summary, "Вымышленный инженер ☃")
        self.assert_clean()

    def test_missing_usage_is_unknown(self):
        self.configure("missing_usage")
        self.assertIsNone(self.generate().usage)

    def test_output_caps_include_stderr(self):
        for case in ["excessive", "excessive_stderr"]:
            with self.subTest(case=case):
                self.failure(case, "OUTPUT_TOO_LARGE")

    def test_sanitized_provider_failures_without_retry(self):
        for case, code in [("nonzero", "CLI_FAILED"), ("quota", "RATE_LIMITED"),
                           ("model_denied", "MODEL_DENIED"), ("expired", "AUTH_REQUIRED")]:
            with self.subTest(case=case):
                before = self.starts()
                self.failure(case, code)
                self.assertEqual(self.starts() - before, 1)

    def test_version_profile_and_auth_fail_before_generation(self):
        for case, code, extra in [
            ("valid", "CLI_UNSUPPORTED", {"version": "codex-cli 0.0.1"}),
            ("bad_help", "CLI_PROFILE_UNSAFE", {}),
            ("missing_login", "AUTH_REQUIRED", {}),
            ("api_key", "AUTH_MODE_MISMATCH", {}),
            ("valid", "CLI_PROFILE_UNSAFE", {"version": "codex-cli 0.162.0-alpha.2"}),
        ]:
            with self.subTest(case=case, extra=extra):
                self.failure(case, code, **extra)
        self.assertEqual(self.starts(), 0)

    def test_missing_executable(self):
        with self.assertRaisesRegex(SpikeError, "CLI_MISSING"):
            Runner(self.base / "missing", root=self.root).probe()
        self.assert_clean()

    def test_startup_status_metadata_and_idle_do_not_generate(self):
        self.assertTrue(self.runner.probe().generation_ready)
        self.assertEqual(self.runner.metadata(), {"auth_mode": "chatgpt", "models": ["gpt-6-luna"], "catalog_complete": True})
        # Idle is passive: no timer, thread, server, or generation was created.
        self.assertEqual(self.starts(), 0)
        self.assert_clean()

    def test_metadata_errors_and_auth_changes_are_safe(self):
        for case, code in [("metadata_error", "METADATA_FAILED"),
                           ("metadata_tool", "UNEXPECTED_METADATA_EVENT"),
                           ("metadata_api_key", "AUTH_MODE_MISMATCH"),
                           ("metadata_initial_only", "INCOMPLETE_STREAM"),
                           ("metadata_account_only", "INCOMPLETE_STREAM"),
                           ("metadata_duplicate_catalog", "METADATA_FAILED")]:
            with self.subTest(case=case):
                self.configure(case)
                with self.assertRaises(SpikeError) as raised:
                    self.runner.metadata()
                self.assertEqual(str(raised.exception), code)
                self.assertEqual(self.starts(), 0)
                self.assert_clean()

    def test_stdin_argv_environment_and_safe_logs(self):
        environment = {key: "synthetic-secret" for key in (
            "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN",
            "CODEX_HOME", "CODEX_MODEL", "T3CODE_CODEX_LAUNCH_ARGS", "PYTHONPATH", "HTTPS_PROXY",
        )}
        with patch.dict(os.environ, environment):
            result = self.generate()
        self.assertTrue(any(entry.get("stdin_match") for entry in self.audit()))
        self.assertNotIn(PROMPT, json.dumps(self.audit()))
        self.assertNotIn("synthetic-secret", json.dumps(self.audit()))
        self.assertNotIn(result.summary, json.dumps(result.metadata()))
        self.assert_clean()
        self.assertFalse((self.base / "inert").exists())

    def test_every_unexpected_tool_item_is_rejected(self):
        for kind in ["command_execution", "mcp_tool_call", "web_search", "file_change", "image_generation", "collab_tool_call", "unknown_tool"]:
            with self.subTest(kind=kind):
                self.failure("tool", "UNEXPECTED_TOOL_ACTIVITY", tool_type=kind)

    def test_invalid_limits_input_and_model_do_not_spawn(self):
        for value in (0, -1, 61, float("inf"), float("nan"), True, None, "60"):
            with self.subTest(value=value), self.assertRaisesRegex(SpikeError, "INVALID_LIMIT"):
                self.generate(timeout=value)
        with self.assertRaisesRegex(SpikeError, "INPUT_TOO_LARGE"):
            self.runner.generate("☃" * 3000, model="gpt-6-luna")
        with self.assertRaisesRegex(SpikeError, "INVALID_INPUT"):
            self.runner.generate("", model="gpt-6-luna")
        with self.assertRaisesRegex(SpikeError, "MODEL_DENIED"):
            self.runner.generate(PROMPT, model="--evil")
        self.assertEqual(self.audit(), [])

    def test_prompt_words_in_stderr_do_not_relabel_exit(self):
        prompt = "Designed an authentication service with a quota and a model not available."
        self.configure("nonzero", prompt=prompt)
        with self.assertRaisesRegex(SpikeError, "CLI_FAILED"):
            self.runner.generate(prompt, model="gpt-6-luna")
        self.assertNotIn(prompt, json.dumps(self.runner.last_metadata))
        self.assert_clean()

    def test_deadline_expired_after_schema_write_does_not_spawn(self):
        offset = [0]
        self.runner.clock = lambda: time.monotonic() + offset[0]
        original = Path.write_text

        def write_text(path, data, *args, **kwargs):
            result = original(path, data, *args, **kwargs)
            if path.name == "schema.json":
                offset[0] = 61
            return result

        with patch.object(Path, "write_text", write_text):
            with self.assertRaisesRegex(SpikeError, "DEADLINE_EXCEEDED"):
                self.generate(timeout=60)
        self.assertEqual(self.runner.generation_starts, 0)
        self.assertEqual(self.runner.last_metadata["generation_starts"], 0)
        self.assertEqual(self.starts(), 0)
        self.assert_clean()

    def test_corrupt_worker_record_is_quarantined(self):
        for index, record in enumerate((b"", b"{bad", b'{"pid":0}', b'{"pid":2,"extra":true}')):
            with self.subTest(record=record):
                identifier = "f" * 31 + str(index)
                stale = self.root / ("op-" + identifier)
                stale.mkdir()
                (stale / ".owner").write_text(json.dumps({"owner": OWNER, "id": identifier}))
                (stale / ".lock").touch()
                (stale / ".worker").write_bytes(record)
                (stale / "canary").write_text(PROMPT)
                Runner(self.cli, root=self.root)
                self.assertEqual((stale / ".worker").read_bytes(), record)
                self.assertEqual((stale / "canary").read_text(), PROMPT)
                self.assertTrue((stale / ".cleanup-blocked").exists())

        identifier = "f" * 31 + "4"
        stale = self.root / ("op-" + identifier)
        stale.mkdir()
        (stale / ".owner").write_text(json.dumps({"owner": OWNER, "id": identifier}))
        (stale / ".lock").touch()
        (stale / ".worker").symlink_to(stale / "missing-worker")
        Runner(self.cli, root=self.root)
        self.assertTrue((stale / ".worker").is_symlink())
        self.assertTrue((stale / ".cleanup-blocked").exists())

    def test_fallback_reinspects_same_group_fork(self):
        self.configure("fork_race")
        real_killpg = os.killpg
        inspected = [0]

        def killpg(group_id, sig):
            marker = self.fixture / "leader_pid"
            if marker.exists() and group_id == int(marker.read_text()):
                raise PermissionError()
            return real_killpg(group_id, sig)

        def members(group_id):
            marker = self.fixture / "leader_pid"
            if marker.exists() and group_id == int(marker.read_text()):
                inspected[0] += 1
                snapshot = group_members(group_id)
                if inspected[0] == 2:
                    (self.fixture / "fork_now").touch()
                    deadline = time.monotonic() + 2
                    while not (self.fixture / "forked_pid").exists():
                        if time.monotonic() >= deadline:
                            self.fail("Worker did not fork")
                        time.sleep(0.005)
                return snapshot
            return group_members(group_id)

        try:
            with patch("resume_api.cli.runner.os.killpg", side_effect=killpg), patch(
                "resume_api.cli.runner.group_members", side_effect=members
            ):
                self.assertEqual(self.generate().summary, "Fictional engineer builds small services.")
            self.assertGreaterEqual(inspected[0], 3)
            child = int((self.fixture / "forked_pid").read_text())
            state = subprocess.run(["/bin/ps", "-p", str(child), "-o", "stat="],
                                   capture_output=True, text=True).stdout.strip()
            self.assertTrue(not state or state.startswith("Z"), state)
            self.assert_clean()
        finally:
            marker = self.fixture / "leader_pid"
            if marker.exists():
                try:
                    real_killpg(int(marker.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_unverified_group_cleanup_quarantines_operation(self):
        def members(group_id):
            if self.starts():
                raise SpikeError("PROCESS_CLEANUP_FAILED")
            return group_members(group_id)

        with patch("resume_api.cli.runner.group_members", side_effect=members):
            with self.assertRaisesRegex(SpikeError, "PROCESS_CLEANUP_FAILED"):
                self.generate()
        directories = [path for path in self.root.iterdir() if path.is_dir()]
        self.assertEqual(len(directories), 1)
        self.assertTrue((directories[0] / ".worker").exists())
        self.assertTrue((directories[0] / ".cleanup-blocked").exists())
        self.assertEqual((directories[0] / "synthetic-content.txt").read_text(), PROMPT)

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
            deadline = time.monotonic() + 4
            while not (self.fixture / "ready").exists():
                if not thread.is_alive() or time.monotonic() >= deadline:
                    self.fail("Fake did not signal readiness")
                time.sleep(0.005)
            yield outcome
        finally:
            thread.join(2)
            if thread.is_alive():
                (self.fixture / "release").touch()
                thread.join(2)
            self.assertFalse(thread.is_alive(), "Runner did not stop")

    def test_cancel_before_spawn(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaisesRegex(SpikeError, "CANCELLED"):
            self.generate(cancel=cancel)
        self.assertEqual(self.audit(), [])

    def test_cancellation_discards_already_completed_stream(self):
        self.configure("late")
        cancel = threading.Event()
        with self.background(cancel=cancel) as outcome:
            cancel.set()
        self.assertEqual(outcome, ["CANCELLED"])
        self.assertEqual(self.starts(), 1)
        self.assert_clean()

    def test_deadline_discards_delayed_completion(self):
        self.configure("late")
        advanced = threading.Event()
        self.runner.clock = lambda: time.monotonic() + (61 if advanced.is_set() else 0)
        with self.background(timeout=60) as outcome:
            advanced.set()
        self.assertEqual(outcome, ["DEADLINE_EXCEEDED"])
        self.assert_clean()

    def test_deadline_also_bounds_status_probes(self):
        self.configure("slow_probe")
        advanced = threading.Event()
        self.runner.clock = lambda: time.monotonic() + (61 if advanced.is_set() else 0)
        with self.background(timeout=60) as outcome:
            advanced.set()
        self.assertEqual(outcome, ["DEADLINE_EXCEEDED"])
        self.assertEqual(self.starts(), 0)
        self.assert_clean()

    def test_child_ignoring_term_is_stopped_on_cancel(self):
        self.configure("tree")
        cancel = threading.Event()
        with self.background(cancel=cancel) as outcome:
            pid = int((self.fixture / "child_pid").read_text())
            cancel.set()
        self.assertEqual(outcome, ["CANCELLED"])
        self.assertTrue((self.fixture / "term_seen").exists())
        state = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True).stdout.strip()
        self.assertTrue(not state or state.startswith("Z"), f"Child still running: {state}")
        self.assert_clean()

    def test_cancel_during_generation_without_completion(self):
        self.configure("hang")
        cancel = threading.Event()
        with self.background(cancel=cancel) as outcome:
            cancel.set()
        self.assertEqual(outcome, ["CANCELLED"])
        self.assertEqual(self.starts(), 1)
        self.assert_clean()

    def test_child_is_stopped_on_deadline(self):
        self.configure("tree")
        advanced = threading.Event()
        self.runner.clock = lambda: time.monotonic() + (61 if advanced.is_set() else 0)
        with self.background(timeout=60) as outcome:
            pid = int((self.fixture / "child_pid").read_text())
            advanced.set()
        self.assertEqual(outcome, ["DEADLINE_EXCEEDED"])
        state = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True).stdout.strip()
        self.assertTrue(not state or state.startswith("Z"))
        self.assertTrue((self.fixture / "term_seen").exists())
        self.assert_clean()

    def test_failed_process_cleanup_preserves_quarantined_directory(self):
        with self.assertRaisesRegex(SpikeError, "PROCESS_CLEANUP_FAILED"):
            with operation(self.root) as directory:
                (directory / "synthetic-content").write_text(PROMPT)
                raise SpikeError("PROCESS_CLEANUP_FAILED")
        Runner(self.cli, root=self.root)
        self.assertEqual((directory / "synthetic-content").read_text(), PROMPT)
        self.assertTrue((directory / ".cleanup-blocked").exists())

    def test_restart_reaps_only_marked_inactive_directories(self):
        identifier = "a" * 32
        stale = self.root / ("op-" + identifier)
        stale.mkdir()
        (stale / ".owner").write_text(json.dumps({"owner": OWNER, "id": identifier}))
        (stale / ".lock").touch()
        (stale / "canary").write_text(PROMPT)
        other = self.root / ("op-" + "b" * 32)
        other.mkdir()
        (other / ".owner").write_text(json.dumps({"owner": "unrelated", "id": "b" * 32}))
        (other / ".lock").touch()
        link = self.root / ("op-" + "c" * 32)
        link.symlink_to(self.fixture, target_is_directory=True)
        with operation(self.root) as active:
            (active / "canary").write_text(PROMPT)
            self.assertEqual(reap_owned(self.root), 1)
            self.assertTrue(active.exists())
        self.assertFalse(stale.exists())
        self.assertTrue(other.exists())
        self.assertTrue(link.is_symlink())
        self.assertTrue(self.unrelated.exists())
        self.assertTrue(self.cli.exists())

    def test_startup_automatically_reaps_owned_crash_directory(self):
        identifier = "d" * 32
        stale = self.root / ("op-" + identifier)
        stale.mkdir()
        (stale / ".owner").write_text(json.dumps({"owner": OWNER, "id": identifier}))
        (stale / ".lock").touch()
        (stale / "canary").write_text(PROMPT)
        Runner(self.cli, root=self.root)
        self.assert_clean()
        self.assertEqual(self.audit(), [])

    def test_spawn_marker_precedes_launch_and_failed_launch_cleans_up(self):
        original_popen = subprocess.Popen
        markers = []

        def checked_popen(*args, **kwargs):
            if args[0][0] == str(self.cli):
                markers.append(json.loads((Path(kwargs["cwd"]) / ".worker").read_text()))
            return original_popen(*args, **kwargs)

        with patch("resume_api.cli.runner.subprocess.Popen", side_effect=checked_popen):
            self.runner.probe()
        self.assertEqual(markers, [{"state": "spawning"}] * 3)
        self.assert_clean()

        with patch("resume_api.cli.runner.subprocess.Popen", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(SpikeError, "CLI_MISSING"):
                self.runner.probe()
        self.assert_clean()

    def test_restart_quarantines_crash_during_spawn_with_live_worker(self):
        identifier = "6" * 32
        stale = self.root / ("op-" + identifier)
        stale.mkdir()
        (stale / ".owner").write_text(json.dumps({"owner": OWNER, "id": identifier}))
        (stale / ".lock").touch()
        (stale / ".worker").write_text('{"state":"spawning"}')
        (stale / "canary").write_text(PROMPT)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 cwd=stale, start_new_session=True)
        try:
            Runner(self.cli, root=self.root)
            self.assertIsNone(child.poll())
            self.assertEqual((stale / "canary").read_text(), PROMPT)
            self.assertTrue((stale / ".cleanup-blocked").exists())
            self.assertEqual(json.loads((stale / ".worker").read_text()), {"state": "spawning"})
        finally:
            child.kill()
            child.wait(timeout=2)

    def test_malformed_owner_does_not_block_independent_cleanup(self):
        bad_id, good_id = "7" * 32, "8" * 32
        bad, good = self.root / ("op-" + bad_id), self.root / ("op-" + good_id)
        for path in (bad, good):
            path.mkdir()
            (path / ".lock").touch()
            (path / "canary").write_text(PROMPT)
        (bad / ".owner").write_text("{bad")
        (good / ".owner").write_text(json.dumps({"owner": OWNER, "id": good_id}))
        Runner(self.cli, root=self.root)
        self.assertEqual((bad / "canary").read_text(), PROMPT)
        self.assertFalse(good.exists())
        self.assertEqual(self.audit(), [])

    def test_restart_preserves_directory_with_surviving_worker(self):
        identifier = "e" * 32
        stale = self.root / ("op-" + identifier)
        stale.mkdir()
        (stale / ".owner").write_text(json.dumps({"owner": OWNER, "id": identifier}))
        (stale / ".lock").touch()
        (stale / "canary").write_text(PROMPT)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        (stale / ".worker").write_text(json.dumps({"pid": child.pid}))
        try:
            Runner(self.cli, root=self.root)
            self.assertTrue(stale.exists())
        finally:
            child.kill()
            child.wait(timeout=2)
        Runner(self.cli, root=self.root)
        self.assert_clean()
        self.assertEqual(self.audit(), [])

    def test_symlink_temp_root_is_rejected(self):
        link = self.base / "root-link"
        link.symlink_to(self.fixture, target_is_directory=True)
        with self.assertRaisesRegex(SpikeError, "UNSAFE_TEMP_ROOT"):
            Runner(self.cli, root=link).probe()
        self.assertEqual(self.audit(), [])

    def test_unusable_temp_root_has_sanitized_error(self):
        with self.assertRaisesRegex(SpikeError, "TEMP_FAILED"):
            Runner(self.cli, root=self.unrelated).probe()
        self.assertEqual(self.audit(), [])


if __name__ == "__main__":
    unittest.main()
