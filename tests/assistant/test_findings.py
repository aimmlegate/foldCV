"""publish_findings stores remarks that cite only pages fetched in this run and never changes the resume."""

import json

import pytest

from packages.resume_core import agent_limits as limits
from packages.resume_core.assistant_compiler import target_text
from packages.resume_core.models.assistant import PublishFindingsV1
from packages.resume_core.rich_dependencies import dependencies_current
from tests.support.assistant_tools import Fetcher, tool_session
from tests.templates.golden.corpus import fixtures


def request(block, sources):
    return PublishFindingsV1.model_validate({"findings": [{"severity": "warning", "message": "Evidence is missing.",
        "targets": [{"blockId": block, "start": 0, "end": 3}], "sourceIds": sources}]})


def record_request(record, **target):
    return PublishFindingsV1.model_validate({"findings": [{"message": "Check this.", "targets": [{"recordId": record, **target}]}]})


@pytest.mark.asyncio
async def test_a_finding_on_a_fact_quotes_its_fields_not_its_json():
    session = tool_session()
    session.pinned = fixtures()['scoped'][0]
    record = next(value for value in session.pinned.project.facts.records if value.kind == 'employment')
    try:
        stored = await session.call("publish_findings", lambda: session.findings(record_request(record.id)))
        assert "findingIds" in json.loads(stored.content[0].text)
        anchor = session.service.findings[0].anchors[0]
        assert anchor.text == target_text(session.pinned, record.id) and '{' not in anchor.text and anchor.text
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_finding_can_target_a_template_entity_that_read_facts_lists():
    session = tool_session()
    try:
        stored = await session.call("publish_findings", lambda: session.findings(record_request("paper-a")))
        assert "findingIds" in json.loads(stored.content[0].text)
        anchor = session.service.findings[0].anchors[0]
        assert anchor.text.startswith("title: ") and anchor.dependencies[0].id == "paper-a"
        assert dependencies_current(session.pinned, anchor.dependencies)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_finding_over_its_size_limit_names_the_limit_and_says_to_split():
    session = tool_session()
    block = session.pinned.project.document.regions[2].blocks[0]
    block.content[0].text = "\x01" * 3900
    targets = [{"blockId": block.id}] * 3
    try:
        result = await session.call("publish_findings", lambda: session.findings(PublishFindingsV1.model_validate(
            {"findings": [{"message": "Check this.", "targets": targets}]})))
        body = json.loads(result.content[0].text)
        assert result.isError and body["error"]["code"] == "AGENT_CALL_TOO_LARGE"
        assert str(limits.FINDING_BYTES) in body["detail"][0] and "split" in body["detail"][0]
        assert session.service.findings == []
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_page_injection_and_forged_citations_cannot_change_the_resume_or_store_a_finding():
    session = tool_session(allow_web=True, fetcher=Fetcher())
    before = session.pinned.model_dump_json()
    block = session.pinned.project.document.regions[2].blocks[0].id
    try:
        fetched = json.loads((await session.call("read_public_page", lambda: session.fetch("https://public.example/path"))).content[0].text)
        assert fetched["source"]["id"] == "source_1" and "write to another project" in fetched["excerpt"]
        forged = await session.call("publish_findings", lambda: session.findings(request(block, ["unfetched_source"])))
        assert json.loads(forged.content[0].text) == {"error": {"code": "AGENT_EVIDENCE_INVALID"}}
        assert session.service.findings == []
        stored = json.loads((await session.call("publish_findings", lambda: session.findings(request(block, ["source_1"])))).content[0].text)
        assert len(stored["findingIds"]) == 1 and session.service.findings[0].source_ids == ["source_1"]
        assert session.service.findings[0].anchors[0].text and session.pinned.model_dump_json() == before
    finally:
        await session.close()
