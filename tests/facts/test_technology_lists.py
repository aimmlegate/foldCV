"""Facts keep explicit skill lists styled, punctuated and manually ordered."""

from io import BytesIO
from zipfile import ZipFile

from lxml import etree
from pydantic import TypeAdapter
import pytest

from packages.resume_core.models.rich_document import RichBlock, StyledText
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_panel import field_block, panel_mutation
from packages.resume_core.rich_presentation import authored_text, presentation
from packages.resume_core.rendering.rich_docx import render_rich_docx
from packages.resume_core.template_inverse import inverse_mutation
from tests.facts.panel_fixtures import apply, edit, job, technology_facts, technology_workspace
from tests.support.rich import without_sources


def fixture():
    workspace = technology_workspace([{"kind": "technology", "display": name, "experience": str(index + 1)}
        for index, name in enumerate(["Python", "Docker", "SQL"])])
    facts, document = workspace.project.facts, workspace.project.document
    records = {record.display.raw_text: record for record in facts.records}
    content = []
    for name in ["Python", "Docker", "SQL"]:
        if content: content.append({"type": "text", "text": ", ", "styles": {}})
        span = field_block(records[name], "display")["content"][0]
        span["styles"] = {"italic": True, "textColor": "#123456"}
        content.append(span)
    group = TypeAdapter(RichBlock).validate_python({"id": "technology_group_test", "revision": 1, "type": "section",
        "props": {"recordId": None}, "content": [{"type": "text", "text": "TOOLS", "styles": {}}], "provenance": [],
        "children": [{"id": "tools", "revision": 1, "type": "paragraph", "props": {"alignment": "justify"},
            "content": content, "provenance": [], "children": []}]})
    document.regions[2].blocks = [group]
    return workspace, records


def tools(workspace):
    return next(block for block in workspace.project.document.blocks() if block.id == "tools")


@pytest.mark.parametrize("name,expected", [("Python", "Docker, SQL"), ("Docker", "Python, SQL"), ("SQL", "Python, Docker")])
def test_removing_first_middle_last_has_no_extra_commas_and_preserves_styles(name, expected):
    workspace, records = fixture()
    changed = apply(workspace, operation="remove", recordId=records[name].id)
    assert authored_text(tools(changed)) == expected
    assert all(span.styles.italic and span.styles.text_color == "#123456"
        for span in tools(changed).content if span.type == "fact_field")
    assert tools(changed).props == tools(workspace).props
    assert changed.project.sources == workspace.project.sources


def test_add_uses_existing_list_paragraph_styles_and_no_standalone_tail():
    workspace, _ = fixture()
    changed = apply(workspace, operation="add", recordKind="technology", values={"display": "Kubernetes"})
    assert authored_text(tools(changed)) == "Python, Docker, SQL, Kubernetes"
    assert tools(changed).content[-1].styles == tools(workspace).content[-1].styles
    assert tools(changed).props == tools(workspace).props
    assert [block.id for block in changed.project.document.blocks()] == [block.id for block in workspace.project.document.blocks()]
    assert presentation(changed.project.document, changed.project.facts).blocks["tools"].role == "body"


def test_move_changes_text_export_and_reload_and_undo_redo_keep_source_facts_exact():
    workspace, records = fixture()
    changed = apply(workspace, operation="move_technology", recordId=records["SQL"].id, beforeRecordId=records["Python"].id)
    assert authored_text(tools(changed)) == "SQL, Python, Docker"
    assert changed.project.facts == workspace.project.facts and changed.project.sources == workspace.project.sources
    transferred = WorkspaceV6.model_validate_json(changed.model_dump_json(by_alias=True))
    assert transferred.project.document == changed.project.document
    with ZipFile(BytesIO(render_rich_docx(changed.project.document, facts=changed.project.facts))) as archive:
        xml = etree.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraph = next(p for p in xml.xpath("//w:p", namespaces=ns) if "".join(p.xpath(".//w:t/text()", namespaces=ns)) == "SQL, Python, Docker")
    assert paragraph.xpath("./w:pPr/w:jc/@w:val", namespaces=ns) == ["both"]
    assert paragraph.xpath(".//w:i", namespaces=ns)
    undo = inverse_mutation(workspace, changed, mutation_id="undo-order", session_id="order")
    restored, _ = apply_rich_mutation(changed, undo)
    assert authored_text(tools(restored)) == "Python, Docker, SQL"
    redo = inverse_mutation(changed, restored, mutation_id="redo-order", session_id="order")
    redone, _ = apply_rich_mutation(restored, redo)
    assert authored_text(tools(redone)) == "SQL, Python, Docker"


def test_remove_all_hides_empty_heading_and_add_restores_a_styled_list():
    workspace, records = fixture()
    for record in records.values(): workspace = apply(workspace, operation="remove", recordId=record.id)
    assert not workspace.project.document.regions[2].blocks
    assert not workspace.project.document.regions[1].blocks
    changed = apply(workspace, operation="add", recordKind="technology", values={"display": "Python"})
    group = changed.project.document.regions[2].blocks[0]
    assert authored_text(group) == "НАВЫКИ" and authored_text(group.children[0]) == "Python"


