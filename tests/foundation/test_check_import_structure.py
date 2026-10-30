"""The PDF corpus audit keeps extracted CV text out of the repository."""

from argparse import Namespace
from pathlib import Path

import pytest

from tools import check_import_structure as audit


@pytest.mark.parametrize("path", ["docs/gui/handoffs/X/views", "tests/views", ".private/../docs/views", "views"])
def test_a_repository_folder_is_refused(path):
    with pytest.raises(SystemExit, match="inside the repository"):
        audit.require_private_output(audit.ROOT / path)


def test_a_link_into_the_repository_is_refused(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(audit.ROOT / "docs")
    with pytest.raises(SystemExit, match="inside the repository"):
        audit.require_private_output(link / "views")


@pytest.mark.parametrize("path", [".private/resume-qa/views", "experiments/views"])
def test_the_ignored_private_folders_are_allowed(path):
    audit.require_private_output(audit.ROOT / path)


def test_a_folder_outside_the_repository_is_allowed(tmp_path):
    audit.require_private_output(tmp_path / "views")


@pytest.mark.parametrize("views,summary", [("docs/views", None), (None, "docs/summary.json")], ids=["views", "summary"])
def test_a_refused_path_stops_the_run_before_any_input_or_output(tmp_path, views, summary):
    args = Namespace(inputs=tmp_path / "missing.json", views=audit.ROOT / views if views else tmp_path / "views",
                     summary=audit.ROOT / summary if summary else tmp_path / "summary.json")
    with pytest.raises(SystemExit, match="inside the repository"):
        audit.check(args)
    assert list(tmp_path.iterdir()) == [] and not Path(audit.ROOT / "docs/views").exists()
