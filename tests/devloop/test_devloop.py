"""Offline checks for the development review ledger."""

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[2] / "tools/devloop.py"
spec = importlib.util.spec_from_file_location("devloop", MODULE)
devloop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(devloop)


class DevloopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "docs/gui/automation").mkdir(parents=True)
        (self.repo / "src").mkdir()
        (self.repo / "src/new.py").write_text("answer = 1\n")
        self.list = self.repo / "files.txt"
        self.list.write_text("src/new.py\n")
        self.fake = self.repo / "fake-cli"
        self.configure()
        self.old = devloop.MODEL_EFFORT["grok"]
        devloop.MODEL_EFFORT["grok"] = {"verified-test-model": {"medium"}}
        self.addCleanup(lambda: devloop.MODEL_EFFORT.__setitem__("grok", self.old))
        self.real_verify = devloop.verify_grok_version
        devloop.verify_grok_version = lambda _executable: None
        self.addCleanup(lambda: setattr(devloop, "verify_grok_version", self.real_verify))

    def configure(self):
        config = {"version": 1, "providers": {"grok": {
            "executable": str(self.fake), "model": "verified-test-model",
            "effort": "medium", "transport": "grok_json"}}}
        (self.repo / "docs/gui/automation/config.json").write_text(json.dumps(config))

    def fake_output(self, output: object, code: int = 0):
        payload = json.dumps(output) if not isinstance(output, str) else output
        self.fake.write_text("#!/usr/bin/env python3\nimport sys\n"
                             f"sys.stdout.write({payload!r})\n"
                             f"sys.exit({code})\n")
        self.fake.chmod(0o755)

    def snap(self):
        return devloop.snapshot(self.repo, "T01", self.list)["snapshot"]

    def test_untracked_file_is_retained_and_stale_content_is_visible(self):
        sid = self.snap()
        kept = self.repo / ".devloop/snapshots" / sid / "files/src/new.py"
        self.assertEqual(kept.read_text(), "answer = 1\n")
        (self.repo / "src/new.py").write_text("answer = 2\n")
        state = devloop.status(self.repo)["snapshots"][0]
        self.assertFalse(state["current_files_match"])
        self.assertEqual(kept.read_text(), "answer = 1\n")

    def test_unsafe_paths_and_symlinks_are_rejected(self):
        for name in ("../secret", "/tmp/secret", ".git/config", "src//new.py"):
            with self.subTest(name=name):
                self.list.write_text(name + "\n")
                with self.assertRaises(devloop.DevloopError):
                    devloop.snapshot(self.repo, "T01", self.list)
        (self.repo / "src/link.py").symlink_to("new.py")
        self.list.write_text("src/link.py\n")
        with self.assertRaises(devloop.DevloopError):
            devloop.snapshot(self.repo, "T01", self.list)

    def test_structured_quota_defers_and_skips_next_call(self):
        sid = self.snap()
        self.fake_output({"error": {"code": "quota_exceeded", "retry_after": "2099-01-01T00:00:00+00:00"}}, 1)
        first = devloop.review(self.repo, sid, "grok")
        self.assertEqual(first["status"], "pending_quota")
        self.fake_output({"verdict": "pass", "summary": "Clear", "findings": []})
        second = devloop.review(self.repo, sid, "grok")
        self.assertTrue(second["skipped"])
        self.assertEqual(second["status"], "pending_quota")
        other = self.snap()
        deferred = devloop.review(self.repo, other, "grok")
        self.assertTrue(deferred["skipped"])
        self.assertEqual(deferred["status"], "pending_quota")
        backlog = devloop.read_json(devloop.backlog_path(self.repo))
        self.assertEqual(backlog["entries"][0]["manifest_sha256"], first["manifest_sha256"])
        self.assertEqual(len(backlog["entries"]), 2)
        third = devloop.review(self.repo, sid, "grok", force=True)
        self.assertEqual(third["status"], "reviewed")
        self.assertEqual(devloop.read_holds(self.repo)["providers"], {})

    def test_quota_words_in_model_text_are_not_provider_quota(self):
        sid = self.snap()
        self.fake_output("Quota exhausted; no review", 1)
        result = devloop.review(self.repo, sid, "grok")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "invalid_response")

    def test_adapter_quota_duration_and_auth_codes(self):
        quota = {"status": "failed", "error": {"code": "QUOTA_EXHAUSTED", "retry_after": "600"}}
        state, _, error = devloop.parse_response(1, json.dumps(quota).encode(), "gemini")
        self.assertEqual(state, "pending_quota")
        self.assertTrue(devloop.quota_hold_active(error))
        self.assertIn("T", error["retry_after"])
        auth = {"status": "failed", "error": {"code": "AUTH_REQUIRED"}}
        self.assertEqual(devloop.parse_response(1, json.dumps(auth).encode(), "gemini")[0],
                         "pending_setup")

    def test_model_supplied_usage_is_not_recorded(self):
        report = {"verdict": "pass", "summary": "Clear", "findings": [],
                  "usage": {"input_tokens": 1}}
        state, result, _ = devloop.parse_response(0, json.dumps(report).encode())
        self.assertEqual(state, "reviewed")
        self.assertIsNone(result["usage"])

    def test_malformed_and_eof_do_not_pass(self):
        sid = self.snap()
        self.fake_output("")
        self.assertEqual(devloop.review(self.repo, sid, "grok")["status"], "failed")
        self.fake_output({"verdict": "pass", "summary": "", "findings": []})
        self.assertEqual(devloop.review(self.repo, sid, "grok", force=True)["status"], "failed")

    def test_utf16_response_is_rejected(self):
        payload = {"verdict": "pass", "summary": "Clear", "findings": []}
        state, _, error = devloop.parse_response(0, json.dumps(payload).encode("utf-16"))
        self.assertEqual(state, "failed")
        self.assertEqual(error["code"], "invalid_response")

    def test_malformed_raw_stdout_is_retained_with_hash(self):
        sid = self.snap()
        self.fake.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdout.buffer.write(b'\\xff\\xfe')\n")
        self.fake.chmod(0o755)
        result = devloop.review(self.repo, sid, "grok")
        self.assertEqual(result["status"], "failed")
        raw = self.repo / result["stdout_path"]
        self.assertEqual(raw.read_bytes(), b"\xff\xfe")
        self.assertEqual(result["stdout_sha256"], devloop.hashlib.sha256(b"\xff\xfe").hexdigest())

    def test_child_environment_disables_codex_compat_features(self):
        environment = devloop.safe_environment()
        for feature in ("SKILLS", "RULES", "AGENTS", "MCPS", "HOOKS"):
            self.assertEqual(environment[f"GROK_CODEX_{feature}_ENABLED"], "0")

    def test_grok_headless_envelope_requires_end_turn_and_exact_model(self):
        response = {"stopReason": "end_turn", "modelUsage": {
            "grok-4.7-build-fast": {"modelCalls": 1}},
            "structuredOutput": {"verdict": "pass", "summary": "Clear", "findings": []},
            "usage": {"input_tokens": 10, "output_tokens": 2}}
        status, result, _ = devloop.parse_response(
            0, json.dumps(response).encode(), "grok", "grok-4.7-build-fast")
        self.assertEqual(status, "reviewed")
        self.assertEqual(result["usage"]["input_tokens"], 10)
        response["stopReason"] = "max_tokens"
        self.assertEqual(devloop.parse_response(0, json.dumps(response).encode())[0], "failed")
        response["stopReason"] = "end_turn"
        response["modelUsage"] = {"other-model": {"modelCalls": 1}}
        self.assertEqual(devloop.parse_response(0, json.dumps(response).encode())[0], "failed")

    def test_grok_cli_error_quota_requires_nonzero_error_envelope(self):
        error = {"type": "error", "message": "Quota exceeded for this account"}
        self.assertEqual(devloop.parse_response(1, json.dumps(error).encode())[0],
                         "pending_quota")
        self.assertEqual(devloop.parse_response(0, json.dumps(error).encode())[0], "failed")
        model_text = {"verdict": "pass", "summary": "Quota exceeded is a string", "findings": []}
        self.assertEqual(devloop.parse_response(0, json.dumps(model_text).encode())[0],
                         "reviewed")
        for message in (
                "You’ve hit the rate limit for your plan. Upgrade your account or try again later.",
                "You've reached your free Grok Build usage limit for now. Get SuperGrok.",
                "subscription:free-usage-exhausted",
                "API error (status 429): unavailable"):
            with self.subTest(message=message):
                envelope = {"type": "error", "message": message}
                self.assertEqual(devloop.parse_response(1, json.dumps(envelope).encode())[0],
                                 "pending_quota")

    def test_legacy_parse_evidence_needs_exit_code_to_certify(self):
        sid = self.snap()
        raw = json.dumps({"stopReason": "end_turn", "modelUsage": {
            "verified-test-model": {"modelCalls": 1}},
            "structuredOutput": {"verdict": "pass", "summary": "Clear", "findings": []},
            "usage": {"input_tokens": 3}}).encode()
        report = {"snapshot": sid, "task": "T01", "provider": "grok", "attempt": 1,
                  "model": "verified-test-model", "effort": "medium", "status": "failed",
                  "manifest_sha256": devloop.load_snapshot(self.repo, sid)[2],
                  "error": {"code": "invalid_response"}}
        devloop.save_final_report(self.repo, devloop.report_path(self.repo, sid, "grok"),
                                  report, raw)
        audit = devloop.reparse(self.repo, sid, "grok", 1)
        self.assertFalse(audit["certified"])
        self.assertEqual(devloop.load_report(devloop.report_path(self.repo, sid, "grok"))["status"], "failed")
        certified = devloop.reparse(self.repo, sid, "grok", 1, exit_code=0)
        self.assertTrue(certified["certified"])
        self.assertEqual(devloop.read_json(devloop.attempt_path(self.repo, report))["status"], "failed")
        self.assertEqual(devloop.status(self.repo)["snapshots"][0]["reviews"]["grok"]["status"],
                         "reviewed")

    def test_retry_retains_each_attempt_and_backlog_row(self):
        sid = self.snap()
        self.fake_output("")
        first = devloop.review(self.repo, sid, "grok")
        self.fake_output({"verdict": "pass", "summary": "Clear", "findings": []})
        second = devloop.review(self.repo, sid, "grok", force=True)
        self.assertEqual(first["status"], "failed")
        self.assertEqual(second["status"], "reviewed")
        first_file = self.repo / ".devloop/reviews" / sid / "grok-attempt-1.json"
        second_file = self.repo / ".devloop/reviews" / sid / "grok-attempt-2.json"
        self.assertEqual(devloop.read_json(first_file)["status"], "failed")
        self.assertEqual(devloop.read_json(second_file)["status"], "reviewed")
        self.assertEqual(len(devloop.read_json(devloop.backlog_path(self.repo))["entries"]), 2)

    def test_transport_is_enforced_for_review(self):
        self.fake_output({"verdict": "pass", "summary": "Clear", "findings": []})
        path = self.repo / "docs/gui/automation/config.json"
        cfg = json.loads(path.read_text())
        cfg["providers"]["grok"]["transport"] = "unsafe"
        path.write_text(json.dumps(cfg))
        sid = self.snap()
        result = devloop.review(self.repo, sid, "grok")
        self.assertEqual(result["status"], "pending_setup")
        self.assertEqual(result["error"]["code"], "unsupported_transport")

    def test_probe_reports_ready_auth_and_uses_configured_t3_home(self):
        self.fake_output({})
        cfg_path = self.repo / "docs/gui/automation/config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["providers"]["gemini"] = {
            "model": "gemini-3.8-flash-medium", "effort": "medium",
            "transport": "antigravity_acp", "t3_home": str(self.repo / "custom-t3")}
        cfg_path.write_text(json.dumps(cfg))
        adapter = self.repo / "tools/devloop_antigravity.py"
        adapter.parent.mkdir()
        adapter.write_text("import json, sys\n"
                           "assert '--t3-home' in sys.argv\n"
                           f"assert {str(self.repo / 'custom-t3')!r} in sys.argv\n"
                           "print(json.dumps({'status':'ready','model':'gemini-3.8-flash-medium','auth_mode':'oauth-personal'}))\n")
        found = devloop.doctor(self.repo, probe=True)
        self.assertEqual(found["providers"]["gemini"]["status"], "ready")
        self.assertEqual(found["providers"]["gemini"]["auth"], "oauth-personal")

    def test_grok_overlay_is_local_and_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            target = devloop.grok_overlay({"model": "grok-4.7-build-fast"}, Path(directory))
            value = target.read_text()
            self.assertIn('allowed_models = ["grok-4.7-build-fast"]', value)
            self.assertIn("max_retries = 0", value)
            self.assertEqual(devloop.safe_environment(target)["GROK_CONFIG_PATH"], str(target))
            argv = devloop.grok_argv({"executable": str(self.fake),
                                     "model": "grok-4.7-build-fast", "effort": "medium",
                                     "transport": "grok_json"},
                                    target, Path(directory))
            self.assertEqual(argv[argv.index("--tools") + 1], "read_file")
            self.assertEqual(argv[argv.index("--disallowed-tools") + 1],
                             "read_file,search_tool,use_tool")
            self.assertIn("--system-prompt-override", argv)

    def test_grok_version_drift_is_setup_failure(self):
        self.fake_output({})
        with self.assertRaises(devloop.DevloopError) as caught:
            self.real_verify(str(self.fake))
        self.assertEqual(caught.exception.code, "unsupported_cli_version")

    def test_missing_binary_is_setup_not_quota(self):
        sid = self.snap()
        result = devloop.review(self.repo, sid, "grok")
        self.assertEqual(result["status"], "pending_setup")
        self.assertEqual(result["error"]["code"], "missing_executable")

    def test_process_lock_prevents_a_second_writer(self):
        root = devloop.state_root(self.repo, create=True)
        with (root / ".lock").open("a+b") as file:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(devloop.DevloopError) as caught:
                self.snap()
            self.assertEqual(caught.exception.code, "busy")

    def test_stale_running_record_recovers_as_interrupted(self):
        sid = self.snap()
        path = devloop.report_path(self.repo, sid, "grok")
        devloop.atomic_json(path, {"snapshot": sid, "provider": "grok", "status": "running"})
        with devloop.locked(self.repo):
            pass
        self.assertEqual(devloop.read_json(path)["status"], "interrupted")

    def test_timeout_records_failed_and_cleans_run(self):
        sid = self.snap()
        marker = self.repo / "term-cleanup"
        self.fake.write_text(f"#!{sys.executable}\nimport signal, sys, time\n"
                             f"def finish(*_):\n    open({str(marker)!r}, 'w').write('done')\n    sys.exit(0)\n"
                             "signal.signal(signal.SIGTERM, finish)\n"
                             "while True: time.sleep(0.1)\n")
        self.fake.chmod(0o755)
        old = devloop.TIMEOUT
        devloop.TIMEOUT = 0.8
        try:
            result = devloop.review(self.repo, sid, "grok")
        finally:
            devloop.TIMEOUT = old
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "timeout")
        self.assertEqual(marker.read_text(), "done")
        self.assertFalse((self.repo / ".devloop/runs").exists())

    def test_stubborn_process_is_killed_after_grace(self):
        sid = self.snap()
        pid_file = self.repo / "stubborn-pid"
        self.fake.write_text(f"#!{sys.executable}\nimport os, signal, time\n"
                             f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
                             "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                             "while True: time.sleep(0.1)\n")
        self.fake.chmod(0o755)
        old = devloop.TIMEOUT
        devloop.TIMEOUT = 0.8
        try:
            result = devloop.review(self.repo, sid, "grok")
        finally:
            devloop.TIMEOUT = old
        self.assertEqual(result["error"]["code"], "timeout")
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)


if __name__ == "__main__":
    unittest.main()