def test_job_raw_stack_gets_exact_bindings_and_add_remove_order_stay_in_that_job():
    workspace = without_sources()
    facts, document = technology_facts([job("2021", "2022", "Python"), job("2023", "2024", "Python")])
    workspace.project.facts, workspace.project.document = facts, document
    workspace.project.evidence_records = []
    jobs = [record for record in facts.records if record.kind == "employment"]
    records = [record for record in facts.records if record.kind == "technology"]
    for index, owner in enumerate(jobs):
        document.regions[2].blocks.append(TypeAdapter(RichBlock).validate_python({"id": f"owner{index}", "revision": 1, "type": "section",
            "props": {"recordId": owner.id}, "content": [], "provenance": [], "children": [{"id": f"stack{index}", "revision": 1,
                "type": "paragraph", "props": {}, "content": [{"type": "text", "text": "Стек: Python", "styles": {"bold": True}}], "children": [], "provenance": []}]}))
    changed = apply(workspace, operation="add", recordKind="technology", jobId=jobs[0].id, values={"display": "Docker"})
    first = next(block for block in changed.project.document.blocks() if block.id == "stack0")
    assert authored_text(first) == "Стек: Python, Docker" and first.content[-1].styles.bold
    assert next(block for block in changed.project.document.blocks() if block.id == "stack1") == next(block for block in document.blocks() if block.id == "stack1")
    changed = apply(changed, operation="remove", recordId=records[0].id)
    assert authored_text(next(block for block in changed.project.document.blocks() if block.id == "stack0")) == "Стек: Docker"
    assert next(record for record in changed.project.facts.records if record.id == records[1].id) == records[1]


@pytest.mark.parametrize("before", ["missing", "candidate-1"])
def test_invalid_move_target_is_atomic(before):
    workspace, records = fixture()
    raw = workspace.model_dump_json()
    with pytest.raises(ValueError):
        panel_mutation(workspace, edit(workspace, operation="move_technology", recordId=records["SQL"].id, beforeRecordId=before))
    assert workspace.model_dump_json() == raw


