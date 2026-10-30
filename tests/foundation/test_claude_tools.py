"""The Claude evidence tools wipe a profile, so they never run on the app's data root."""

import sys

import pytest

from tools import claude_mp00 as mp00
from tools import claude_mp05 as mp05


@pytest.fixture
def app_data(tmp_path, monkeypatch):
    root = tmp_path / "FoldCV"
    root.mkdir()
    monkeypatch.setattr(mp00, "APP_DATA", root)
    monkeypatch.setattr(mp00, "PROFILE_ROOT", None)
    monkeypatch.setattr(mp00, "OPERATIONS", None)
    monkeypatch.setattr(mp05, "DATA", None)
    return root


def run(module, monkeypatch, command, *options):
    monkeypatch.setattr(sys, "argv", ["tool", *options, command])
    module.main()


def stub(module, monkeypatch, name, calls):
    monkeypatch.setattr(module, name, lambda _args: calls.append(name))


@pytest.mark.parametrize("module,command", [(mp00, "status"), (mp05, "schemas")], ids=["mp00", "mp05"])
def test_a_tool_without_a_data_root_does_not_start(app_data, monkeypatch, module, command):
    calls = []
    stub(module, monkeypatch, command, calls)
    with pytest.raises(SystemExit) as stopped:
        run(module, monkeypatch, command)
    assert stopped.value.code == 2 and calls == []


@pytest.mark.parametrize("module,command", [(mp00, "status"), (mp05, "schemas")], ids=["mp00", "mp05"])
def test_the_apps_data_root_is_refused_even_through_a_link(app_data, tmp_path, monkeypatch, module, command):
    calls = []
    stub(module, monkeypatch, command, calls)
    link = tmp_path / "link"
    link.symlink_to(app_data)
    for root in (app_data, link):
        with pytest.raises(SystemExit, match="separate folder"):
            run(module, monkeypatch, command, "--data-root", str(root))
    assert calls == []


def test_mp00_keeps_its_profile_and_operations_under_a_separate_root(app_data, tmp_path, monkeypatch):
    calls = []
    stub(mp00, monkeypatch, "status", calls)
    root = tmp_path / "separate"
    run(mp00, monkeypatch, "status", "--data-root", str(root))
    assert calls == ["status"]
    assert mp00.PROFILE_ROOT.parent == mp00.OPERATIONS.parent == root.resolve()


def test_mp05_opens_its_slots_under_a_separate_root(app_data, tmp_path, monkeypatch):
    calls = []
    stub(mp05, monkeypatch, "schemas", calls)
    root = tmp_path / "separate"
    run(mp05, monkeypatch, "schemas", "--data-root", str(root))
    assert calls == ["schemas"] and mp05.DATA == root.resolve()
