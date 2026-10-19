"""Plain rewrites keep model input small and apply only the captured selection."""

import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from packages.resume_core.models.rich_document import StyledText
from packages.resume_core.models.rich_mutations import RichSelection
from packages.resume_core.reasoning import ModelReasoning
from packages.resume_core.rich_mutations import apply_rich_mutation, inline_text
from packages.resume_core.rich_sync import RichRewriteRequest, exact_completion
from packages.resume_core.text_rewrite import (
    PlainTextReply, edited_inline, plain_prompt, plain_rewrite_steps, selection_targets, selection_text,
)
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.test_preferences import MetadataAdapter, application, client_session
from tests.recovery.test_rich_images_service import service
from tests.recovery.test_rich_persistence import without_sources
from tests.recovery.test_rich_synchronization import capture, completion, mutation, selection


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
    for value in ("", " \n", "invalid\x00text", "\ud800"):
        with pytest.raises((ValidationError, UnicodeError)):
            PlainTextReply(text=value)
    link = block(workspace, "narrative").content[-1]
    assert link.type == "link"
    assert edited_inline([link], inline_text(link)) == [link]


def test_caption_and_code_edits_keep_assets_and_language():
    from packages.resume_core.models.rich_document import CodeBlock
    from tests.recovery.test_rich_persistence import image_asset
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


@pytest.mark.asyncio
async def test_request_contains_only_plain_selection_instruction_and_captured_reasoning(tmp_path):
    instance, identifier = service(tmp_path)
    from packages.resume_core.preferences import PreferencesStore
    instance.preferences = PreferencesStore(instance.rules.root)
    instance.preferences.select_model("fixture")
    instance.preferences.select_rewrite_reasoning("fixture", "low")
    selected = selection(instance.read(identifier))
    expected = selection_text(selection_targets(instance.read(identifier), selected))
    class Capture(CreationProvider):
        def generate(self, request, *args):
            assert request.text == plain_prompt("Make clearer.", expected)
            assert request.result_type is PlainTextReply
            assert request.policy.reasoning_effort == "low" and not request.policy.allow_repair
            return super().generate(request, *args)
    provider = Capture()
    instance.provider_factory = lambda: (provider, "fixture")
    reply = await instance.rewrite_rich(identifier, RichRewriteRequest(selection=selected, instruction="Make clearer."))
    assert len(provider.calls) == 1 and reply.workspace.sync_records[-1].ready


@pytest.mark.asyncio
async def test_unchanged_reply_finishes_without_proposal_or_fact_edit(tmp_path):
    instance, identifier = service(tmp_path)
    original = instance.read(identifier).project.model_copy(deep=True)
    selected = selection(instance.read(identifier))
    class Unchanged(CreationProvider):
        def generate(self, request, *args):
            response = super().generate(request, *args)
            response.value.text = request.text.split("\n\nSelected text:\n", 1)[1]
            return response
    instance.provider_factory = lambda: (Unchanged(), "fixture")
    reply = await instance.rewrite_rich(identifier, RichRewriteRequest(selection=selected, instruction="Keep it."))
    record = reply.workspace.sync_records[-1]
    assert record.status == "applied" and not record.ready and record.proposed_steps == []
    assert reply.workspace.project.document == original.document
    assert reply.workspace.project.facts == original.facts and not instance.tasks


@pytest.mark.asyncio
async def test_reasoning_settings_use_reported_levels_persist_and_reject_stale_model(tmp_path):
    class Adapter(MetadataAdapter):
        def inspect(self, *args, **kwargs):
            return replace(super().inspect(*args, **kwargs), reasoning={
                "model-a": ModelReasoning(supported=["low", "medium"], default="medium"),
                "model-b": ModelReasoning(supported=["high"], default="high")})
    adapter, provider = Adapter(), CreationProvider()
    app = application(tmp_path, adapter, provider)
    async with client_session(app) as client:
        state = (await client.post("/v1/host/status", json={})).json()
        assert state["modelReasoning"]["model-a"]["supported"] == ["low", "medium"]
        await client.post("/v1/host/select", json={"model": "model-a"})
        saved = await client.put("/v1/settings/rewrite-reasoning", json={"model": "model-a", "effort": "low"})
        assert saved.status_code == 200 and saved.json()["rewriteReasoningEffort"] == "low"
        for payload in ({"model": "model-a", "effort": "high"}, {"model": "model-b", "effort": "high"}):
            assert (await client.put("/v1/settings/rewrite-reasoning", json=payload)).status_code == 409
        assert (await client.get("/v1/settings/preferences")).json()["rewriteReasoningEffort"] == "low"
    assert provider.calls == [] and adapter.inspections == 1
    assert json.loads((tmp_path / "FoldCV/preferences.json").read_text())["rewriteReasoningEffort"] == "low"