def test_manual_focus_order_survives_year_edit_new_membership_export_and_reload():
    workspace, records = fixture()
    moved = apply(workspace, operation="move_focus", recordId=records["Python"].id, beforeRecordId=records["SQL"].id)
    section = moved.project.document.regions[1].blocks[0]
    assert section.props.manual_order
    expected = [authored_text(block) for block in section.children]
    assert expected == ["Python", "SQL", "Docker"]
    changed = apply(moved, recordId=records["Docker"].id, values={"experience": "99"})
    assert [entry.display for entry in presentation(changed.project.document, changed.project.facts).focus_entries] == expected
    reopened = WorkspaceV6.model_validate_json(changed.model_dump_json(by_alias=True))
    assert reopened.project.document.regions[1].blocks[0].props.manual_order
    with ZipFile(BytesIO(render_rich_docx(reopened.project.document, facts=reopened.project.facts))) as archive:
        xml = etree.fromstring(archive.read("word/document.xml"))
    text = xml.xpath("//w:t/text()", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"})
    assert text.index("Python") < text.index("SQL") < text.index("Docker")


def test_cross_group_move_keeps_destination_style_and_hides_empty_source_group():
    workspace, records = fixture()
    original = tools(workspace)
    third = original.content[-1]
    original.content = original.content[:-2]
    group = workspace.project.document.regions[2].blocks[0].model_copy(deep=True)
    group.id = "technology_group_second"
    group.children[0].id = "second-tools"
    group.children[0].content = [third]
    workspace.project.document.regions[2].blocks.append(group)
    moved = apply(workspace, operation="move_technology", recordId=records["SQL"].id, beforeRecordId=records["Python"].id)
    assert authored_text(tools(moved)) == "SQL, Python, Docker"
    assert not any(block.id == group.id for block in moved.project.document.blocks())
    assert moved.project.facts == workspace.project.facts


def test_split_styling_and_prose_punctuation_survive_removal():
    workspace, records = fixture()
    block = tools(workspace)
    python = block.content[0]
    fragment = python.model_copy(deep=True)
    python.text, python.binding_root_id = "Py", python.binding_id
    fragment.text, fragment.binding_root_id, fragment.binding_id = "thon", python.binding_id, "python-tail"
    fragment.styles.bold = True
    block.content.insert(1, fragment)
    changed = apply(workspace, operation="remove", recordId=records["Docker"].id)
    assert authored_text(tools(changed)) == "Python, SQL"
    assert tools(changed).content[1].styles.bold
    block.content.insert(0, TypeAdapter(RichBlock).validate_python({"id": "text-source", "revision": 1, "type": "paragraph", "props": {},
        "content": [{"type": "text", "text": "Built services using ", "styles": {}}], "provenance": [], "children": []}).content[0])
    changed = apply(workspace, operation="remove", recordId=records["Docker"].id)
    assert authored_text(tools(changed)) == "Built services using Python, SQL"


@pytest.mark.parametrize("prefix", ["", "Built services using ", "Stack: "])
def test_removing_unseparated_bindings_preserves_authored_text_and_styles(prefix):
    workspace, records = fixture()
    block = tools(workspace)
    block.content = [span for span in block.content if span.type == "fact_field"]
    if prefix:
        block.content.insert(0, StyledText(type="text", text=prefix, styles={"bold": True}))
    expected = [span for span in block.content if span.type != "fact_field" or span.record_id != records["Docker"].id]
    before = workspace.model_dump_json()
    changed = apply(workspace, operation="remove", recordId=records["Docker"].id)
    assert authored_text(tools(changed)) == prefix + "PythonSQL"
    assert tools(changed).content == expected
    assert workspace.model_dump_json() == before


def test_bulk_clear_of_a_raw_group_does_not_restore_removed_children():
    workspace, _ = fixture()
    value = tools(workspace).model_dump(by_alias=True)
    value["content"] = [{"type": "text", "text": "Python, Docker, SQL", "styles": {"italic": True}}]
    workspace.project.document.regions[2].blocks[0].children = [TypeAdapter(RichBlock).validate_python(value)]
    changed = apply(workspace, operation="clear_technologies", recordKind="technology", recordId=None)
    assert not changed.project.document.regions[2].blocks
    assert not any(record.kind == "technology" for record in changed.project.facts.records)


def test_job_stack_aliases_keep_visible_spelling_when_moved_or_only_years_change():
    workspace = without_sources()
    facts, document = technology_facts([job("2021", "2022", "postgres"), {"kind": "technology", "display": "PostgreSQL"}])
    workspace.project.facts, workspace.project.document = facts, document
    workspace.project.evidence_records = []
    owner = next(record for record in facts.records if record.kind == "employment")
    record = next(record for record in facts.records if record.kind == "technology" and record.job_id == owner.id)
    document.regions[2].blocks.append(TypeAdapter(RichBlock).validate_python({"id": "alias-owner", "revision": 1, "type": "section",
        "props": {"recordId": owner.id}, "content": [], "provenance": [], "children": [{"id": "alias-stack", "revision": 1,
            "type": "paragraph", "props": {}, "content": [{"type": "text", "text": "PostgreSQL", "styles": {"italic": True}}], "children": [], "provenance": []}]}))
    changed = apply(workspace, operation="add", recordKind="technology", jobId=owner.id, values={"display": "Docker"})
    added = changed.project.facts.records[-1]
    moved = apply(changed, operation="move_technology", recordId=added.id, beforeRecordId=record.id)
    edited = apply(moved, recordId=record.id, values={"experience": "7"})
    assert authored_text(next(block for block in edited.project.document.blocks() if block.id == "alias-stack")) == "Docker, PostgreSQL"
    assert next(value for value in edited.project.facts.records if value.id == record.id).display.raw_text == "postgres"


def test_global_group_can_include_a_job_only_tool_without_losing_list_editing():
    workspace, records = fixture()
    workspace = apply(workspace, operation="add", recordKind="employment", values={"employer": "Example"})
    owner = workspace.project.facts.records[-1]
    workspace = apply(workspace, operation="add", recordKind="technology", jobId=owner.id, values={"display": "Perl"})
    job_tool = workspace.project.facts.records[-1]
    value = tools(workspace).model_dump(by_alias=True)
    value["content"] += [{"type": "text", "text": ", ", "styles": {}}, field_block(job_tool, "display")["content"][0]]
    workspace.project.document.regions[2].blocks[0].children = [TypeAdapter(RichBlock).validate_python(value)]
    changed = apply(workspace, operation="add", recordKind="technology", values={"display": "Kubernetes"})
    assert authored_text(tools(changed)) == "Python, Docker, SQL, Perl, Kubernetes"
    moved = apply(changed, operation="move_technology", recordId=records["Docker"].id, beforeRecordId=records["Python"].id)
    assert authored_text(tools(moved)) == "Docker, Python, SQL, Perl, Kubernetes"
    assert next(record for record in moved.project.facts.records if record.id == job_tool.id) == job_tool


def test_removing_a_global_tool_preserves_a_misbound_job_stack_and_its_own_fact():
    workspace, records = fixture()
    workspace = apply(workspace, operation="add", recordKind="employment", values={"employer": "Example"})
    owner = workspace.project.facts.records[-1]
    workspace = apply(workspace, operation="add", recordKind="technology", jobId=owner.id, values={"display": "Python"})
    job_tool = workspace.project.facts.records[-1]
    section = next(block for block in workspace.project.document.blocks() if getattr(block.props, "record_id", None) == owner.id)
    stack = section.children[-1]
    value = stack.model_dump(by_alias=True)
    value["content"] = field_block(records["Python"], "display")["content"]
    section.children[-1] = TypeAdapter(RichBlock).validate_python(value)
    changed = apply(workspace, operation="remove", recordId=records["Python"].id)
    kept = next(block for block in changed.project.document.blocks() if block.id == stack.id)
    assert authored_text(kept) == "Python" and kept.content[0].record_id == job_tool.id
    assert next(record for record in changed.project.facts.records if record.id == job_tool.id) == job_tool
