"""Manual preview corrections use the same bounded compiler without inference."""

import pytest
from pydantic import ValidationError

from packages.resume_core.rich_dependencies import dependency
from packages.resume_core.text_rewrite import RichRewriteEditRequest
from resume_api.gui_projects import ProjectFailure
from tests.recovery.test_plain_rewrite import block, text
from tests.recovery.test_rich_images_service import service
from tests.recovery.test_rich_synchronization import selection


def test_manual_preview_keeps_originals_and_facts_until_apply_and_calls_no_provider(tmp_path):
    instance, identifier = service(tmp_path)
    instance.provider_factory = lambda: pytest.fail("Manual corrections must not invoke a provider")
    workspace = instance.read(identifier).model_copy(deep=True)
    selected = selection(workspace, id="title", end=len(text(block(workspace, "title").content)))
    request = RichRewriteEditRequest(selection=selected, text="Lead Engineer 🚀")
    result = instance.rewrite_edit_preview(identifier, request).workspace
    assert text(block(result, "title").content) == "Lead Engineer 🚀"
    assert result.project.facts.records[0].title.raw_text == "Lead Engineer 🚀"
    assert result.project.facts.records[0].title.user_corrected
    assert result.project.facts.records[0].evidence == workspace.project.facts.records[0].evidence
    assert result.project.sources == workspace.project.sources
    assert instance.read(identifier) == workspace
    assert not instance.tasks


def test_manual_partial_preview_preserves_unselected_text_format_and_other_sections(tmp_path):
    instance, identifier = service(tmp_path)
    workspace = instance.read(identifier).model_copy(deep=True)
    result = instance.rewrite_edit_preview(identifier, RichRewriteEditRequest(selection=selection(workspace), text="Manual")).workspace
    changed = block(result, "narrative")
    assert text(changed.content) == "Manual" + text(block(workspace, "narrative").content)[6:]
    assert changed.content[0].styles.bold
    assert changed.children == block(workspace, "narrative").children
    for old in workspace.project.document.blocks():
        if old.id not in {"narrative", "job-section"}:
            assert block(result, old.id) == old
    assert instance.read(identifier) == workspace


@pytest.mark.parametrize("change", ["checksum", "dependency", "deleted"])
def test_manual_preview_rejects_stale_selection(tmp_path, change):
    instance, identifier = service(tmp_path)
    workspace = instance.read(identifier)
    selected = selection(workspace)
    if change == "checksum":
        selected.text_sha256 = "0" * 64
    elif change == "dependency":
        selected.capture.dependencies = [dependency(workspace, "block", "narrative")]
        block(workspace, "narrative").revision += 1
    else:
        block(workspace, "job-section").children.clear()
    instance.workspaces[identifier] = workspace
    instance.persist(identifier)
    with pytest.raises(ProjectFailure):
        instance.rewrite_edit_preview(identifier, RichRewriteEditRequest(selection=selected, text="Manual"))


@pytest.mark.parametrize("replacement", ["", " \n", "bad\x00text", "x" * 65537])
def test_manual_preview_rejects_invalid_replacement(tmp_path, replacement):
    instance, identifier = service(tmp_path)
    with pytest.raises(ValidationError):
        RichRewriteEditRequest(selection=selection(instance.read(identifier)), text=replacement)


def test_manual_preview_rejects_cross_block_scope(tmp_path):
    instance, identifier = service(tmp_path)
    selected = selection(instance.read(identifier))
    selected.block_ids.append("title")
    selected.head.block_id = "title"
    with pytest.raises(ValidationError):
        RichRewriteEditRequest(selection=selected, text="Manual")
