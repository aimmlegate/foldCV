"""Actual rich HTTP entries preserve interleaved canonical work through shared writers."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import threading

import httpx
import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.extraction.parser import extract
from packages.resume_core.gui_projects import GuiRenameProjectRequest
from packages.resume_core.models.rich_workspace import RichWarning
from packages.resume_core.rich_api import ImageSessionRequest
from packages.resume_core.rich_archive import export_rich_archive
from packages.resume_core.rich_dependencies import placements
from packages.resume_core.rich_sync import RichRewriteRequest
from packages.resume_core.rich_timeline import CascadeRequest, cascade_proposal
from tests.recovery.test_agent_lifecycle import MetadataAdapter, Tools
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.test_background_exports import HeldRenderer
from tests.recovery.test_background_inverse import block, mutation, put
from tests.recovery.test_rich_images_service import png
from tests.recovery.test_rich_synchronization import capture, selection
from tests.recovery.test_rich_timeline import timeline
from tests.support.background_publication import PublicationFixture


class HeldProvider(CreationProvider):
    def __init__(self):
        super().__init__()
        self.entered, self.release = threading.Event(), threading.Event()

    def generate(self, *args):
        self.entered.set()
        assert self.release.wait(10)
        return super().generate(*args)


def independent(fixture, text="Interleaved canonical input"):
    before = fixture.current()
    parent, previous, _owner = placements(before.project.document)["quote"]
    return fixture.coordinator.manual(fixture.project, mutation(before,
        [put(before, "quote", parent=parent, after=previous, text=text)], "external_" + str(before.project_revision)),
        originals=fixture.originals, artifacts=fixture.artifact_bytes, images=fixture.images)[0]


@asynccontextmanager
async def boundary(fixture, tmp_path, provider=None):
    from resume_api.agent.runtime import ScriptedAgentRuntime
    from resume_api.app import create_app
    dist = tmp_path / "dist"; dist.mkdir()
    (dist / "index.html").write_text("Synthetic rich route boundary")
    origin, secret = "http://127.0.0.1:39277", "synthetic-background-writers-0123456789"
    wrapped = create_app(origin=origin, secret=secret, temp_root=tmp_path / "operations", dist=dist,
        data_root=fixture.root, connection_adapter=MetadataAdapter(), agent_runtime=ScriptedAgentRuntime(None),
        agent_tools=Tools(), gui_provider=provider or CreationProvider(), background_enabled=True)
    app, service, jobs = wrapped.app, wrapped.app.state.rich_projects, wrapped.app.state.jobs
    service.renderer = HeldRenderer(); service.renderer.release.set()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin,
                headers={"Origin": origin}) as client:
            assert (await client.post("/v1/session/exchange", json={"secret": secret})).status_code == 200
            service.read(fixture.project)
            yield client, service, jobs
    assert not service.files and all(task.done() for task in service.tasks.values()) and not jobs.supervisor.controls


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [f"NB-P08:v{index:02d}" for index in (1, 2, 3, 7, 8)])
async def test_source_import_and_fixed_generation_routes_keep_independent_publication(tmp_path, monkeypatch, variant):
    from resume_api import rich_projects
    fixture = PublicationFixture(tmp_path / "store")
    provider = HeldProvider()
    parsed, release_parse = asyncio.Event(), asyncio.Event()
    async def scripted_extract(data, name, pasted, _files):
        parsed.set()
        if variant == "NB-P08:v02":
            await release_parse.wait()
        return extract(data, name, pasted)
    monkeypatch.setattr(rich_projects, "run_extract", scripted_extract)
    async with boundary(fixture, tmp_path, provider) as (client, service, jobs):
        prefix = "/v1/rich/projects"
        data = Path("tests/fixtures/recovery/E1.txt").read_bytes()
        if variant == "NB-P08:v03":
            archive = export_rich_archive(fixture.current(), {}, {}, {})
            original = rich_projects.open_rich_archive
            def parse_then_interleave(*args):
                result = original(*args)
                independent(fixture)
                return result
            monkeypatch.setattr(rich_projects, "open_rich_archive", parse_then_interleave)
            response = await client.post(prefix + "/archive", files={"file": ("synthetic.foldcv", archive, "application/zip")})
            assert response.status_code == 201, response.text
            identifier = response.json()["workspace"]["projectId"]
            assert identifier != fixture.project and service.read(identifier).project.document == fixture.initial.project.document
            assert block(fixture.current(), "quote").content[0].text == "Interleaved canonical input"
            assert not jobs.store.open(identifier).jobs
            return
        if variant == "NB-P08:v01":
            response = await client.post(prefix, json={"text": data.decode()})
            assert response.status_code == 202, response.text
            identifier = response.json()["workspace"]["projectId"]
        elif variant == "NB-P08:v02":
            task = asyncio.create_task(client.post(prefix + "/input", files={"file": ("pasted.txt", data, "text/plain")}))
            await asyncio.wait_for(parsed.wait(), 10)
            identifier = next(key for key in service.workspaces if key != fixture.project)
        else:
            selected = await service.select(data, "pasted.txt", True)
            identifier = selected.project_id
            response = await client.post(prefix + f"/{identifier}/generation", json={})
            assert response.status_code == 202, response.text
        if variant != "NB-P08:v02":
            assert await asyncio.to_thread(provider.entered.wait, 10)
        before, checksum = service.storage.read_committed(identifier)
        changed = before.model_copy(deep=True)
        changed.title, changed.title_manually_set = "Keep the interleaved title", True
        changed.project_revision += 1
        fixture.coordinator.snapshot(identifier, checksum, changed, "external-title", originals=service.originals,
            artifacts=service.artifacts, images=service.images)
        if variant == "NB-P08:v02":
            release_parse.set()
            response = await task
            assert response.status_code == 201, response.text
            assert service.read(identifier).pre_draft.sources[0].parser != "pending"
            assert not provider.calls
        else:
            if variant == "NB-P08:v08":
                cancel_task = asyncio.create_task(client.post(prefix + f"/{identifier}/cancel", json={}))
                key = next(key for key in service.cancels if key[0] == identifier)
                assert await asyncio.to_thread(service.cancels[key].wait, 10)
            provider.release.set()
            generation_id = service.generations[identifier].id
            await asyncio.wait_for(service.tasks[(identifier, generation_id)], 10)
            if variant == "NB-P08:v08":
                assert (await cancel_task).status_code == 200
                assert service.generations[identifier].status == "cancelled" and len(provider.calls) == 1
            else:
                assert service.generations[identifier].status == "completed", service.generations[identifier]
                assert len(provider.calls) == 2 and service.read(identifier).project
        current, checksum = service.storage.read_committed(identifier)
        assert current.title == "Keep the interleaved title" and current.title_manually_set
        assert jobs.store.load(identifier).history.workspace_sha256 == checksum == digest_bytes(current)
        assert service.read(identifier) == current


CANONICAL = (4, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [f"NB-P08:v{index:02d}" for index in CANONICAL])
async def test_each_existing_canonical_http_entry_preserves_an_interleaved_change(tmp_path, variant):
    fixture = PublicationFixture(tmp_path / "store")
    if variant in {"NB-P08:v14", "NB-P08:v15"}:
        value = timeline([("A", "a", "2020-01", "2020-04"), ("B", "b", "2020-04", "2020-06")])
        def seed(workspace):
            workspace.project = value.project.model_copy(deep=True)
            workspace.formatting_as_of = value.formatting_as_of
        fixture.snapshot(seed, "timeline-seed")
    provider = HeldProvider() if variant == "NB-P08:v20" else CreationProvider()
    async with boundary(fixture, tmp_path, provider) as (client, service, jobs):
        prefix = "/v1/rich/projects/" + fixture.project
        before = service.read(fixture.project)
        selected = selection(before) if variant not in {"NB-P08:v14", "NB-P08:v15"} else None
        record = None
        if variant in {"NB-P08:v17", "NB-P08:v18", "NB-P08:v19"}:
            await service.rewrite_rich(fixture.project, RichRewriteRequest(selection=selected, instruction="Clarify"))
            record = service.read(fixture.project).sync_records[-1]
        if variant == "NB-P08:v06":
            service.workspaces[fixture.project].warnings.append(RichWarning(id="async-warning", code="SOURCE_NOTE",
                blockIds=[], recordIds=[], evidence=[]))
        if variant in {"NB-P08:v14", "NB-P08:v15"}:
            fixture.snapshot(lambda value: setattr(value, "title", "Independent timeline title"), "timeline-title")
        else:
            independent(fixture)
        committed = fixture.current()
        raw = (jobs.store.projects / fixture.project / "state.json").read_bytes()
        model_calls = len(provider.calls)
        request = mutation(before, [put(before, "narrative", text="Explicit route edit")], "route-edit") if selected else None
        path, payload, method, files, headers = None, {}, "POST", None, None
        if variant == "NB-P08:v04":
            path, method = "/title", "PUT"
            payload = GuiRenameProjectRequest(title="Explicit title", baseRevision=committed.project_revision).model_dump(by_alias=True)
        elif variant == "NB-P08:v05":
            path, payload = "/delete", {"confirmed": True}
        elif variant == "NB-P08:v06":
            path = "/save"
        elif variant in {"NB-P08:v09", "NB-P08:v10"}:
            path, payload = "/mutations" if variant == "NB-P08:v09" else "/preview", request.model_dump(mode="json", by_alias=True)
        elif variant == "NB-P08:v11":
            path = "/completion"
            payload = {"capture": capture(), "blockIds": ["title"], "movedIds": [], "removedFields": [], "interpret": False}
        elif variant == "NB-P08:v12":
            path = "/panel/preview"
            payload = {"operation": "edit", "recordId": "language-1", "recordKind": "language", "values": {"level": "C2"},
                "factsRevision": committed.project.facts.revision, "documentRevision": committed.document_revision, "capture": capture()}
        elif variant == "NB-P08:v13":
            path, payload = "/panel/sync", {"capture": capture(), "recordIds": ["job-1"]}
        elif variant in {"NB-P08:v14", "NB-P08:v15"}:
            captured = CascadeRequest(anchorJobId="A", anchorPeriodId="a", capture=capture())
            if variant == "NB-P08:v14":
                path, payload = "/cascade", captured.model_dump(by_alias=True)
            else:
                cascade = cascade_proposal(committed, captured)
                assert cascade.status == "available"
                path, payload = "/cascade/preview", {"proposal": cascade.model_dump(mode="json", by_alias=True), "capture": capture()}
        elif variant in {"NB-P08:v16", "NB-P08:v20"}:
            path, payload = "/rewrite", RichRewriteRequest(selection=selected, instruction="Clarify").model_dump(mode="json", by_alias=True)
        elif variant in {"NB-P08:v17", "NB-P08:v18", "NB-P08:v19"}:
            suffix = "" if variant == "NB-P08:v17" else "/resolve" if variant == "NB-P08:v18" else "/retry"
            path, payload = "/sync/" + record.id + suffix, {"status": "stale"} if not suffix else capture("fresh-action")
        elif variant == "NB-P08:v21":
            path = "/images/session"
            payload = ImageSessionRequest(sessionId="images", revision=1, live=[], history=[], closed=False).model_dump(by_alias=True)
        elif variant == "NB-P08:v22":
            service.update_image_session(fixture.project, ImageSessionRequest(sessionId="images", revision=1, live=[], history=[], closed=False))
            path, files = "/images/upload", {"file": ("synthetic.png", png(), "image/png")}
            headers = {"X-FoldCV-Session": "images", "X-FoldCV-Revision": "1", "X-FoldCV-Action": "upload", "X-FoldCV-Reservation": "upload"}
        elif variant == "NB-P08:v23":
            path = "/export"
        else:
            path, payload = "/archive", {"projectRevision": committed.project_revision, "documentRevision": committed.document_revision}
        if variant == "NB-P08:v20":
            task = asyncio.create_task(client.post(prefix + path, json=payload))
            assert await asyncio.to_thread(provider.entered.wait, 10)
            cancelled = asyncio.create_task(client.post(prefix + "/cancel-action", json=capture()))
            key = next(key for key in service.cancels if key[0] == fixture.project)
            assert await asyncio.to_thread(service.cancels[key].wait, 10)
            provider.release.set()
            response = await task
            assert (await cancelled).status_code == 200
        elif files:
            response = await client.request(method, prefix + path, files=files, headers=headers)
        else:
            response = await client.request(method, prefix + path, json=payload)
        assert response.status_code in {200, 201}, (variant, response.status_code, response.text)
        if variant == "NB-P08:v05":
            assert response.json()["status"] == "deleted" and not (service.storage.projects / fixture.project).exists()
            return
        after = fixture.current()
        if selected:
            assert block(after, "quote").content == block(committed, "quote").content
        else:
            assert after.title == committed.title
        if variant in {"NB-P08:v10", "NB-P08:v12", "NB-P08:v14", "NB-P08:v15"}:
            assert after == committed and (jobs.store.projects / fixture.project / "state.json").read_bytes() == raw
        else:
            assert jobs.store.load(fixture.project).history.workspace_sha256 == digest_bytes(after)
        if variant == "NB-P08:v06":
            assert any(warning.id == "async-warning" for warning in after.warnings)
        if variant in {"NB-P08:v18", "NB-P08:v19"}:
            old = next(item for item in after.sync_records if item.id == record.id)
            assert old.status == "stale" and not old.ready and not old.proposed_steps
        if variant not in {"NB-P08:v13", "NB-P08:v16", "NB-P08:v19", "NB-P08:v20"}:
            assert len(provider.calls) == model_calls
