"""Frozen production traces with an independent observable-state oracle."""

import asyncio
from dataclasses import dataclass, field
import hashlib
import json
import random

from packages.resume_core.models import validate_contract
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.project_store import encoded
from spikes.background.corpus import ACTIONS, FIXED_TRANSITIONS, reached_orders
from spikes.background.writer_bridge import Bridge
from tests.recovery.test_background_inverse import mutation, put


def block(workspace, identifier):
    def visit(blocks):
        for item in blocks:
            if item["id"] == identifier:
                return item
            if found := visit(item["children"]):
                return found
        return None
    for region in workspace["project"]["document"]["regions"]:
        if found := visit(region["blocks"]):
            return found
    raise AssertionError("Missing oracle block: " + identifier)


def text_of(value):
    return "".join(item["text"] if item["type"] != "link" else text_of(item["content"]) for item in value)


@dataclass
class ProjectOracle:
    revision: int
    texts: dict[str, str]
    cursor: int = 0
    draft: str | None = None
    status: str = "attached"
    epoch: int = 2
    sequence: int = 0
    deleted: bool = False
    edits: list[tuple[str, str]] = field(default_factory=list)
    generations: dict[str, int] = field(default_factory=dict)


class IntegrationTrace:
    def __init__(self, root, seed, *, transitions=FIXED_TRANSITIONS, identity="NB03:production", capacity=1):
        if capacity not in {1, 3}:
            raise ValueError("Use the frozen capacity one or three policy")
        self.root, self.seed, self.rng = root, seed, random.Random(seed)
        self.transitions, self.identity = transitions, identity
        self.capacity = capacity
        self.observed = asyncio.Event()
        self.bridge, self.earlier_starts = None, 0
        self.projects, self.proofs, self.views, self.models = {}, {}, {}, {}
        self.jobs, self.requests, self.barriers, self.last_manual = {}, {}, {}, {}
        self.expected_jobs, self.hooks, self.events, self.log = {}, {}, [], []
        self.slots, self.starts, self.elapsed_ms = 0, 0, 0

    async def start(self):
        self.root.mkdir(parents=True)
        await self.connect()
        other = await self.bridge.handle({"kind": "clone"})
        self.projects = {"A": {"project": self.bridge.project, "conversation": self.bridge.conversation.id}, "B": other}
        for label in self.projects:
            await self.open(label, "one")
            workspace = self.views[label]["response"]["workspace"]
            self.models[label] = ProjectOracle(workspace["projectRevision"],
                {target: text_of(block(workspace, target)["content"]) for target in ("narrative", "quote")})

    async def connect(self):
        self.bridge = Bridge(self.root, parallel=self.capacity == 3)
        def event(value):
            self.events.append(value)
            self.observed.set()
            if value.get("event") == "hook":
                self.hooks[value["token"]].set()
        self.bridge.send = event
        await self.bridge.start()

    async def http(self, label, tail, body=None, *, contract=None, status=200):
        path = "/v1/rich/projects/" + self.projects[label]["project"] + tail
        result = await self.bridge.handle({"kind": "http", "path": path, "method": "GET" if body is None else "POST",
            **({"body": body} if body is not None else {})})
        assert result["status"] == status, (path, result)
        value = result["value"]
        if contract:
            validate_contract(contract, value)
        return value

    async def open(self, label, incarnation, *, previous=None):
        view = await self.http(label, "/writer", contract="background_writer_view_v1")
        credential = "synthetic_integration_credential_0123456789"
        request = dict(schemaVersion=1, sessionId="session-" + label, incarnation=incarnation, credential=credential,
            canonicalRevision=view["response"]["workspace"]["projectRevision"], canonicalSha256=view["workspaceSha256"], actionCursor=0,
            **({"previousEpoch": previous["epoch"], "previousIncarnation": previous["incarnation"]} if previous else {}))
        view = await self.http(label, "/writer/open", request, contract="background_writer_view_v1")
        self.views[label] = view
        self.proofs[label] = dict(schemaVersion=1, lineage=view["writer"]["lineage"], epoch=view["writer"]["epoch"],
            sessionId=view["writer"]["sessionId"], incarnation=incarnation, credential=credential)

    async def read(self, label):
        view = await self.http(label, "/writer/read", self.proofs[label], contract="background_writer_view_v1")
        self.views[label] = view
        return view

    async def header(self, label):
        view = await self.read(label)
        return dict(schemaVersion=1, proof=self.proofs[label], canonicalRevision=view["response"]["workspace"]["projectRevision"],
            canonicalSha256=view["workspaceSha256"], actionCursor=self.models[label].cursor, touches=[])

    async def hold(self, name, *, job=None):
        token = "hold-" + str(len(self.hooks))
        self.hooks[token] = asyncio.Event()
        await self.bridge.handle(dict(kind="hold", token=token, family="job", name=name, job=job))
        return token

    async def reached(self, token):
        await asyncio.wait_for(self.hooks[token].wait(), 10)

    async def reached_jobs(self, token, jobs):
        while True:
            self.observed.clear()
            reached = {row.get("job") for row in self.events if row.get("token") == token}
            if set(jobs) <= reached:
                return
            await asyncio.wait_for(self.observed.wait(), 10)

    async def release(self, token):
        await self.bridge.handle(dict(kind="release", token=token))

    async def submit(self, label, key, *, edits=True):
        registry = await self.http(label, "/jobs", contract="background_project_v1")
        view = await self.read(label); workspace = view["response"]["workspace"]
        request = dict(schemaVersion=1, lineage=registry["lineage"], requestEpoch=registry["requestEpoch"], request=dict(
            clientRequestId=key, conversationId=self.projects[label]["conversation"], message="Synthetic corpus " + key,
            allowEdits=edits, allowWeb=False, scope={"kind": "resume"}, settingsRevision=2,
            projectRevision=workspace["projectRevision"], documentRevision=workspace["documentRevision"],
            factsRevision=workspace["project"]["facts"]["revision"]))
        self.requests[key] = request
        self.jobs[key] = await self.http(label, "/jobs/agent", request, contract="background_snapshot_v1", status=202)
        return self.jobs[key]

    async def remember(self, action, label, key, result):
        row = dict(action=action, project=label, job=key, result=result, clock=self.elapsed_ms,
            read="narrative", write="quote" if action in {"touch", "undo", "input"} else "narrative")
        starts = self.earlier_starts + len(self.bridge.factory.calls)
        assert starts == self.starts
        for name, model in self.models.items():
            if model.deleted:
                store = self.bridge.service.store
                with store.guard(self.projects[name]["project"], deleted=True) as directory:
                    assert store._read(self.projects[name]["project"], directory).tombstoned
                continue
            stats = await asyncio.to_thread(self.bridge.stats, self.projects[name]["project"])
            workspace, state = stats["workspace"], stats["state"]
            assert stats["activeSlots"] == self.slots and self.slots <= self.capacity
            assert len(state["jobs"]) <= 3 and len(state["proposals"]) <= 2
            assert not self.bridge.service.supervisor.listeners
            assert all(control.owned is None and control.permit is None for control in
                self.bridge.service.supervisor.controls.values() if control.task is not None and control.task.done())
            assert workspace["projectRevision"] == model.revision, (action, name, model.revision, workspace["projectRevision"])
            assert state["writer"]["status"] == model.status
            assert state["writer"]["epoch"] == model.epoch and state["writer"]["acknowledgedCursor"] == model.cursor
            for target, text in model.texts.items():
                assert text_of(block(workspace, target)["content"]) == text, (action, name, target)
            assert len(state["drafts"]) == int(model.draft is not None)
            if model.draft is not None:
                draft = state["drafts"][0]
                payload = self.bridge.service.writers._draft(self.bridge.service.store.projects / state["projectId"],
                    self.bridge.service.store.load(state["projectId"]).drafts[0])
                assert next(item for item in payload.document.blocks() if item.id == "quote").content[0].text == model.draft
                assert draft["sequence"] == model.sequence
            current = {value["key"]: value["generation"] for value in state["generations"]}
            assert all(current.get(key, -1) >= value for key, value in model.generations.items())
            model.generations = current
            for alias, (owner, execution, publication) in self.expected_jobs.items():
                if owner == name:
                    saved = next(item for item in state["jobs"] if item["id"] == self.jobs[alias]["id"])
                    assert (saved["execution"], saved["publication"]) == (execution, publication), (action, alias, saved)
            row["revision" + name], row["cursor" + name] = model.revision, model.cursor
            row["sha256" + name] = stats["workspaceSha256"]
            row["generations" + name] = hashlib.sha256(encoded(current)).hexdigest()
        row["syntheticStarts"] = starts
        self.log.append(row)

    async def execute_job(self, label, key):
        spawn, model, cleanup = await self.hold("before_spawn"), await self.hold("scripted_model_ready"), await self.hold("cleanup_started")
        await self.submit(label, key); await self.reached(spawn)
        self.expected_jobs[key] = label, "starting", "none"; self.slots = 1
        await self.remember("submit", label, key, "accepted")
        replay = await self.http(label, "/jobs/agent", self.requests[key], contract="background_snapshot_v1")
        assert replay["id"] == self.jobs[key]["id"]
        await self.remember("duplicate", label, key, "replay")
        await self.release(spawn); await self.reached(model)
        self.expected_jobs[key] = label, "running", "none"; self.starts += 1
        await self.remember("start", label, key, "started")
        await self.release(model); await self.reached(cleanup)
        self.expected_jobs[key] = label, "running", "waiting_for_sync"
        await self.remember("propose", label, key, "stored")
        await self.release(cleanup)
        await self.bridge.handle(dict(kind="wait_job", project=self.projects[label]["project"], job=self.jobs[key]["id"]))
        self.expected_jobs[key] = label, "completed", "waiting_for_sync"; self.slots = 0
        await self.remember("runtime_exit", label, key, "released")

    async def execute_pair(self):
        spawn, model = await self.hold("before_spawn"), await self.hold("scripted_model_ready")
        await self.submit("A", "one")
        await self.submit("B", "two")
        jobs = [self.jobs[key]["id"] for key in ("one", "two")]
        cleanup = {key: await self.hold("cleanup_started", job=self.jobs[key]["id"]) for key in ("one", "two")}
        await self.reached_jobs(spawn, jobs)
        self.slots = 2
        for label, key in (("A", "one"), ("B", "two")):
            self.expected_jobs[key] = label, "starting", "none"
        for label, key in (("A", "one"), ("B", "two")):
            await self.remember("submit", label, key, "accepted")
            replay = await self.http(label, "/jobs/agent", self.requests[key], contract="background_snapshot_v1")
            assert replay["id"] == self.jobs[key]["id"]
            await self.remember("duplicate", label, key, "replay")
        await self.release(spawn)
        await self.reached_jobs(model, jobs)
        self.starts += 2
        for label, key in (("A", "one"), ("B", "two")):
            self.expected_jobs[key] = label, "running", "none"
        for label, key in (("A", "one"), ("B", "two")):
            await self.remember("start", label, key, "started")
        await self.release(model)
        for token in cleanup.values():
            await self.reached(token)
        for label, key in (("A", "one"), ("B", "two")):
            self.expected_jobs[key] = label, "running", "waiting_for_sync"
        for label, key in (("A", "one"), ("B", "two")):
            await self.remember("propose", label, key, "stored")
        order = [("A", "one"), ("B", "two")]
        self.rng.shuffle(order)
        for label, key in order:
            await self.release(cleanup[key])
            await self.bridge.handle(dict(kind="wait_job", project=self.projects[label]["project"], job=self.jobs[key]["id"]))
            self.expected_jobs[key] = label, "completed", "waiting_for_sync"
            self.slots -= 1
            await self.remember("runtime_exit", label, key, "released")

    async def barrier(self, label):
        header = await self.header(label)
        value = await self.http(label, "/writer/barrier", {**header, "generation": self.views[label]["writer"]["barrierGeneration"] + 1,
            "touchGeneration": self.views[label]["writer"]["touchGeneration"], "token": "synthetic_corpus_barrier_token_0123456789"}, contract="background_barrier_v1")
        self.barriers[label] = dict(schemaVersion=1, proof=self.proofs[label], generation=value["generation"], token=value["token"])

    async def publish(self, label, key, *, rejected=False):
        proposal = await self.http(label, "/jobs/" + self.jobs[key]["id"] + "/proposal/read", {}, contract="background_proposal_v1")
        result = await self.http(label, "/writer/publish", {**self.barriers[label], "jobId": self.jobs[key]["id"],
            "proposalSha256": proposal["payloadSha256"]}, status=409 if rejected else 200)
        if rejected:
            assert result["error"]["code"] == "WRITER_UNKNOWN"
            await self.remember("claim", label, key, "rejected")
            return
        validate_contract("background_writer_publication_v1", result)
        self.views[label], self.jobs[key] = result["view"], result["job"]
        self.models[label].texts["narrative"] = "Scripted bridge change" + self.models[label].texts["narrative"][6:]
        self.models[label].revision += 1
        self.expected_jobs[key] = label, "completed", "saved"
        await self.remember("claim", label, key, "claimed")

    async def edit(self, label, action):
        model = self.models[label]
        view = await self.read(label)
        workspace = view["response"]["workspace"]
        target, text = (model.edits.pop() if action == "undo" else ("quote", f"Edit {self.seed}:{len(self.log)}"))
        if action != "undo":
            model.edits.append((target, model.texts[target]))
        before = WorkspaceV6.model_validate(workspace)
        request = mutation(before, [put(before, target, text=text)], f"manual-{self.seed}-{len(self.log)}")
        request.kind, request.capture.session_id = "undo" if action == "undo" else "typing", self.proofs[label]["sessionId"]
        header = await self.header(label); model.cursor += 1
        payload = {**header, "actionCursor": model.cursor, "touches": [{"cursor": model.cursor, "mutation": request.model_dump(by_alias=True)}],
            "mutation": request.model_dump(by_alias=True)}
        self.views[label] = await self.http(label, "/writer/save", payload, contract="background_writer_view_v1")
        self.last_manual[label] = payload
        model.revision += 1; model.texts[target] = text
        await self.remember(action, label, "one" if label == "A" else "two", "touched")

    async def checkpoint(self, label):
        model = self.models[label]
        view = await self.read(label); before = WorkspaceV6.model_validate(view["response"]["workspace"])
        document = before.project.document.model_copy(deep=True)
        text = f"Retained {self.seed}:{len(self.log)}"
        next(item for item in document.blocks() if item.id == "quote").content[0].text = text
        request = mutation(before, [put(before, "quote", text=text)], "draft-touch-" + str(len(self.log)))
        request.capture.session_id = self.proofs[label]["sessionId"]
        model.sequence += 1
        payload = dict(schemaVersion=1, proof=self.proofs[label], id="draft-" + label, sequence=model.sequence,
            actionCursor=model.cursor + 1, baseRevision=model.revision, baseSha256=view["workspaceSha256"],
            payload=dict(schemaVersion=1, document=document.model_dump(by_alias=True), facts=before.project.facts.model_dump(by_alias=True),
                touches=[dict(cursor=model.cursor + 1, mutation=request.model_dump(by_alias=True))], outbox=[], assetPins=[]))
        self.views[label] = view
        await self.http(label, "/writer/checkpoint", payload, contract="background_draft_v1")
        model.draft, model.status = text, "recovering"
        await self.remember("input", label, "one" if label == "A" else "two", "checkpointed")

    async def resolve(self, label):
        model = self.models[label]; view = await self.read(label); record = view["drafts"][0]
        command = dict(schemaVersion=1, proof=self.proofs[label], id=record["id"], sequence=record["sequence"],
            payloadSha256=record["payloadSha256"], canonicalRevision=model.revision, canonicalSha256=view["workspaceSha256"])
        self.views[label] = await self.http(label, "/writer/draft/discard", command, contract="background_writer_view_v1")
        model.draft, model.status = None, "attached"; model.cursor += 1
        await self.remember("resolve", label, "one" if label == "A" else "two", "explicit_discard")

    async def run(self):
        try:
            await self.start()
            if self.capacity == 3:
                await self.execute_pair()
            else:
                await self.execute_job("A", "one")
            await self.barrier("A"); await self.publish("A", "one")
            await self.http("A", "/writer/revoke", self.barriers["A"])
            await self.bridge.handle(dict(kind="advance", seconds=0.75)); self.elapsed_ms += 750
            await self.remember("timeout", "A", "one", "recovering")
            await self.checkpoint("A")
            receipt = await self.http("A", "/jobs/" + self.jobs["one"]["id"] + "/read", {}, contract="background_snapshot_v1")
            assert receipt["receipt"] == self.jobs["one"]["receipt"]
            await self.remember("deliver", "A", "one", "saved")
            await self.resolve("A"); await self.edit("A", "touch"); await self.edit("A", "undo")
            await self.http("A", "/writer/detach", await self.header("A"), contract="background_writer_view_v1")
            self.models["A"].status = "clean_detached"; await self.remember("detach", "A", "one", "writer_changed")
            await self.open("A", "two"); self.models["A"].epoch += 1; self.models["A"].cursor = self.models["A"].sequence = 0
            self.models["A"].status = "attached"; await self.remember("attach", "A", "one", "writer_changed")
            if self.capacity == 1:
                await self.execute_job("B", "two")
            await self.barrier("B")
            await self.http("B", "/writer/revoke", self.barriers["B"])
            await self.remember("timeout", "B", "two", "revoked"); await self.publish("B", "two", rejected=True)
            hold = await self.hold("before_spawn")
            await self.submit("B", "three", edits=False); await self.reached(hold)
            self.expected_jobs["three"] = "B", "starting", "none"; self.slots = 1
            await self.remember("submit", "B", "three", "accepted")
            await self.http("B", "/jobs/" + self.jobs["three"]["id"] + "/cancel", {}, contract="background_snapshot_v1")
            await self.release(hold); await self.bridge.service.supervisor.controls[self.jobs["three"]["id"]].task
            self.expected_jobs["three"] = "B", "cancelled", "none"; self.slots = 0
            await self.remember("stop", "B", "three", "cancelled")
            previous = {key: value.copy() for key, value in self.proofs.items()}
            self.earlier_starts += len(self.bridge.factory.calls)
            await self.bridge.close(); await self.connect()
            for model in self.models.values(): model.status = "recovering"
            await self.remember("restart", "B", "two", "recovered_without_inference")
            for label, incarnation in (("A", "one"), ("B", "two")):
                await self.open(label, incarnation, previous=previous[label]); self.models[label].status = "attached"
                await self.remember("attach", label, "one" if label == "A" else "two", "writer_changed")
            await self.http("B", "/jobs/" + self.jobs["two"]["id"] + "/cancel", {}, contract="background_snapshot_v1")
            self.expected_jobs["two"] = "B", "completed", "cancelled"
            await self.remember("stop", "B", "two", "cancelled")
            while len(self.log) < self.transitions - 1:
                label = self.rng.choice(("A", "B")); model = self.models[label]
                if model.draft is not None:
                    await self.resolve(label); continue
                action = self.rng.choice(("touch", "touch", "undo", "input", "duplicate", "tick", "heartbeat", "deliver"))
                if action == "undo" and not model.edits: action = "touch"
                if action in {"touch", "undo"}: await self.edit(label, action)
                elif action == "input": await self.checkpoint(label)
                elif action == "duplicate" and label in self.last_manual:
                    before = model.revision
                    value = await self.http(label, "/writer/save", self.last_manual[label], contract="background_writer_view_v1")
                    assert value["replayed"] and value["response"]["workspace"]["projectRevision"] == before
                    await self.remember(action, label, "one" if label == "A" else "two", "replay")
                elif action == "deliver":
                    value = await self.http("A", "/jobs/" + self.jobs["one"]["id"] + "/read", {}, contract="background_snapshot_v1")
                    assert value["receipt"] == receipt["receipt"]
                    await self.remember(action, "A", "one", "saved")
                else:
                    await self.bridge.handle(dict(kind="advance", seconds=0.001)); self.elapsed_ms += 1
                    await self.http(label, "/writer/heartbeat", self.proofs[label], contract="background_writer_view_v1")
                    await self.remember("tick" if action == "tick" else "heartbeat", label, "one" if label == "A" else "two", "advanced")
            await self.http("B", "/delete", {"confirmed": True})
            self.models["B"].deleted = True
            late = await self.http("B", "/writer/heartbeat", self.proofs["B"], status=410)
            assert late["error"]["code"] == "PROJECT_DELETED"
            await self.remember("delete", "B", "two", "tombstoned")
            actions = sorted({row["action"] for row in self.log if row["result"] != "rejected"})
            assert set(ACTIONS) <= set(actions)
            assert len(self.log) == self.transitions
            return dict(id=f"{self.identity}:{self.capacity}:{self.seed}", seed=self.seed, capacity=self.capacity, transitions=len(self.log),
                actions=actions, orders=reached_orders(self.log), log=self.log, scope="production_integration")
        except BaseException as error:
            (self.root / "failure-trace.json").write_text(json.dumps(dict(seed=self.seed, log=self.log,
                hooks=self.events, reason=str(error)), ensure_ascii=False, indent=2) + "\n")
            raise
        finally:
            if self.bridge is not None:
                await self.bridge.close()
