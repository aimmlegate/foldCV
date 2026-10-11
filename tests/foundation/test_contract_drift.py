"""Generation checks detect added files and leave the original snapshot intact."""

from pathlib import Path
import subprocess

import pytest

from tools import check_contract_drift as drift


@pytest.fixture
def generated_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(drift, "ROOT", tmp_path)
    monkeypatch.setattr(drift, "WEB", tmp_path / "apps/web")
    paths = []
    for folder, suffix in [("contracts/json-schema", ".json"), ("apps/web/src/contracts/generated", ".ts")]:
        directory = tmp_path / folder
        directory.mkdir(parents=True)
        for index in range(18):
            path = directory / f"contract-{index}{suffix}"
            path.write_bytes(f"original {index}".encode())
            paths.append(path)
    catalog = tmp_path / "contracts/technology-catalog.json"
    catalog.write_bytes(b"original catalog")
    return {path: path.read_bytes() for path in paths + [catalog]}


@pytest.mark.parametrize("change", ["add", "nested", "edit", "delete", "fail"])
def test_drift_restores_changed_deleted_and_new_files(generated_tree, monkeypatch, change):
    first = next(iter(generated_tree))
    added = first.parent / ("nested/extra.txt" if change == "nested" else "extra.schema.json")

    def generate(*args, **kwargs):
        if change in {"add", "nested", "fail"}:
            added.parent.mkdir(parents=True, exist_ok=True)
            added.write_bytes(b"unexpected output")
        if change in {"edit", "fail"}:
            first.write_bytes(b"changed")
        if change == "delete":
            first.unlink()
        if change == "fail":
            raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(drift.subprocess, "run", generate)
    with pytest.raises((SystemExit, subprocess.CalledProcessError)) as error:
        drift.main()
    if change != "fail":
        assert "contract generation drift" in str(error.value)
    assert drift.generated_files() == set(generated_tree)
    assert {path: path.read_bytes() for path in drift.generated_files()} == generated_tree
    if change == "nested":
        assert not added.parent.exists()


def test_matching_generation_succeeds_without_rewriting_files(generated_tree, monkeypatch, capsys):
    monkeypatch.setattr(drift.subprocess, "run", lambda *args, **kwargs: None)
    drift.main()
    assert "37 generated" in capsys.readouterr().out
    assert {path: path.read_bytes() for path in drift.generated_files()} == generated_tree
