"""Local rewrite diagnostics stay scoped and cannot affect durable text edits."""

import asyncio
import json

import pytest

from resume_api.rewrite_timing import add_phase, rewrite_timing
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.test_rich_images_service import service
from tests.recovery.test_rich_synchronization import selection
from packages.resume_core.rich_sync import RichRewriteRequest


@pytest.mark.asyncio
async def test_threaded_rewrite_timing_keeps_no_content_and_publishes_operation_with_proposal(tmp_path):
    instance, identifier = service(tmp_path)
    class TimedProvider(CreationProvider):
        def generate(self, *args):
            add_phase("model_turn", .025)
            add_phase("private instruction", 100)
            return super().generate(*args)
    instance.provider_factory = lambda: (TimedProvider(), "fixture")
    request = RichRewriteRequest(selection=selection(instance.read(identifier)), instruction="Private rewrite instruction")
    with rewrite_timing(instance.rules.root, 1) as timing:
        result = await instance.rewrite_rich(identifier, request)
        timing.outcome = result.workspace.sync_records[-1].status
    committed, _ = instance.storage.read_committed(identifier)
    assert committed.project.operations[-1].status == "completed"
    assert committed.sync_records[-1].ready and committed.sync_records[-1].proposed_steps
    raw = (instance.rules.root / "diagnostics/rewrite-timings.json").read_text()
    row, = json.loads(raw)
    assert set(row) == {"at", "blocks", "outcome", "milliseconds"}
    assert row["outcome"] == "pending" and row["milliseconds"]["model_turn"] == 25
    assert {"prepare", "content", "proposal", "publish", "response", "total"} <= row["milliseconds"].keys()
    assert "Private rewrite instruction" not in raw and "private instruction" not in raw
    assert "Clearer" not in raw and "sessionId" not in raw


@pytest.mark.asyncio
async def test_concurrent_timing_contexts_and_thread_handoffs_stay_separate(tmp_path):
    async def run(name, seconds):
        root = tmp_path / name
        with rewrite_timing(root, 1):
            await asyncio.sleep(0)
            await asyncio.to_thread(add_phase, "model_turn", seconds)
        return json.loads((root / "diagnostics/rewrite-timings.json").read_text())[0]
    first, second = await asyncio.gather(run("first", .01), run("second", .03))
    assert first["milliseconds"]["model_turn"] == 10
    assert second["milliseconds"]["model_turn"] == 30


def test_timing_retention_is_bounded_and_unwritable_diagnostics_do_not_fail_edits(tmp_path, monkeypatch):
    for index in range(53):
        with rewrite_timing(tmp_path, index):
            pass
    rows = json.loads((tmp_path / "diagnostics/rewrite-timings.json").read_text())
    assert len(rows) == 50 and rows[0]["blocks"] == 3 and rows[-1]["blocks"] == 52
    def failed(*_args):
        raise PermissionError("Unavailable diagnostics")
    monkeypatch.setattr("resume_api.rewrite_timing.atomic_write", failed)
    with rewrite_timing(tmp_path, 1):
        pass


@pytest.mark.asyncio
async def test_authenticated_rewrite_route_keeps_the_proposal_and_local_timing(tmp_path):
    import httpx
    from resume_api.app import create_app
    from tests.recovery.test_rich_persistence import without_sources
    origin, secret = "http://127.0.0.1:39329", "synthetic-timing-session-0123456789"
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("fixture")
    app = create_app(origin=origin, secret=secret, temp_root=tmp_path / "operations", dist=dist, data_root=tmp_path / "store")
    instance = app.app.state.rich_projects
    instance.provider_factory = lambda: (CreationProvider(), "fixture")
    workspace = without_sources()
    instance.loaded = True
    instance.workspaces[workspace.project_id] = workspace
    instance.persist(workspace.project_id)
    request = RichRewriteRequest(selection=selection(workspace), instruction="Clarify")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin) as client:
        await client.post("/v1/session/exchange", headers={"Origin": origin}, json={"secret": secret})
        response = await client.post(f"/v1/rich/projects/{workspace.project_id}/rewrite", headers={"Origin": origin},
            json=request.model_dump(mode="json", by_alias=True))
    assert response.status_code == 200
    assert response.json()["workspace"]["syncRecords"][-1]["ready"]
    row, = json.loads((instance.rules.root / "diagnostics/rewrite-timings.json").read_text())
    assert row["outcome"] == "pending" and row["blocks"] == 1
