"""Private selection and reuse never discover or rewrite normal projects."""

import json

import pytest

from packages.resume_core.rules import RulesStore
from packages.resume_core.preferences import PreferencesStore
from tools.gui_native_cycle import MARKER, select_store, verified_bytes


@pytest.fixture
def inputs(tmp_path):
    tmp_path.chmod(0o700)
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    rules = RulesStore(tmp_path / "rules")
    value = rules.load()
    return tmp_path, profile, rules.path, value.sha256


def test_new_and_reused_store_preserve_saved_rules_and_projects(inputs):
    parent, profile, rules, digest = inputs
    root = select_store(parent / "store", rules, digest, "selected", profile, reuse=False)
    snapshot = root / "project-snapshot"
    snapshot.write_bytes(b"unchanged")
    assert select_store(root, rules, digest, "selected", profile, reuse=True) == root
    assert snapshot.read_bytes() == b"unchanged"
    assert RulesStore(root).load().sha256 == digest
    assert PreferencesStore(root).load().selected_model == "selected"
    assert json.loads((root / MARKER).read_text())["model"] == "selected"


def test_reuse_requires_existing_owned_store_and_matching_configuration(inputs):
    parent, profile, rules, digest = inputs
    with pytest.raises(FileNotFoundError):
        select_store(parent / "missing", rules, digest, "selected", profile, reuse=True)
    root = select_store(parent / "store", rules, digest, "selected", profile, reuse=False)
    with pytest.raises(ValueError, match="CYCLE_STORE_MISMATCH"):
        select_store(root, rules, digest, "other", profile, reuse=True)
    with pytest.raises(ValueError, match="CYCLE_STORE_EXISTS"):
        select_store(root, rules, digest, "selected", profile, reuse=False)
    alias = parent / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="CYCLE_UNSAFE_PATH"):
        select_store(alias, rules, digest, "selected", profile, reuse=True)


def test_wrong_rule_or_source_hash_cannot_create_a_store(inputs):
    parent, profile, rules, digest = inputs
    with pytest.raises(ValueError, match="CYCLE_RULES_MISMATCH"):
        select_store(parent / "store", rules, "0" * 64, "selected", profile, reuse=False)
    assert not (parent / "store").exists()
    source = parent / "source.pdf"
    source.write_bytes(b"source")
    source.chmod(0o600)
    with pytest.raises(ValueError, match="CYCLE_HASH_MISMATCH"):
        verified_bytes(source, "0" * 64)
