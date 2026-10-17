"""Drive real HTTP/compiler/store boundaries over an owned offline test pipe."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import threading

import httpx

from packages.resume_core.background_clock import ControlledDeadlines
from packages.resume_core.background_supervisor import ExecutionOutcome
from packages.resume_core.models.agent import AgentApplyRequest, AgentQuery, AgentReadSnapshot, AgentSettingsRequest
from spikes.background.fixtures import TIME
from tests.recovery.test_agent_edits import command, replace
from tests.recovery.test_agent_lifecycle import MetadataAdapter, Tools
from tests.support.agent import isolated_project
from tests.support.background import PipeExecutions


class Bridge:
    def __init__(self, root, *, dist=None, origin=None, background_enabled=True, parallel=False):
        self.root, self.loop = root, asyncio.get_running_loop()
        self.dist, self.origin = dist, origin
        self.background_enabled = background_enabled
        self.parallel = parallel
        self.clock = ControlledDeadlines()
        self.factory = PipeExecutions(root / "pipes", self.clock)
        self.holds, self.lock = {}, threading.Lock()
        self.tasks, self.results = set(), {}
        self.closed, self.wall_offset = False, 0

    @staticmethod
    def send(value):
        sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    def observe(self, name, project):
        with self.lock:
            held = [(token, row) for token, row in self.holds.items() if row["name"] == name and row["family"] == "writer"]
        for token, row in held:
            if row.get("jobOnly"):
                # Commit observers may already own the non-reentrant lifecycle flock.
                state = self.service.store._read(project, self.service.store.projects / project)
                if not any(intent.phase not in {"receipt_stored", "reconciled"} for intent in state.intents):
                    continue
            self.loop.call_soon_threadsafe(self.send, {"event": "hook", "token": token, "name": name, "project": project})
            if not row["thread"].wait(30):
                raise TimeoutError("Writer bridge watchdog: " + name)

    async def observe_job(self, name, job):
        await self.observe_async(name, "job", job=job)

    async def observe_async(self, name, family, **identity):
        with self.lock:
            held = [(token, row) for token, row in self.holds.items() if row["name"] == name and row["family"] == family
                and (row.get("job") is None or row["job"] == identity.get("job"))]
        for token, row in held:
            self.send({"event": "hook", "token": token, "name": name, **identity})
            await row["async"].wait()

    async def start(self):
        from resume_api.app import create_app
        from resume_api.agent.runtime import ScriptedAgentRuntime
        identity_path = self.root / "identities.json"
        if identity_path.exists():
            from types import SimpleNamespace
            from packages.resume_core.agent_store import AgentStore
            from packages.resume_core.rich_project_store import RichProjectStore
            identity = json.loads(identity_path.read_text())
            self.journal, canonical = AgentStore(self.root / "FoldCV"), RichProjectStore(self.root / "FoldCV")
            workspace = canonical.read_committed(identity["project"])[0]
            self.conversation = SimpleNamespace(id=identity["conversation"])
        else:
            self.journal, canonical, workspace, self.conversation = isolated_project(self.root / "FoldCV")
            identity_path.write_text(json.dumps({"project": workspace.project_id, "conversation": self.conversation.id}))
        dist = self.dist or self.root / "dist"
        if self.dist is None:
            dist.mkdir(exist_ok=True); (dist / "index.html").write_text("Synthetic offline bridge")
        self.origin, secret = self.origin or "http://127.0.0.1:39288", "synthetic_background_bridge_secret_0123456789"
        self.adapter = MetadataAdapter()
        self.application = create_app(origin=self.origin, secret=secret, temp_root=self.root / "operations", dist=dist,
            data_root=canonical.root, connection_adapter=self.adapter, agent_runtime=ScriptedAgentRuntime(None),
            agent_tools=Tools(), background_enabled=self.background_enabled, background_factory=self.factory,
            background_parallel=self.parallel)
        self.service = self.application.app.state.jobs
        self.service.supervisor.clock = self.clock
        self.service.publisher.authority.clock = self.clock
        self.service.writers.clock = self.clock
        base = datetime.fromisoformat(TIME.replace("Z", "+00:00"))
        self.service.store.clock = self.service.artifacts.clock = lambda: (base + timedelta(seconds=self.clock.now() + self.wall_offset)).isoformat()
        self.service.publisher.observer = self.service.writers.observer = self.observe
        self.service.supervisor.observer = self.observe_job
        self.lifespan = self.application.app.router.lifespan_context(self.application.app)
        await self.lifespan.__aenter__()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.application), base_url=self.origin,
            headers={"Origin": self.origin})
        exchanged = await self.client.post("/v1/session/exchange", json={"secret": secret})
        assert exchanged.status_code == 200, exchanged.text
        status = await self.client.post("/v1/host/status", json={})
        assert status.status_code == 200, status.text
        if self.service.settings.load().revision == 1:
            self.service.settings.save(AgentSettingsRequest(expectedRevision=1, enabled=True,
                selectedAgentModel="assistant-model"), ("assistant-model", "processing-model"))
        self.project = workspace.project_id
        self.send({"event": "ready", "project": self.project, "conversation": self.conversation.id,
            "root": str(self.root), "synthetic": True, "capacity": 3 if self.parallel else 1})

    def script(self, request_id, text):
        async def execute(control, _actor):
            session = self.service.tools.session(control)
            try:
                await self.observe_job("scripted_model_ready", control.job.id)
                read = await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"]))
                if control.job.submission.allow_edits:
                    prepared = await session.call("prepare_edit_batch", command(replace(
                        AgentReadSnapshot.model_validate(read["snapshot"]), "narrative", 0, 6, text)))
                    assert prepared["disposition"] == "prepared", prepared
                    await self.observe_job("scripted_proposal_prepared", control.job.id)
                    self.results[request_id] = await session.call("apply_edit_batch", AgentApplyRequest(batchId=prepared["batchId"]))
                    await self.observe_job("scripted_after_apply", control.job.id)
                return ExecutionOutcome(finished_at=self.clock.now())
            finally:
                await session.close()
        self.factory.callbacks[request_id] = execute

    async def handle(self, frame):
        kind = frame["kind"]
        if kind == "http":
            path = frame["path"]
            body = frame.get("body")
            if path.endswith("/jobs/agent") and isinstance(body, dict):
                request = body.get("request", {})
                self.script(request["clientRequestId"], frame.get("text", "Scripted bridge change"))
            response = await self.client.request(frame.get("method", "POST"), path,
                **({"json": body} if body is not None else {}))
            await self.observe_async(path.rsplit("/", 1)[-1] + "_response", "http", path=path, status=response.status_code)
            return {"status": response.status_code, "value": response.json()}
        if kind == "hold":
            with self.lock:
                assert frame["token"] not in self.holds
                self.holds[frame["token"]] = {"name": frame["name"], "family": frame.get("family", "writer"),
                    "thread": threading.Event(), "async": asyncio.Event(), "jobOnly": frame.get("jobOnly", False),
                    "job": frame.get("job")}
            return {"held": frame["token"]}
        if kind == "release":
            with self.lock:
                row = self.holds.pop(frame["token"])
            row["thread"].set(); row["async"].set()
            return {"released": frame["token"]}
        if kind == "advance":
            self.clock.advance(frame["seconds"])
            self.wall_offset += frame.get("wallOffset", 0)
            return {"elapsed": self.clock.now()}
        if kind == "wait_job":
            project = frame.get("project", self.project)
            job = self.service.store.read(project, frame["job"])
            await self.factory.actor(job)
            await asyncio.wait_for(asyncio.shield(self.service.supervisor.controls[job.id].task), 20)
            return {"job": self.service.store.read(project, job.id).model_dump(mode="json", by_alias=True),
                "apply": self.results.get(job.submission.identity.request_id)}
        if kind == "fixed_fixture":
            from spikes.background.fixed_fixtures import prepare_fixed
            return await asyncio.to_thread(prepare_fixed, self, frame.get("project", self.project))
        if kind == "prune_events":
            project = frame.get("project", self.project)
            job = self.service.store.read(project, frame["job"])
            with self.service.store.guard(project) as directory:
                (directory / "events" / (job.id + ".json")).unlink(missing_ok=True)
            return {"pruned": job.id}
        if kind == "wait_execution":
            job = await self.wait_execution(frame.get("project", self.project), frame["job"])
            return {"job": job.model_dump(mode="json", by_alias=True)}
        if kind == "wait_publication":
            project = frame.get("project", self.project)
            changed = asyncio.Event()
            self.service.supervisor.listeners.add(changed)
            try:
                while True:
                    changed.clear()
                    job = self.service.store.read(project, frame["job"])
                    if job.publication == frame["publication"]:
                        return {"job": job.model_dump(mode="json", by_alias=True)}
                    await asyncio.wait_for(changed.wait(), 20)
            finally:
                self.service.supervisor.listeners.discard(changed)
        if kind == "wait_fixed":
            project, identifier = frame.get("project", self.project), frame["job"]
            changed = asyncio.Event()
            self.service.supervisor.listeners.add(changed)
            try:
                while True:
                    changed.clear()
                    job = self.service.store.read(project, identifier)
                    if job.execution in {"completed", "failed", "cancelled", "interrupted"}:
                        break
                    await asyncio.wait_for(changed.wait(), 20)
                control = self.service.supervisor.controls.get(identifier)
                if control and control.task:
                    await asyncio.wait_for(asyncio.shield(control.task), 20)
                task = self.service.publication_tasks.get(project)
                if task:
                    await asyncio.wait_for(asyncio.shield(task), 20)
                return self.service.fixed.reply(self.service.store.read(project, identifier)).model_dump(mode="json", by_alias=True)
            finally:
                self.service.supervisor.listeners.discard(changed)
        if kind == "clone":
            from packages.resume_core.rich_archive import export_rich_archive
            def clone():
                source = self.service.projects.read(self.project)
                project = self.service.projects.import_portable(export_rich_archive(source, {}, {}, {}))
                conversation = self.journal.create_conversation(project)
                return {"project": project, "conversation": conversation.id}
            return await asyncio.to_thread(clone)
        if kind == "stats":
            project = frame.get("project", self.project)
            return await asyncio.to_thread(self.stats, project)
        if kind == "close":
            self.closed = True
            return {"closing": True}
        raise ValueError("Unknown writer bridge command")

    async def wait_execution(self, project, identifier):
        changed = asyncio.Event()
        self.service.supervisor.listeners.add(changed)
        try:
            while True:
                changed.clear()
                job = self.service.store.read(project, identifier)
                if job.execution in {"completed", "failed", "cancelled", "interrupted"}:
                    break
                await asyncio.wait_for(changed.wait(), 20)
            control = self.service.supervisor.controls.get(identifier)
            if control and control.task:
                await asyncio.wait_for(asyncio.shield(control.task), 20)
            return self.service.store.read(project, identifier)
        finally:
            self.service.supervisor.listeners.discard(changed)

    def stats(self, project):
        workspace, checksum = self.service.projects.storage.read_committed(project)
        state = self.service.store.load(project)
        return {"workspace": workspace.model_dump(mode="json", by_alias=True), "workspaceSha256": checksum,
            "state": state.model_dump(mode="json", by_alias=True), "syntheticStarts": len(self.factory.calls),
            "fixedStarts": len(getattr(getattr(self, "fixed_provider", None), "calls", [])),
            "activeSlots": sum(bool(control.slot_granted and control.task and not control.task.done())
                for control in self.service.supervisor.controls.values()), "metadataInspections": self.adapter.inspections,
            "admissionHeld": self.service.admission.locked()}

    async def respond(self, frame):
        try:
            result = await self.handle(frame)
            self.send({"id": frame["id"], "result": result})
        except Exception as error:
            self.send({"id": frame.get("id"), "error": {"type": type(error).__name__, "message": str(error)}})

    async def close(self):
        with self.lock:
            rows, self.holds = list(self.holds.values()), {}
        for row in rows:
            row["thread"].set(); row["async"].set()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)
        self.factory.verify(); self.clock.verify()


async def main(root):
    bridge = Bridge(root)
    await bridge.start()
    inbox = asyncio.Queue()
    def receive():
        for raw in sys.stdin:
            if len(raw.encode()) > 16 * 1024 * 1024:
                bridge.loop.call_soon_threadsafe(inbox.put_nowait, ValueError("Writer bridge frame exceeds its test limit"))
                return
            try:
                frame = json.loads(raw)
                if frame.get("kind") in {"release", "close"}:
                    with bridge.lock:
                        rows = list(bridge.holds.values()) if frame["kind"] == "close" else [bridge.holds.get(frame["token"])]
                    for row in rows:
                        if row is not None:
                            row["thread"].set(); bridge.loop.call_soon_threadsafe(row["async"].set)
                bridge.loop.call_soon_threadsafe(inbox.put_nowait, frame)
            except Exception as error:
                bridge.loop.call_soon_threadsafe(inbox.put_nowait, error)
                return
        bridge.loop.call_soon_threadsafe(inbox.put_nowait, None)
    reader = asyncio.create_task(asyncio.to_thread(receive))
    try:
        while not bridge.closed:
            frame = await inbox.get()
            if frame is None:
                break
            if isinstance(frame, Exception):
                raise frame
            if frame.get("kind") == "close":
                await bridge.respond(frame)
            else:
                task = asyncio.create_task(bridge.respond(frame))
                bridge.tasks.add(task); task.add_done_callback(bridge.tasks.discard)
    finally:
        await bridge.close()
        await reader


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]).resolve()))
