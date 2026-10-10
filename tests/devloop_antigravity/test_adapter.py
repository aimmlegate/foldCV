"""Behavior checks for the isolated ACP review adapter."""

import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("devloop_antigravity", ROOT / "tools" / "devloop_antigravity.py")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)
FAKE = Path(__file__).with_name("fake_acp.py")


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FAKE.chmod(FAKE.stat().st_mode | stat.S_IXUSR)

    def invoke(self, scenario="success", mode="review", timeout=5):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profile"
            profile.mkdir()
            with patch.dict(os.environ, {"FAKE_ACP_SCENARIO": scenario}):
                return adapter.run(mode, Path(directory), adapter.MODEL,
                                   "Review this patch." if mode == "review" else None,
                                   timeout, 1024, installation=(profile, FAKE, FAKE))

    def test_review_and_probe(self):
        self.assertEqual(self.invoke()["response"], "Review looks fine.")
        self.assertEqual(self.invoke(mode="probe")["status"], "ready")

    def test_model_must_be_offered(self):
        with self.assertRaises(adapter.ReviewError) as context:
            self.invoke("model_missing")
        self.assertEqual(context.exception.code, "MODEL_UNAVAILABLE")

    def test_mismatched_response_and_early_eof(self):
        for scenario in ("duplicate", "eof"):
            with self.subTest(scenario=scenario), self.assertRaises(adapter.ReviewError) as context:
                self.invoke(scenario)
            self.assertEqual(context.exception.code, "PROTOCOL_ERROR")

    def test_tool_requests_and_updates_are_rejected(self):
        for scenario in ("callback", "tool_update"):
            with self.subTest(scenario=scenario), self.assertRaises(adapter.ReviewError) as context:
                self.invoke(scenario)
            self.assertEqual(context.exception.code, "PROTOCOL_ERROR")

    def test_timeout(self):
        with self.assertRaises(adapter.ReviewError) as context:
            self.invoke("timeout", timeout=1)
        self.assertEqual(context.exception.code, "TIMEOUT")

    def test_wire_limit_counts_non_response_updates(self):
        with self.assertRaises(adapter.ReviewError) as context:
            self.invoke("wire_limit")
        self.assertEqual(context.exception.code, "PROTOCOL_ERROR")

    def test_quota_requires_provider_error(self):
        with self.assertRaises(adapter.ReviewError) as context:
            self.invoke("quota")
        self.assertEqual(context.exception.code, "QUOTA_EXHAUSTED")
        self.assertEqual(context.exception.retry_after, "600")
        self.assertEqual(self.invoke("quota_text")["response"], "RESOURCE_EXHAUSTED")

    def test_profile_rejects_active_hooks(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            config = profile / "config"
            config.mkdir()
            (config / "hooks.json").write_text('{"hooks":{"before":["danger"]}}')
            with self.assertRaises(adapter.ReviewError) as context:
                adapter._profile_safe(profile)
        self.assertEqual(context.exception.code, "UNSAFE_PROFILE")


if __name__ == "__main__":
    unittest.main()
