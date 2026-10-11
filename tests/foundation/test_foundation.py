"""Foundation checks independent of future application features."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import socket

import pytest

from tests.support.foundation import (
    FROZEN_DATE,
    CountingContentProvider,
    ForbiddenContentProvider,
    assert_no_content_calls,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/synthetic"


def test_synthetic_manifest_has_independent_source_evidence(frozen_clock) -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["asOf"] == frozen_clock.today.isoformat() == FROZEN_DATE.isoformat()
    assert {entry["name"] for entry in manifest["fixtures"]} == {"short", "overlap"}
    for entry in manifest["fixtures"]:
        source = (FIXTURES / entry["file"]).read_bytes()
        assert hashlib.sha256(source).hexdigest() == entry["sha256"]
        text = source.decode("utf-8")
        for metric in entry["metrics"]:
            assert metric["quote"] in text
        for forbidden in entry["mustNotInfer"]:
            assert forbidden not in text
    short, overlap = manifest["fixtures"]
    assert short["metrics"][0]["meaning"] == "team_growth"
    assert overlap["metrics"][0]["meaning"] == "team_size"
    assert overlap["nestedProjects"][0]["parentEmployer"] == "Cedar Works"


def test_provider_helpers_count_and_forbid_calls(temp_root: Path, fixture_random) -> None:
    assert temp_root.is_dir()
    assert fixture_random.sample(range(10), 4) == [5, 3, 0, 9]
    provider = CountingContentProvider({"summary": "Synthetic"})
    assert provider.generate("normalize_semantics", {"source": "fictional"}) == {"summary": "Synthetic"}
    assert provider.generate("draft_prose", {"factIds": ["fact_1"]}) == {"summary": "Synthetic"}
    assert provider.count("normalize_semantics") == 1
    assert provider.count("draft_prose") == 1
    assert provider.count("rewrite_prose") == 0
    assert_no_content_calls(lambda _: temp_root.name)
    with pytest.raises(AssertionError, match="unexpected content operation"):
        ForbiddenContentProvider().generate("rewrite_prose", {})


def test_routine_python_network_is_denied() -> None:
    with pytest.raises(AssertionError, match="network access is forbidden"):
        socket.create_connection(("example.invalid", 443))


def test_deterministic_modules_do_not_import_provider() -> None:
    paths = [*sorted((ROOT / "packages/resume_core").rglob("*.py")),
             *sorted((ROOT / "spikes/render").glob("*.py")),
             *sorted((ROOT / "skills/format-resume/scripts").glob("*.py")),
             *(ROOT / "services/api/src/resume_api" / name for name in
               ("extracting.py", "rendering.py", "lifecycle.py", "cli/process_runner.py"))]
    assert paths
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        assert all("provider" not in ast.unparse(node).lower() for node in imported), path
