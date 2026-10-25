"""Current authored Cyrillic content with rich metadata and an extraction gap."""

import hashlib
import time

from packages.resume_core.models.contracts import Source, SourceUnit
from packages.resume_core.models.rich_document import Hyperlink, StyledText
from tests.recovery.test_agent_lifecycle import setup
from tests.recovery.test_agent_tools import Fetcher
from tests.recovery.test_rich_persistence import image_asset
from resume_api.agent.service import RunControl
from resume_api.agent.tools import ToolSession


def environment(root, *, task_message="Перепиши текущее резюме, сохрани факты и оформление.", large=False, supported_source=False):
    service, runtime, projects, initial, _, request, _ = setup(root, None)
    service.assistant_protocol_enabled = True
    workspace = projects.workspaces[initial.project_id]
    narrative = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
    narrative.content = [StyledText(type="text", text="Разрабатывал API 😀. ", styles={"bold": True}),
        Hyperlink(type="link", href="mailto:hello@example.invalid", content=[StyledText(type="text",
            text="hello@example.invalid", styles={"underline": True})]),
        StyledText(type="text", text=" Работал в команде с 2024 года.", styles={"italic": True})]
    if large:
        narrative.content[0].text = "А" * 100000
    table = next(block for block in workspace.project.document.blocks() if block.type == "table")
    table.content.rows[1].cells[0].content = [StyledText(type="text", text="Создавал сервисы 😀", styles={"italic": True})]
    table.content.rows[1].cells[1].content = [Hyperlink(type="link", href="https://example.invalid/portfolio",
        content=[StyledText(type="text", text="Портфолио", styles={"underline": True})])]
    asset, blob = image_asset(workspace)
    projects.images[(workspace.project_id, asset.id)] = blob
    image = next(block for block in workspace.project.document.blocks() if block.id == "test-image")
    image.props.alt = "Синтетическая схема"
    image.props.caption = [StyledText(type="text", text="Схема проекта 😀", styles={"italic": True})]
    workspace.project.facts.records[0].user_corrected = True
    hidden = ("Роль: Architect. Это синтетический исходник." if supported_source else
        "Скрытая строка старого исходника: не восстанавливать при переписывании.").encode()
    units = [SourceUnit(id="cap-u1", revision=1, order=0, text=hidden.decode(),
        location={"kind": "pasted", "index": 0, "row": None, "column": None}, disposition="shown", representedFactIds=[])] if supported_source else []
    source = Source(id="cap-original", revision=1, originalName="synthetic-original.txt", mimeType="text/plain",
        byteSha256=hashlib.sha256(hidden).hexdigest(), byteRef="sources/cap-original/original", parser="text",
        parserVersion="fixture-v1", units=units, overlays=[], warnings=[] if supported_source else ["SOURCE_EXTRACTION_INCOMPLETE"])
    workspace.project.sources = [source]
    projects.originals[(workspace.project_id, source.id)] = hidden
    assert projects.persist(workspace.project_id) == "durable"
    run, _ = service.submit(workspace.project_id, request.model_copy(update={"allow_edits": False, "message": task_message}))
    control = RunControl(workspace.project_id, run.id, run.owner_epoch, run.connection_epoch, time.monotonic())
    return service, runtime, projects, workspace, ToolSession(service, control, run, Fetcher())
