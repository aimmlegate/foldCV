"""publish_findings stores remarks that cite only pages fetched in this run and never changes the resume."""

import json

import pytest

from packages.resume_core.models.assistant import PublishFindingsV1
from tests.support.assistant_tools import Fetcher, tool_session


def request(block, sources):
    return PublishFindingsV1.model_validate({"findings": [{"severity": "warning", "message": "Evidence is missing.",
        "targets": [{"blockId": block, "start": 0, "end": 3}], "sourceIds": sources}]})


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
