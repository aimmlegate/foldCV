"""Advertised native read schemas stay within the isolated tool authority."""

import json

import httpx
from jsonschema import Draft202012Validator
import pytest

from packages.resume_core.agent_store import run_in
from packages.resume_core.models.rich_document import StyledText
from packages.resume_core.rich_mutations import apply_rich_mutation, inline_text
from tests.recovery.test_agent_tools import tools_setup


@pytest.mark.asyncio
async def test_read_tool_schemas_match_their_authority_and_load_known_blocks_without_search(tmp_path):
    session, _, workspace, _ = tools_setup(tmp_path)
    session.application = session.sdk.streamable_http_app()
    headers = {"Authorization": "Bearer " + session.token, "Accept": "application/json, text/event-stream"}
    before = workspace.model_dump_json()
    try:
        async with session.application.router.lifespan_context(session.application):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=session), base_url="http://" + session.host, headers=headers) as client:
                async def rpc(method, params):
                    response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                    assert response.status_code == 200
                    return response.json()["result"]
                tools = {tool["name"]: tool for tool in (await rpc("tools/list", {}))["tools"]}
                queries = {"get_resume_context": {"kind": "document", "ids": ["narrative"]},
                    "find_resume_content": {"kind": "find", "text": "Python"},
                    "get_working_facts": {"kind": "facts"}, "get_original_source": {"kind": "source"},
                    "get_conversation_context": {"kind": "history"}}
                for name, query in queries.items():
                    validator = Draft202012Validator(tools[name]["inputSchema"])
                    validator.validate({"query": query})
                    wrong = {**query, "kind": "facts" if query["kind"] != "facts" else "document"}
                    assert not validator.is_valid({"query": wrong})
                    denied = await rpc("tools/call", {"name": name, "arguments": {"query": wrong}})
                    assert denied["isError"] and json.loads(denied["content"][0]["text"])["error"]["code"] == "AGENT_TOOL_DENIED"
                    valid = await rpc("tools/call", {"name": name, "arguments": {"query": query}})
                    result = json.loads(valid["content"][0]["text"])
                    assert not valid.get("isError") and result["snapshot"]["id"]
                    if name == "get_resume_context":
                        assert json.loads(result["content"])["blocks"][0]["id"] == "narrative"
                        assert session.book.require(result["snapshot"]["id"]).complete
                search = Draft202012Validator(tools["find_resume_content"]["inputSchema"])
                for arguments in ({}, {"query": None}, {"query": {"kind": "find"}}, {"query": {"kind": "find", "text": ""}}):
                    assert not search.is_valid(arguments)
                    denied = await rpc("tools/call", {"name": "find_resume_content", "arguments": arguments})
                    assert denied["isError"]
                alias = await rpc("tools/call", {"name": "get_resume_context", "arguments": {"query": {"ids": ["narrative"]}}})
                assert json.loads(json.loads(alias["content"][0]["text"])["content"])["blocks"][0]["id"] == "narrative"
                assert workspace.model_dump_json() == before
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["Developed REST APIs in Python. ", "Вёл 😀 REST API. e\u0301 "],
    ids=["native-split-runs", "unicode"])
async def test_literal_search_ranges_compile_the_exact_substring_across_styled_runs(tmp_path, prefix):
    session, service, workspace, _ = tools_setup(tmp_path)
    block = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
    suffix = " unit tests with pytest."
    block.content = [StyledText(type="text", text=prefix, styles={"bold": True}),
        StyledText(type="text", text="Wro", styles={"italic": True}),
        StyledText(type="text", text="te", styles={"italic": True}),
        StyledText(type="text", text=suffix, styles={"underline": True})]
    before = workspace.model_dump_json()
    session.application = session.sdk.streamable_http_app()
    headers = {"Authorization": "Bearer " + session.token, "Accept": "application/json, text/event-stream"}
    try:
        async with session.application.router.lifespan_context(session.application):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=session), base_url="http://" + session.host, headers=headers) as client:
                async def call(name, arguments):
                    response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1,
                        "method": "tools/call", "params": {"name": name, "arguments": arguments}})
                    assert response.status_code == 200
                    result = response.json()["result"]
                    assert not result.get("isError")
                    return json.loads(result["content"][0]["text"])
                search = await call("find_resume_content", {"query": {"kind": "find", "text": "Wrote"}})
                match, = [item for item in json.loads(search["content"])["matches"] if item["blockId"] == "narrative"]
                start = len(prefix.encode("utf-16-le")) // 2
                assert (match["start"], match["end"], match["text"], match["fullTarget"]) == (start, start + 5, "Wrote", False)
                full = await call("get_resume_context", {"query": {"kind": "document", "ids": [match["blockId"]]}})
                prepared = await call("prepare_edit_batch", {"request": {"key": "exact-search-range",
                    "snapshotIds": [full["snapshot"]["id"]], "operations": [{"kind": "replace_text",
                        "target": {"snapshotId": full["snapshot"]["id"], "blockId": match["blockId"],
                            "cellId": match["cellId"], "field": match["field"], "start": match["start"], "end": match["end"]},
                        "content": [{"text": "Added"}]}]}})
                assert prepared["disposition"] == "prepared"
                _, _, journal = run_in(service.store.load(workspace.project_id), session.run.id)
                batch, = [item.batch for item in journal.batches if item.batch.id == prepared["batchId"]]
                changed, replay = apply_rich_mutation(workspace, batch.mutation)
                result = next(block for block in changed.project.document.blocks() if block.id == "narrative")
                assert not replay and "".join(inline_text(span) for span in result.content) == prefix + "Added" + suffix
                assert result.content[0].styles.bold and result.content[-1].styles.underline
                assert next(span for span in result.content if span.text == "Added").styles.italic
                assert changed.project.facts == workspace.project.facts
                assert workspace.model_dump_json() == before
    finally:
        await session.close()
