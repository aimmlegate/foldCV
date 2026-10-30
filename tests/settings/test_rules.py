"""Shared Rules persist privately with a revision, two presets and safe failures."""

import stat
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from packages.resume_core.rules import DEFAULT_RULES, FIRST_PRESET, RulesFailure, RulesStore, captured_rules, presets
from packages.resume_core import rules as rules_module
from packages.resume_core.storage import data_root

# The default rules.md text of 4cc6523e, as stores seeded before D111 hold it.
LEGACY_DEFAULT = Path(__file__).parents[1] / "fixtures/synthetic/rules/default-4cc6523e.md"


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
    changed = store.save(initial.markdown.replace("лишние слова", "вводные слова"), initial.revision)
    assert changed.revision == 2 and changed.sha256 != initial.sha256
    assert initial.revision == 1 and "лишние слова" in initial.markdown
    assert RulesStore(store.root).load() == changed
    assert store.save(changed.markdown, changed.revision) == changed
    assert "foldcv-rules:v1" not in changed.markdown
    assert not list(store.root.glob(".foldcv-write-*"))
    with pytest.raises(ValidationError):
        initial.markdown = "mutated"


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
    store.path.write_text(store.path.read_text().replace("лишние слова", "вводные слова"))
    with pytest.raises(RulesFailure, match="RULES_LOAD_FAILED"):
        store.load()
    assert "вводные слова" in store.path.read_text()


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


def test_rule_seed_holds_only_the_two_presets():
    assert DEFAULT_RULES.startswith("## Preset: shorten\n")
    assert FIRST_PRESET.search(DEFAULT_RULES).start() == 0 and "Editorial" not in DEFAULT_RULES
    assert set(presets(DEFAULT_RULES)) == {"shorten", "clarify"}
    for excluded in ["scripts/", "PDF", "branded footer", "CODEX_HOME", "0700"]:
        assert excluded not in DEFAULT_RULES
    assert data_root().parts[-2:] == ("Application Support", "FoldCV")
    normalized = captured_rules(DEFAULT_RULES.replace("\n", "\r\n"), 1)
    assert normalized.markdown == DEFAULT_RULES
    with pytest.raises(RulesFailure, match="RULES_TOO_LARGE"):
        captured_rules(DEFAULT_RULES + "x" * 32768, 1)


def stored(store, markdown, revision):
    rules = captured_rules(markdown, revision)
    store.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    store.path.write_text(f"<!-- foldcv-rules:v1 revision={revision} sha256={rules.sha256} -->\n" + markdown)
    store.path.chmod(0o600)
    return rules


def test_an_unchanged_old_default_loses_its_editorial_text_once(store):
    legacy = LEGACY_DEFAULT.read_text(encoding="utf-8")
    presets_part = legacy[FIRST_PRESET.search(legacy).start():]
    stored(store, legacy, 3)
    migrated = store.load()
    assert (migrated.revision, migrated.markdown) == (4, presets_part)
    assert RulesStore(store.root).load() == migrated
    # Edited presets after the old text are kept byte for byte.
    stored(store, legacy.replace("лишние слова", "вводные слова"), 7)
    assert store.load().markdown == presets_part.replace("лишние слова", "вводные слова")


def test_editorial_text_a_user_wrote_stays(store):
    legacy = LEGACY_DEFAULT.read_text(encoding="utf-8")
    edited = legacy.replace("15 years", "20 years")
    stored(store, edited, 2)
    assert store.load() == captured_rules(edited, 2)
    custom = "Мои правила.\n\n" + DEFAULT_RULES
    stored(store, custom, 5)
    assert store.load() == captured_rules(custom, 5)
    assert store.path.read_text().endswith(custom)
