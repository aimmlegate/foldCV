"""Offline checks for the development review ledger."""

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


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
        self.real_isolation = devloop.verify_grok_isolation
        devloop.verify_grok_isolation = lambda *_args: None
        self.addCleanup(lambda: setattr(devloop, "verify_grok_isolation", self.real_isolation))

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

    def test_status_reads_historical_attempt_zero_without_new_write(self):
        sid = self.snap()
        latest = devloop.report_path(self.repo, sid, "grok")
        archive = latest.with_name("grok-attempt-0.json")
        record = {"snapshot": sid, "provider": "grok", "status": "pending_setup",
                  "attempt": 0, "error": {"code": "unsupported_cli_version"}}
        backlog = {"version": 1, "entries": [{"snapshot": sid, "provider": "grok",
                                               "attempt": 0, "status": "pending_setup",
                                               "report": str(archive.relative_to(self.repo))}]}
        devloop.atomic_json(latest, record)
        devloop.atomic_json(archive, record)
        devloop.atomic_json(devloop.backlog_path(self.repo), backlog)
        entry = devloop.status(self.repo)["snapshots"][0]["reviews"]["grok"]
        self.assertEqual(entry["attempt"], 0)
        self.assertEqual(entry["report"], str(archive.relative_to(self.repo)))
        self.assertEqual(devloop.read_json(latest), record)
        self.assertEqual(devloop.read_json(archive), record)
        self.assertEqual(devloop.read_json(devloop.backlog_path(self.repo)), backlog)
        with self.assertRaises(devloop.DevloopError) as caught:
            devloop.save_final_report(self.repo, latest, record, b"new output")
        self.assertEqual(caught.exception.code, "invalid_attempt")

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

    def test_snapshot_task_limit_matches_loader(self):
        sid = devloop.snapshot(self.repo, "T" * 67, self.list)["snapshot"]
        self.assertEqual(len(sid), 100)
        self.assertEqual(devloop.load_snapshot(self.repo, sid)[1]["task"], "T" * 67)
        with self.assertRaises(devloop.DevloopError) as caught:
            devloop.snapshot(self.repo, "T" * 68, self.list)
        self.assertEqual(caught.exception.code, "invalid_task")

    def test_snapshot_storage_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            state = devloop.state_root(self.repo, create=True)
            (state / "snapshots").symlink_to(external, target_is_directory=True)
            for operation in (lambda: devloop.snapshot(self.repo, "T01", self.list),
                              lambda: devloop.load_snapshot(self.repo, "T01-" + "a" * 32),
                              lambda: devloop.status(self.repo)):
                with self.assertRaises(devloop.DevloopError) as caught:
                    operation()
                self.assertEqual(caught.exception.code, "unsafe_state_path")
            self.assertEqual(list(Path(external).iterdir()), [])

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

    def test_gemini_accepts_only_one_exact_json_fence(self):
        report = '{"verdict":"pass","summary":"Clear","findings":[]}'
        envelope = {"status": "completed", "model": "gemini-3.8-flash-medium",
                    "response": f"```json\n{report}\n```", "usage": None}
        def parsed():
            return devloop.parse_response(0, json.dumps(envelope).encode(), "gemini",
                                          "gemini-3.8-flash-medium")
        self.assertEqual(parsed()[0], "reviewed")
        for invalid in (f"Review:\n```json\n{report}\n```",
                        f"```json\n{report}\n```\nextra",
                        f"```json\n{report}\n```\n```json\n{report}\n```",
                        f"```json\n{report} trailing\n```",
                        f"```JSON\n{report}\n```"):
            with self.subTest(response=invalid):
                envelope["response"] = invalid
                self.assertEqual(parsed()[0], "failed")
        envelope["response"] = f"```json\n{report}\n```"
        envelope["model"] = "another-model"
        self.assertEqual(parsed()[0], "failed")

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
            devloop.grok_project_config(Path(directory))
            value = target.read_text()
            self.assertIn('allowed_models = ["grok-4.7-build-fast"]', value)
            self.assertIn("max_retries = 0", value)
            self.assertEqual(devloop.safe_environment(target)["GROK_CONFIG_PATH"], str(target))
            environment = devloop.safe_environment(target, Path(directory))
            self.assertEqual(environment["HOME"], os.environ["HOME"])
            self.assertIn('disabled = ["mcpmarket-me"]',
                          (Path(directory) / ".grok/config.toml").read_text())
            argv = devloop.grok_argv({"executable": str(self.fake),
                                     "model": "grok-4.7-build-fast", "effort": "medium",
                                     "transport": "grok_json"},
                                    target, Path(directory))
            self.assertEqual(argv[argv.index("--tools") + 1], "read_file")
            self.assertEqual(argv[argv.index("--disallowed-tools") + 1],
                             "read_file,search_tool,use_tool")
            self.assertIn("--system-prompt-override", argv)

    def test_grok_preflight_rejects_active_plugin_hook_or_mcp(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            overlay = devloop.grok_overlay({"model": "grok-4.7-build-fast"}, base)
            for key, value in (("plugins", {"name": "bad", "enabled": True}),
                               ("hooks", {"event": "start"}),
                               ("mcpServers", {"name": "bad"})):
                with self.subTest(key=key):
                    payload = {"cwd": directory, "plugins": [], "hooks": [],
                               "mcpServers": [{"name": "compat", "disabled": True}]}
                    payload[key].append(value)
                    self.fake_output(payload)
                    with self.assertRaises(devloop.DevloopError) as caught:
                        self.real_isolation({"executable": str(self.fake)}, base, overlay)
                    self.assertEqual(caught.exception.code, "unexpected_hooks_or_mcp")
            payload = {"cwd": directory, "plugins": [{"name": "off", "enabled": False}],
                       "hooks": [{"event": "off", "disabled": True}],
                       "mcpServers": [{"name": "compat", "disabled": True}]}
            self.fake_output(payload)
            self.real_isolation({"executable": str(self.fake)}, base, overlay)

    def test_known_mcpmarket_plugin_requires_exact_identity_and_files(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / ".claude/plugins/marketplaces/local-desktop-app-uploads/mcpmarket-me"
            sample = root / "hooks/hooks.json"
            sample.parent.mkdir(parents=True)
            sample.write_bytes(b"reviewed hook")
            plugin = {"name": "mcpmarket-me", "path": str(root), "scope": "user",
                      "enabled": True,
                      "provides": {"agents": 0, "hooks": True, "mcpServers": 1, "skills": 1}}
            digest = hashlib.sha256(sample.read_bytes()).hexdigest()
            with mock.patch.object(Path, "home", return_value=home), \
                    mock.patch.object(devloop, "safe_environment", return_value={"PATH": str(home)}), \
                    mock.patch.object(devloop, "MCPMARKET_PLUGIN_FILES",
                                      {"hooks/hooks.json": digest}):
                self.assertTrue(devloop.known_mcpmarket_plugin(plugin))
                self.assertFalse(devloop.known_mcpmarket_plugin({**plugin, "scope": "project"}))
                node = home / "node"
                node.touch()
                self.assertFalse(devloop.known_mcpmarket_plugin(plugin))
                node.unlink()
                sample.write_bytes(b"changed hook")
                self.assertFalse(devloop.known_mcpmarket_plugin(plugin))

    def test_grok_preflight_allows_only_known_plugin_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            overlay = devloop.grok_overlay({"model": "grok-4.7-build-fast"}, base)
            root = Path.home() / ".claude/plugins/marketplaces/local-desktop-app-uploads/mcpmarket-me"
            hook = {"event": "(plugin)", "hookType": "file", "matcher": None,
                    "target": str(root / "hooks/hooks.json"),
                    "source": {"path": str(root), "plugin_name": "mcpmarket-me",
                               "type": "plugin"}}
            payload = {"cwd": directory, "plugins": [{"name": "mcpmarket-me", "enabled": True}],
                       "hooks": [hook], "mcpServers": [{"name": "compat", "disabled": True}]}
            with mock.patch.object(devloop, "known_mcpmarket_plugin", return_value=True):
                self.fake_output(payload)
                self.real_isolation({"executable": str(self.fake)}, base, overlay)
                payload["hooks"].append({"event": "UserPromptSubmit"})
                self.fake_output(payload)
                with self.assertRaises(devloop.DevloopError) as caught:
                    self.real_isolation({"executable": str(self.fake)}, base, overlay)
                self.assertEqual(caught.exception.code, "unexpected_hooks_or_mcp")

    def test_active_hook_records_setup_debt_without_review_call(self):
        sid = self.snap()
        marker = self.repo / "review-invoked"
        self.fake.write_text(
            f"#!{sys.executable}\nimport json, pathlib, sys\n"
            "if 'inspect' in sys.argv:\n"
            "    print(json.dumps({'cwd': sys.argv[sys.argv.index('--cwd') + 1], "
            "'plugins': [], 'hooks': [{'event': 'start'}], 'mcpServers': []}))\n"
            "else:\n"
            f"    pathlib.Path({str(marker)!r}).write_text('called')\n")
        self.fake.chmod(0o755)
        devloop.verify_grok_isolation = self.real_isolation
        result = devloop.review(self.repo, sid, "grok")
        self.assertEqual(result["status"], "pending_setup")
        self.assertEqual(result["error"]["code"], "unexpected_hooks_or_mcp")
        self.assertFalse(marker.exists())

    def test_configured_timeout_is_bounded_and_used(self):
        cfg_path = self.repo / "docs/gui/automation/config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["providers"]["grok"]["timeout_seconds"] = 600
        cfg_path.write_text(json.dumps(cfg))
        self.fake_output({"verdict": "pass", "summary": "Clear", "findings": []})
        self.assertEqual(devloop.provider_config(self.repo, "grok")["timeout_seconds"], 600)
        for invalid in (0, 601, True, 3.5):
            with self.subTest(invalid=invalid):
                cfg["providers"]["grok"]["timeout_seconds"] = invalid
                cfg_path.write_text(json.dumps(cfg))
                with self.assertRaises(devloop.DevloopError) as caught:
                    devloop.provider_config(self.repo, "grok")
                self.assertEqual(caught.exception.code, "invalid_timeout")

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

    def test_recovery_accepts_matching_archived_result(self):
        sid = "T01-" + "a" * 32
        for status in ("failed", "pending_quota", "pending_setup", "interrupted"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                repo = Path(directory) / "repo"
                latest = repo / ".devloop/reviews" / sid / "grok.json"
                running = {"snapshot": sid, "provider": "grok", "status": "running",
                           "attempt": 1}
                final = {**running, "status": status, "error": {"code": "example"}}
                devloop.atomic_json(latest, running)
                devloop.atomic_json(latest.with_name("grok-attempt-1.json"), final)
                with devloop.locked(repo):
                    pass
                self.assertEqual(devloop.read_json(latest), final)
                self.assertEqual(devloop.read_json(devloop.backlog_path(repo))["entries"][0]
                                 ["status"], status)

    def test_recovery_accepts_valid_reviewed_archive(self):
        sid = self.snap()
        latest = devloop.report_path(self.repo, sid, "grok")
        running = {"snapshot": sid, "provider": "grok", "status": "running", "attempt": 1}
        final = {**running, "status": "reviewed",
                 "report": {"verdict": "pass", "summary": "Clear", "findings": [],
                            "usage": {"input_tokens": 1}},
                 "usage": {"output_tokens": 5}}
        devloop.atomic_json(latest, running)
        devloop.atomic_json(latest.with_name("grok-attempt-1.json"), final)
        with devloop.locked(self.repo):
            pass
        self.assertEqual(devloop.read_json(latest), final)
        entry = devloop.read_json(devloop.backlog_path(self.repo))["entries"][0]
        self.assertEqual((entry["status"], entry["verdict"]), ("reviewed", "pass"))

    def test_recovery_preserves_latest_for_malformed_reviewed_archive(self):
        sid = "T01-" + "a" * 32
        valid = {"verdict": "pass", "summary": "Clear", "findings": []}
        cases = (
            ("missing_report", {}), ("null_report", {"report": None}),
            ("empty_report", {"report": {}}),
            ("bad_verdict", {"report": {**valid, "verdict": "unknown"}}),
            ("blank_summary", {"report": {**valid, "summary": " "}}),
            ("pass_with_findings", {"report": {**valid, "findings": [{
                "severity": "high", "file": "x.py", "line": 1, "message": "Bug"}]}}),
            ("findings_without_items", {"report": {**valid, "verdict": "findings"}}),
            ("invalid_finding", {"report": {**valid, "verdict": "findings", "findings": [{
                "severity": "high", "file": "x.py", "line": True, "message": "Bug"}]}}),
            ("reviewed_with_error", {"report": valid, "error": {"code": "failure"}}),
            ("invalid_usage", {"report": valid, "usage": {"output_tokens": -1}}),
        )
        for label, change in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                repo = Path(directory) / "repo"
                latest = repo / ".devloop/reviews" / sid / "grok.json"
                running = {"snapshot": sid, "provider": "grok", "status": "running",
                           "attempt": 1}
                archived = latest.with_name("grok-attempt-1.json")
                final = {**running, "status": "reviewed", **change}
                devloop.atomic_json(latest, running)
                devloop.atomic_json(archived, final)
                with self.assertRaises(devloop.DevloopError) as caught:
                    with devloop.locked(repo):
                        pass
                self.assertEqual(caught.exception.code, "invalid_report")
                self.assertEqual(devloop.read_json(latest), running)
                self.assertEqual(devloop.read_json(archived), final)
                self.assertFalse(devloop.backlog_path(repo).exists())

    def test_recovery_preserves_latest_for_malformed_archive(self):
        sid = "T01-" + "a" * 32
        changes = ({"snapshot": "../../escape"}, {"provider": "gemini"},
                   {"attempt": 2}, {"attempt": True}, {"status": "running"},
                   {"status": "unknown"}, {"report": []},
                   {"report": {"verdict": "pass", "summary": "Clear", "findings": []}},
                   {"usage": {"output_tokens": 1}})
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                repo = Path(directory) / "repo"
                latest = repo / ".devloop/reviews" / sid / "grok.json"
                running = {"snapshot": sid, "provider": "grok", "status": "running",
                           "attempt": 1}
                final = {**running, "status": "failed", **change}
                devloop.atomic_json(latest, running)
                archived = latest.with_name("grok-attempt-1.json")
                devloop.atomic_json(archived, final)
                with self.assertRaises(devloop.DevloopError) as caught:
                    with devloop.locked(repo):
                        pass
                self.assertEqual(caught.exception.code, "invalid_report")
                self.assertEqual(devloop.read_json(latest), running)
                self.assertEqual(devloop.read_json(archived), final)
                self.assertFalse(devloop.backlog_path(repo).exists())
                self.assertFalse((repo / "escape/grok-attempt-1.json").exists())

    def test_recovery_rejects_record_path_escape_before_writing(self):
        for absolute in (False, True):
            with self.subTest(absolute=absolute), tempfile.TemporaryDirectory() as directory:
                repo = Path(directory) / "repo"
                outside = Path(directory) / "outside"
                malicious = str(outside) if absolute else "../../escape"
                latest = repo / ".devloop/reviews/valid/grok.json"
                latest.parent.mkdir(parents=True)
                record = {"snapshot": malicious, "provider": "grok", "status": "running"}
                devloop.atomic_json(latest, record)
                with self.assertRaises(devloop.DevloopError) as caught:
                    with devloop.locked(repo):
                        pass
                self.assertEqual(caught.exception.code, "invalid_report")
                self.assertEqual(devloop.read_json(latest), record)
                self.assertFalse((repo / "escape/grok-attempt-1.json").exists())
                self.assertFalse((outside / "grok-attempt-1.json").exists())

    def test_recovery_rejects_symlinked_attempt(self):
        sid = self.snap()
        latest = devloop.report_path(self.repo, sid, "grok")
        devloop.atomic_json(latest, {"snapshot": sid, "provider": "grok",
                                     "status": "running", "attempt": 1})
        external = self.repo / "external.json"
        external.write_text('{"status":"reviewed"}\n')
        archived = latest.with_name("grok-attempt-1.json")
        archived.symlink_to(external)
        with self.assertRaises(devloop.DevloopError) as caught:
            with devloop.locked(self.repo):
                pass
        self.assertEqual(caught.exception.code, "unsafe_state_path")
        self.assertEqual(external.read_text(), '{"status":"reviewed"}\n')

    def test_report_storage_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            state = devloop.state_root(self.repo, create=True)
            (state / "reviews").symlink_to(external, target_is_directory=True)
            with self.assertRaises(devloop.DevloopError) as caught:
                devloop.report_path(self.repo, "T01-" + "a" * 32, "grok")
            self.assertEqual(caught.exception.code, "unsafe_state_path")
            self.assertEqual(list(Path(external).iterdir()), [])

    def test_timeout_records_failed_and_cleans_run(self):
        sid = self.snap()
        marker = self.repo / "term-cleanup"
        self.fake.write_text(f"#!{sys.executable}\nimport signal, sys, time\n"
                             f"def finish(*_):\n    open({str(marker)!r}, 'w').write('done')\n    sys.exit(0)\n"
                             "signal.signal(signal.SIGTERM, finish)\n"
                             "while True: time.sleep(0.1)\n")
        self.fake.chmod(0o755)
        cfg_path = self.repo / "docs/gui/automation/config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["providers"]["grok"]["timeout_seconds"] = 1
        cfg_path.write_text(json.dumps(cfg))
        result = devloop.review(self.repo, sid, "grok")
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
        cfg_path = self.repo / "docs/gui/automation/config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["providers"]["grok"]["timeout_seconds"] = 1
        cfg_path.write_text(json.dumps(cfg))
        result = devloop.review(self.repo, sid, "grok")
        self.assertEqual(result["error"]["code"], "timeout")
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)


if __name__ == "__main__":
    unittest.main()
