"""Shared Rules persist privately, capture once and drive all GUI prompt kinds."""

from pathlib import Path
import json
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from packages.resume_core.gui_prompts import content_input
from packages.resume_core.rules import DEFAULT_RULES, RulesFailure, RulesStore, captured_rules, presets
from packages.resume_core import rules as rules_module
from packages.resume_core.storage import data_root


@pytest.fixture
def store(tmp_path):
    return RulesStore(tmp_path / "FoldCV")


def test_shared_rules_persist_revision_and_presets_at_one_private_path(store):
    initial = store.load()
    assert initial.revision == 1
    assert store.path.name == "rules.md"
    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert set(presets(initial.markdown)) == {"shorten", "clarify"}
    changed = store.save(initial.markdown.replace("15 years", "20 years"), initial.revision)
    assert changed.revision == 2 and changed.sha256 != initial.sha256
    assert initial.revision == 1 and "15 years" in initial.markdown
    assert RulesStore(store.root).load() == changed
    assert store.save(changed.markdown, changed.revision) == changed
    assert "foldcv-rules:v1" not in changed.markdown
    assert not list(store.root.glob(".foldcv-write-*"))
    with pytest.raises(ValidationError):
        initial.markdown = "mutated"


@pytest.mark.parametrize("kind", ["normalize_semantics", "draft_prose", "rewrite_prose", "reconcile_edits"])
def test_every_gui_prompt_uses_captured_rules_without_legacy_policy(kind, store):
    initial = store.load()
    payload = {"activeJobs": [{"id": "recent"}, {"id": "2008-2009"}]}
    captured = json.loads(content_input(kind, payload, initial))
    changed = store.save(initial.markdown.replace("15 years", "20 years"), 1)
    current = json.loads(content_input(kind, payload, changed))
    assert captured["rulesUsed"]["revision"] == 1
    assert current["rulesUsed"]["revision"] == 2
    assert "15 years" in captured["rulesUsed"]["markdown"]
    assert "20 years" in current["rulesUsed"]["markdown"]
    assert current["input"] == payload
    assert "15 years" not in json.dumps(current["constraints"])
    assert "recent-project prose" not in json.dumps(current)
    assert any("untrusted" in constraint for constraint in current["constraints"])
    assert any("quantities" in constraint for constraint in current["constraints"])
    assert any("requested JSON schema" in constraint for constraint in current["constraints"])


@pytest.mark.parametrize("markdown", [
    "Only policy", "## Preset: shorten\nShorten", "## Preset: shorten\n\n## Preset: clarify\nClarify",
    "## Preset: shorten\nOne\n## Preset: shorten\nTwo\n## Preset: clarify\nThree",
    "```\n## Preset: shorten\nShorten\n## Preset: clarify\nClarify\n```",
    "## Preset: shorten \nShorten\n## Preset: clarify\nClarify",
])
def test_invalid_presets_never_create_a_revision(store, markdown):
    initial = store.load()
    before = store.path.read_bytes()
    with pytest.raises(RulesFailure, match="RULES_PRESETS_REQUIRED"):
        store.save(markdown, initial.revision)
    assert store.path.read_bytes() == before
    assert store.load() == initial


def test_rule_write_failure_and_stale_save_keep_accepted_rules(store, monkeypatch):
    initial = store.load()
    with pytest.raises(RulesFailure, match="RULES_STALE"):
        store.save(initial.markdown + "\nNew policy", 2)

    def fail(*_args):
        raise OSError("private storage detail")

    monkeypatch.setattr(rules_module, "atomic_write", fail)
    with pytest.raises(RulesFailure, match="RULES_SAVE_FAILED") as error:
        store.save(initial.markdown + "\nNew policy", 1)
    assert "private storage detail" not in str(error.value)
    assert store.load() == initial


def test_symlink_rules_and_root_fail_without_touching_other_files(tmp_path):
    outside = tmp_path / "outside"
    outside.write_text("keep")
    root = tmp_path / "FoldCV"
    root.mkdir()
    (root / "rules.md").symlink_to(outside)
    with pytest.raises(RulesFailure, match="RULES_UNSAFE_STORAGE"):
        RulesStore(root).load()
    assert outside.read_text() == "keep"
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(RulesFailure, match="RULES_UNSAFE_STORAGE"):
        RulesStore(alias).load()


def test_corrupt_rule_hash_is_not_silently_replaced(store):
    store.load()
    store.path.write_text(store.path.read_text().replace("15 years", "20 years"))
    with pytest.raises(RulesFailure, match="RULES_LOAD_FAILED"):
        store.load()
    assert "20 years" in store.path.read_text()


def test_shared_rule_save_serializes_concurrent_revisions(store):
    initial = store.load()

    def save(index):
        try:
            return RulesStore(store.root).save(initial.markdown + f"\nPolicy {index}", 1).revision
        except RulesFailure as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, [1, 2]))
    assert sorted(outcomes, key=str) == [2, "RULES_STALE"]
    assert store.load().revision == 2


def test_rule_seed_has_no_workflow_pdf_footer_or_storage_commands():
    assert "first-person" in DEFAULT_RULES and "15 years" in DEFAULT_RULES
    assert "first substantive" in DEFAULT_RULES
    assert "## Preset: shorten" in DEFAULT_RULES and "## Preset: clarify" in DEFAULT_RULES
    for excluded in ["scripts/", "PDF", "mail@example.com", "branded footer", "CODEX_HOME", "0700"]:
        assert excluded not in DEFAULT_RULES
    assert data_root().parts[-2:] == ("Application Support", "FoldCV")
    normalized = captured_rules(DEFAULT_RULES.replace("\n", "\r\n"), 1)
    assert normalized.markdown == DEFAULT_RULES
    with pytest.raises(RulesFailure, match="RULES_TOO_LARGE"):
        captured_rules(DEFAULT_RULES + "x" * 32768, 1)
