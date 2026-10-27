"""Plain selection text (text_rewrite): the model sees plain text and the reply replaces only the captured selection."""

import pytest
from pydantic import ValidationError

from packages.resume_core.models.rich_document import CodeBlock, StyledText
from packages.resume_core.models.rich_mutations import RichSelection
from packages.resume_core.rich_mutations import apply_rich_mutation, inline_text
from packages.resume_core.rich_sync import exact_completion
from packages.resume_core.text_rewrite import (
    PlainTextReply, edited_inline, plain_rewrite_steps, selection_targets, selection_text,
)
from tests.support.rich import capture, completion, image_asset, mutation, selection, without_sources


def block(workspace, identifier):
    return next(item for item in workspace.project.document.blocks() if item.id == identifier)


def text(content):
    return "".join(inline_text(span) for span in content)


def test_partial_unicode_selection_preserves_styles_links_children_and_outside_text():
    workspace = without_sources()
    original = block(workspace, "narrative")
    original.content[0].text = "Styled 🚀 text "
    selected = selection(workspace, start=7, end=14)
    before = workspace.model_copy(deep=True)
    steps = plain_rewrite_steps(workspace, selected, PlainTextReply(text="clear text"))
    after, _ = apply_rich_mutation(workspace, mutation(workspace, steps))
    changed = block(after, "narrative")
    assert text(changed.content).startswith("Styled clear text ")
    assert changed.content[0].styles.bold
    assert changed.content[-1] == original.content[-1]
    assert changed.children == original.children and changed.provenance == original.provenance
    for item in before.project.document.blocks():
        if item.id not in {"narrative", "job-section"}:
            assert block(after, item.id) == item
    assert workspace == before


def test_plain_field_change_keeps_binding_and_updates_working_fact():
    workspace = without_sources()
    original = block(workspace, "title")
    selected = selection(workspace, id="title", end=len(text(original.content)))
    after, _ = apply_rich_mutation(workspace, mutation(workspace,
        plain_rewrite_steps(workspace, selected, PlainTextReply(text="Lead Engineer"))))
    assert all(span.type == "fact_field" for span in block(after, "title").content)
    steps, conflicts = exact_completion(after, completion())
    assert steps and not conflicts
    updated, _ = apply_rich_mutation(after, mutation(after, steps, id="working-fact"))
    assert updated.project.facts.records[0].title.raw_text == "Lead Engineer"


def test_multiblock_plain_text_can_keep_paragraphs_or_merge_selection():
    workspace = without_sources()
    first = block(workspace, "narrative")
    first.content = [StyledText(type="text", text="First paragraph", styles={"bold": True})]
    first.children = []
    second = first.model_copy(deep=True)
    second.id, second.content = "second-text", [StyledText(type="text", text="Second paragraph", styles={})]
    block(workspace, "job-section").children.append(second)
    selected = RichSelection.model_validate({"kind": "text", "blockIds": [first.id, second.id],
        "anchor": {"blockId": first.id, "cellId": None, "offset": 0},
        "head": {"blockId": second.id, "cellId": None, "offset": 16}, "capture": capture(), "textSha256": "0" * 64})
    assert selection_text(selection_targets(workspace, selected)) == "First paragraph\n\nSecond paragraph"
    kept, _ = apply_rich_mutation(workspace, mutation(workspace,
        plain_rewrite_steps(workspace, selected, PlainTextReply(text="First edited\n\nSecond edited"))))
    assert text(block(kept, first.id).content) == "First edited"
    assert text(block(kept, second.id).content) == "Second edited"
    merged, _ = apply_rich_mutation(workspace, mutation(workspace,
        plain_rewrite_steps(workspace, selected, PlainTextReply(text="One sentence."))))
    assert text(block(merged, first.id).content) == "One sentence."
    assert second.id not in {item.id for item in merged.project.document.blocks()}


def test_selected_table_cells_keep_grid_and_unselected_text():
    workspace = without_sources()
    table = next(item for item in workspace.project.document.blocks() if item.type == "table")
    cells = [cell for row in table.content.rows for cell in row.cells]
    selected = RichSelection.model_validate({"kind": "table_cells", "blockIds": [table.id],
        "anchor": {"blockId": table.id, "cellId": cells[0].id, "offset": 1},
        "head": {"blockId": table.id, "cellId": cells[1].id, "offset": 2}, "capture": capture(), "textSha256": "0" * 64})
    after, _ = apply_rich_mutation(workspace, mutation(workspace,
        plain_rewrite_steps(workspace, selected, PlainTextReply(text="X\n\nY"))))
    updated = block(after, table.id)
    actual = [cell for row in updated.content.rows for cell in row.cells]
    assert [cell.id for cell in actual] == [cell.id for cell in cells]
    assert text(actual[0].content) == text(cells[0].content)[:1] + "X"
    assert text(actual[1].content) == "Y" + text(cells[1].content)[2:]
    assert actual[2:] == cells[2:]
    assert updated.content.column_widths == table.content.column_widths


def test_plain_noop_and_invalid_output_do_not_create_an_edit():
    workspace = without_sources()
    selected = selection(workspace)
    source = selection_text(selection_targets(workspace, selected))
    assert plain_rewrite_steps(workspace, selected, PlainTextReply(text=source)) == []
    for value in ("", " \n", "invalid\x00text", "\ud800", "x" * 65537):
        with pytest.raises((ValidationError, UnicodeError)):
            PlainTextReply(text=value)
    link = block(workspace, "narrative").content[-1]
    assert link.type == "link"
    assert edited_inline([link], inline_text(link)) == [link]


def test_caption_and_code_edits_keep_assets_and_language():
    workspace = without_sources()
    image_asset(workspace)
    image = block(workspace, "test-image")
    image.props.caption = [StyledText(type="text", text="Old caption", styles={"italic": True})]
    code = CodeBlock(type="code", id="code-text", revision=1, children=[], provenance=[],
        props={"language": "python"}, content="value = 1\nprint(value)")
    workspace.project.document.regions[2].blocks.append(code)
    for identifier, end, replacement in [(image.id, 3, "New"), (code.id, 9, "value = 2")]:
        selected = selection(workspace, id=identifier, end=end)
        after, _ = apply_rich_mutation(workspace, mutation(workspace,
            plain_rewrite_steps(workspace, selected, PlainTextReply(text=replacement))))
        if identifier == image.id:
            assert text(block(after, image.id).props.caption) == "New caption"
            assert block(after, image.id).props.asset_id == image.props.asset_id
            assert block(after, image.id).props.caption[0].styles.italic
        else:
            assert block(after, code.id).content == "value = 2\nprint(value)"
            assert block(after, code.id).props == code.props
        assert after.project.assets == workspace.project.assets
