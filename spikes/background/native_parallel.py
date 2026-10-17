"""Run only the authorized ten-turn feasibility matrix on synthetic stores."""

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
from types import SimpleNamespace

from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.agent_store import digest
from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.agent import AgentSettingsRequest
from packages.resume_core.models.background import JobAgentRequestV1
from packages.resume_core.models.rich_document import StyledText, NarrativeCitation
from packages.resume_core.rules import RulesStore
from packages.resume_core.storage import atomic_write
from resume_api.agent.service import AgentConnection
from resume_api.cli.experimental_profile import BINARY, ExperimentalCliProfile
from resume_api.inference_admission import InferenceAdmission, AdmissionTimeout
from resume_api.jobs.appserver import SharedAgentRuntime, SharedContentProvider
from resume_api.jobs.service import JobService
from resume_api.rich_projects import RichProjectService
from resume_api.profile_ownership import native_profile
from .appserver_driver import SharedAppServer
from .appserver_offline import alive
from .native_turn_budget import spend_turn, ROLES, matrix_budget
from tests.support.agent import isolated_project
from tests.recovery.test_background_fixed_jobs import fixed_request, rewrite_command, completion_command
from tests.recovery.test_rich_synchronization import selection
from tools.background_evidence import source_hashes, assert_native_bindings, assert_report, digest as source_digest
from tools.checks import background_spec


HANDOFF = Path("docs/gui/handoffs/BACKGROUND-WORK")
LEDGER = HANDOFF / "native-attempts.json"
PROFILE = Path.home() / "Library/Application Support/FoldCV/cli-experiment"
MODEL = "gpt-6-luna"


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n")


@dataclass
class Participant:
    role: str
    service: object
    workspace: object
    conversation: str
    marker: str
    before: str
    job: object = None
    session: object = None
    attempt: object = None
    runtime: object = None


class Feasibility:
    def __init__(self, root, controlled):
        if root.parent != Path("/private/tmp") or not root.name.startswith("foldcv-nb00b-native-") or root.exists():
            raise ValueError("Use a new owned /private/tmp/foldcv-nb00b-native-* root")
        spec = background_spec()
        self.hashes = source_hashes(spec["sources"])
        context = json.loads((controlled / "context.json").read_bytes())
        validation = json.loads((controlled / "validation.json").read_bytes())
        if context["sourceHashes"] != self.hashes or validation.get("outcome") != "passed" or validation["runId"] != context["runId"]:
            raise ValueError("The complete current controlled gate is required")
        if (validation["sourceSha256"] != source_digest(self.hashes)
                or validation["reportSha256"] != hashlib.sha256((controlled / "execution.json").read_bytes()).hexdigest()):
            raise ValueError("The current controlled report hash is required")
        assert_report(controlled / "execution.json", run_id=context["runId"], suite="fast", sources=self.hashes,
            started_at=context["startedAt"], bindings={**spec["bindings"], **spec["checks"]},
            required_traces=spec["requiredTraces"], required_actions=set(spec["requiredActions"]), required_orders=set(spec["requiredOrders"]))
        ledger = json.loads(LEDGER.read_bytes())
        self.native_cap, prior_matrix, self.entry_spent, _retry = matrix_budget(ledger, "NB00")
        if prior_matrix:
            raise ValueError("This one-shot matrix cannot retry, reset or resume native attempts")
        root.mkdir(mode=0o700)
        self.root, self.spec, self.controlled = root, spec, controlled
        self.groups, self.participants, self.all_participants = [], [], []
        self.ready, self.interrupt_seen, self.target_called = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.arrived, self.charged = set(), 0
        self.condition = asyncio.Condition()
        self.variant, self.wire_path, self.failed = None, None, False
        self.exclusion_checks = []
        self.exclusion_lost = False
        connection = SimpleNamespace(executable=BINARY, experimental_profile=ExperimentalCliProfile(PROFILE))
        self.server = SharedAppServer.native(root / "operations", connection, wire_audit=self.wire)
        write(root / "entry-native-ledger.json", ledger)
        write(root / "source-context.json", dict(at=now(), sourceHashes=self.hashes, controlledEvidence=str(controlled),
            nativePool="NB00", nativeCap=self.native_cap, historicalStarts=self.entry_spent,
            transport="one pinned multiplexed App Server", ordinaryRollout=False,
            scope="Three isolated capacity-one JobServices share one transport; NB04 scheduler and UI are not accepted here."))

    def wire(self, value):
        if self.wire_path is None:
            return
        descriptor = os.open(self.wire_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a") as output:
            output.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
        if value["direction"] == "client" and value["frame"].get("method") == "turn/interrupt":
            self.interrupt_seen.set()

    async def authorize(self, participant, control):
        if source_hashes(self.spec["sources"]) != self.hashes:
            raise ValueError("Frozen native source changed")
        self.arrived.add(participant.role)
        if len(self.arrived) == len(self.participants): self.ready.set()
        await asyncio.wait_for(self.ready.wait(), 12)
        async with self.condition:
            if self.charged >= len(ROLES[self.variant]):
                raise ValueError("Unexpected extra native turn")
            await asyncio.wait_for(self.condition.wait_for(lambda: ROLES[self.variant][self.charged] == participant.role), 12)
            participant.attempt = spend_turn(LEDGER, pool="NB00", variant=self.variant,
                job=control.run_id, source_hashes=self.hashes)
            self.charged += 1
            self.condition.notify_all()

    def check_exclusion(self):
        if self.server.owner_context is None:
            self.exclusion_lost = True
            raise ValueError("Shared profile ownership is absent")
        for action in ("second-api", "maintenance", "login"):
            try:
                with native_profile(ExperimentalCliProfile(PROFILE), threading.Event(), deadline=time.monotonic() + 2,
                        blocking=False, operations_root=self.root / "operations"):
                    self.exclusion_lost = True
                    raise ValueError("Shared profile ownership was lost")
            except AdmissionTimeout:
                self.exclusion_checks.append(dict(at=now(), action=action, result="BUSY", variant=self.variant))
            except Exception:
                self.exclusion_lost = True
                raise

    def session(self, participant, control, original):
        session = original(control)
        participant.session = session
        call = session.call
        first = True
        async def recorded(name, arguments):
            nonlocal first
            result = await call(name, arguments)
            descriptor = os.open(self.root / (participant.attempt["id"] + "-tools.jsonl"),
                os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "a") as output:
                output.write(json.dumps(dict(at=now(), jobId=control.run_id, name=name,
                    arguments=arguments.model_dump(mode="json", by_alias=True) if hasattr(arguments, "model_dump") else arguments,
                    result=result), ensure_ascii=False) + "\n")
            if self.variant == "NB-R05:v01" and first:
                first = False
                if participant.role == "agent-A":
                    self.target_called.set()
                await asyncio.wait_for(self.interrupt_seen.wait(), 20)
            return result
        session.call = recorded
        return session

    async def participant(self, role):
        data = self.root / (self.variant.replace(":", "-") + "-" + role)
        _, storage, workspace, conversation = isolated_project(data)
        marker = self.variant + "/" + role
        block = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
        block.content = [StyledText(type="text", text=marker + ". Built REST APIs in Python. Wrote unit tests with pytest.", styles={})]
        if role == "structured-sync-C":
            block.content[0].text = marker + ". Current job title: Python API Engineer. Built REST APIs in Python. Wrote unit tests with pytest."
            block.provenance = [NarrativeCitation(kind="citation", id="native-linked-narrative",
                recordId="candidate-1", fieldKeys=["title"], evidence=[])]
        storage.save(workspace, {}, {})
        AgentSettingsStore(data).save(AgentSettingsRequest(expectedRevision=1, enabled=True, selectedAgentModel=MODEL), (MODEL,))
        projects = RichProjectService(data / "fixed-operations", RulesStore(data), lambda: None, storage=storage)
        projects.ensure_loaded()
        view = AgentConnection(True, (MODEL,), "synthetic-owned-server-metadata")
        service = JobService(projects, SharedAgentRuntime(self.server), lambda: view,
            enabled=True, admission=InferenceAdmission())
        participant = Participant(role, service, workspace, conversation.id, marker, digest(workspace))
        service.authorize_native = lambda control: self.authorize(participant, control)
        service.runtime.audit = lambda value: setattr(participant, "runtime", value)
        original = service.tools.session
        service.tools.session = lambda control: self.session(participant, control, original)
        provider = SharedContentProvider(self.server, audit=lambda value: setattr(participant, "runtime", value))
        projects.provider_factory = lambda: (provider, MODEL)
        await service.start()
        self.all_participants.append(participant)
        return participant

    async def submit(self, participant):
        service, workspace = participant.service, participant.workspace
        project, state = workspace.project_id, service.project(workspace.project_id)
        request_id = self.variant.replace(":", "-") + "-" + participant.role
        if participant.role.startswith("agent-"):
            request = JobAgentRequestV1(schemaVersion=1, lineage=state.lineage, requestEpoch=state.request_epoch,
                request=dict(clientRequestId=request_id, conversationId=participant.conversation,
                    message="Выполни проверку без правок. Обязательно вызови get_resume_context для полного блока narrative, "
                        "отдельно get_working_facts и check_resume. В конце дословно укажи исходную метку из narrative и кратко "
                        "перечисли подтвержденные факты. Используй только инструменты этого резюме.",
                    allowEdits=False, allowWeb=False, scope={"kind": "resume"}, settingsRevision=2,
                    projectRevision=workspace.project_revision, documentRevision=workspace.document_revision,
                    factsRevision=workspace.project.facts.revision))
            participant.job = (await service.submit(project, request))[0]
        else:
            command = (completion_command(action="native-auto-sync", block="narrative", interpret=True)
                if participant.role == "structured-sync-C" else rewrite_command(workspace))
            if participant.role != "structured-sync-C":
                block = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
                command["request"]["selection"] = selection(workspace,
                    end=len(block.content[0].text.encode("utf-16-le")) // 2).model_dump(by_alias=True)
                command["request"]["instruction"] = "Replace exactly 'Python. Wrote' with 'Python; Wrote'. Preserve the exact marker, all other text, facts and formatting."
            participant.job = (await service.fixed.submit(project, fixed_request(service, project,
                request_id, command)))[0].job

    async def completed(self, participant):
        service, job, project = participant.service, participant.job, participant.workspace.project_id
        changed = asyncio.Event()
        service.supervisor.listeners.add(changed)
        try:
            while job.id not in service.supervisor.controls:
                changed.clear()
                if job.id not in service.supervisor.controls: await asyncio.wait_for(changed.wait(), 200)
            await asyncio.wait_for(asyncio.shield(service.supervisor.controls[job.id].task), 210)
            if not participant.role.startswith("agent-"):
                # Execution cleanup can finish before the separate publisher stores its receipt.
                async with asyncio.timeout(LIMITS.receipt_seconds):
                    while project in service.publication_tasks:
                        await asyncio.shield(service.publication_tasks[project])
        finally:
            service.supervisor.listeners.discard(changed)
        return service.store.read(project, job.id)

    async def finished(self, participant):
        service, project = participant.service, participant.workspace.project_id
        job = await self.completed(participant)
        artifact = participant.attempt["id"] if participant.attempt is not None else participant.role + "-uncharged"
        write(self.root / (artifact + "-job.json"), job.model_dump(mode="json", by_alias=True))
        if participant.runtime is not None:
            write(self.root / (artifact + "-runtime.json"), participant.runtime)
        cancelled = self.variant == "NB-R05:v01" and participant.role == "agent-A"
        if (participant.attempt is None or participant.runtime is None or job.execution != ("cancelled" if cancelled else "completed")
                or not job.attempts[-1].cleanup_verified):
            if job.error is not None:
                raise BackgroundFailure(job.error.code)
            raise ValueError("Native participant did not pass: " + participant.role + "/" + job.execution + "/" + str(job.error))
        runtime = dict(participant.runtime)
        runtime.update(jobId=job.id, role=participant.role, profileExclusionLost=self.exclusion_lost,
            mcpListenerClosed=participant.session is not None and participant.session.listener.fileno() == -1
                and not participant.session.token if participant.role.startswith("agent-") else None)
        if (runtime["nativeStarted"] is not True or runtime["cleanupVerified"] is not True
                or any(runtime[name] is not True for name in ("toolsClosed", "parserClosed", "operationRemoved", "turnResourcesClosed"))
                or runtime["sharedProcessDead"] is not False or self.server.pipe.process.poll() is not None):
            raise ValueError("Native turn cleanup or service ownership was not proved")
        if participant.role.startswith("agent-"):
            if runtime["toolCalls"] < (1 if cancelled else 2) or runtime["mcpListenerClosed"] is not True:
                raise ValueError("Required native tool use or capability cleanup is absent")
        elif not runtime.get("schemaValidated") or runtime.get("logicalAttempts") != 1 or runtime.get("repairTurns") != 0:
            raise ValueError("The fixed native turn did not pass its original one-attempt grammar")
        elif job.publication != "saved" or job.receipt is None or not job.receipt.durable:
            raise ValueError("The fixed native result did not reach durable publication")
        if not participant.role.startswith("agent-"):
            current = service.projects.storage.read_committed(project)[0]
            content = current.project.document.model_dump_json(by_alias=True)
            if participant.marker not in content or any(other.marker in content for other in self.participants if other is not participant):
                raise ValueError("The fixed native result crossed or lost its private context")
            if participant.role == "structured-sync-C":
                from packages.resume_core.rich_fields import set_text
                expected_facts = participant.workspace.project.facts.model_copy(deep=True)
                candidate = next(record for record in expected_facts.records if record.id == "candidate-1")
                actual = next(record for record in current.project.facts.records if record.id == "candidate-1")
                set_text(candidate, "title", "Python API Engineer")
                candidate.revision, candidate.title.revision = actual.revision, actual.title.revision
                expected_facts.revision = current.project.facts.revision
                if current.project.facts != expected_facts:
                    raise ValueError("The eligible native sync changed more than its explicit captured title")
            else:
                expected = participant.workspace.project.document.model_copy(deep=True)
                block = next(block for block in expected.blocks() if block.id == "narrative")
                block.content[0].text = block.content[0].text.replace("Python. Wrote", "Python; Wrote", 1)
                expected.revision = current.project.document.revision
                for before_region, after_region in zip(expected.regions, current.project.document.regions):
                    before_region.revision = after_region.revision
                actual_blocks = {block.id: block for block in current.project.document.blocks()}
                for before_block in expected.blocks():
                    before_block.revision = actual_blocks[before_block.id].revision
                if current.project.document != expected or current.project.facts != participant.workspace.project.facts:
                    raise ValueError("The native selected rewrite changed more than the exact requested punctuation")
            runtime["fixedPublication"] = dict(exactRequestedChange=True,
                jobArtifact=str(HANDOFF / "nb00b-evidence" / self.root.name / (participant.attempt["id"] + "-job.json")))
        if participant.role.startswith("agent-") and not cancelled:
            reply = service.artifacts.record(project, job.id)[1].reply.text
            if participant.marker not in reply or any(other.marker in reply for other in self.participants if other is not participant):
                raise ValueError("Native answer crossed or lost its captured context")
            if digest(service.projects.storage.read_committed(project)[0]) != participant.before:
                raise ValueError("A check-only native agent changed canonical content")
        write(self.root / (participant.attempt["id"] + "-runtime.json"), runtime)
        write(self.root / (participant.attempt["id"] + "-job.json"), job.model_dump(mode="json", by_alias=True))
        participant.runtime = runtime

    def mark(self, participants, status, error=None):
        with (LEDGER.parent / ".native-attempts.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            ledger = json.loads(LEDGER.read_bytes())
            ids = {p.attempt["id"] for p in participants if p.attempt is not None}
            for row in ledger["attempts"]:
                if row["id"] in ids:
                    row.update(status=status, error=error, finishedAt=now())
            write(LEDGER, ledger)

    async def group(self, variant):
        self.variant, self.charged, self.arrived = variant, 0, set()
        self.ready, self.interrupt_seen, self.target_called = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.wire_path = self.root / (variant.replace(":", "-") + "-wire.jsonl")
        roles = ROLES[variant]
        self.participants = []
        try:
            await self.server.prepare(planned=len(roles))
            self.participants = [await self.participant(role) for role in roles]
            for participant in self.participants: await self.submit(participant)
            await asyncio.wait_for(self.ready.wait(), 15)
            await asyncio.to_thread(self.check_exclusion)
            if variant == "NB-R05:v01":
                await asyncio.wait_for(self.target_called.wait(), 40)
                target = self.participants[0]
                await target.service.supervisor.cancel(target.workspace.project_id, target.job.id)
            await asyncio.gather(*(self.finished(participant) for participant in self.participants))
            intervals = [p.runtime for p in self.participants]
            if max(row["startedAt"] for row in intervals) >= min(row["endedAt"] for row in intervals):
                raise ValueError("No true native overlap")
            if source_hashes(self.spec["sources"]) != self.hashes:
                raise ValueError("Native source changed")
            await asyncio.to_thread(self.check_exclusion)
            self.mark(self.participants, "passed")
            self.groups.append(dict(variant=variant, participants=list(self.participants), wire=self.wire_path))
            print(variant + " passed " + str(len(roles)) + " charged turns", flush=True)
        except BaseException as error:
            self.failed = True
            self.mark(self.participants, "failed", getattr(error, "code", "NATIVE_MATRIX_FAILED"))
            write(self.root / "failure.json", dict(at=now(), variant=variant, error=str(error),
                errorType=type(error).__name__,
                transportCause=self.server.fence_code, chargedTurns=sum(p.attempt is not None for p in self.participants),
                nativePool="NB00", noRetry=True, sourceHashes=self.hashes))
            raise
        finally:
            for participant in self.participants: await participant.service.shutdown()
            for participant in self.participants:
                identifier = participant.attempt["id"] if participant.attempt is not None else participant.role + "-uncharged"
                if participant.runtime is not None:
                    write(self.root / (identifier + "-raw-runtime.json"), participant.runtime)
                if participant.job is not None:
                    job = participant.service.store.read(participant.workspace.project_id, participant.job.id)
                    write(self.root / (identifier + "-raw-job.json"), job.model_dump(mode="json", by_alias=True))

    async def run(self):
        try:
            for variant in ROLES:
                if variant.startswith("NB-R05:"): await self.group(variant)
        finally:
            for participant in self.all_participants: await participant.service.shutdown()
            await self.server.close()
            self.wire_path = None
            pids = [row["processPid"] for row in self.server.shutdowns]
            hosts = sorted({pid for row in self.server.shutdowns for pid in row["hostPids"]})
            write(self.root / "owner-shutdown.json", dict(status="stopped", at=now(),
                profileLockReleased=self.server.owner_context is None, ownedPidsGone=all(not alive(pid) for pid in [*pids, *hosts]),
                operationRemoved=not list((self.root / "operations").glob("op-*")), profileExclusionLost=self.exclusion_lost,
                serverGenerations=self.server.shutdowns))
            write(self.root / "profile-exclusion.json", dict(checks=self.exclusion_checks, lost=self.exclusion_lost))
        self.finalize()

    def finalize(self):
        if self.failed or len(self.groups) != 4 or source_hashes(self.spec["sources"]) != self.hashes:
            raise ValueError("The complete unchanged ten-turn matrix is required")
        destination = HANDOFF / "nb00b-evidence" / self.root.name
        destination.mkdir(mode=0o700)
        for path in self.root.iterdir():
            if path.is_file() and path.suffix in {".json", ".jsonl"}:
                shutil.copyfile(path, destination / path.name)
        shutdown_paths = {}
        for row in self.server.shutdowns:
            path = destination / ("generation-" + str(row["generation"]) + "-shutdown.json")
            write(path, dict(status="stopped", serverPid=row["processPid"], hostPids=row["hostPids"],
                ownedPidsGone=row["ownedGroupCleanupVerified"] and row["ownedHostPidsGone"],
                operationRemoved=row["operationRemoved"], profileExclusionLost=self.exclusion_lost))
            shutdown_paths[row["generation"]] = str(path)
        cases = {}
        for group in self.groups:
            participants = group["participants"]
            generation = participants[0].runtime["generation"]
            turns = [dict(role=p.role, attemptId=p.attempt["id"],
                runtimeArtifact=str(destination / (p.attempt["id"] + "-runtime.json"))) for p in participants]
            paths = [*destination.glob("*.json"), *destination.glob("*.jsonl")]
            artifacts = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
            cases[group["variant"]] = dict(outcome="passed", layer="native", turns=turns, artifacts=artifacts,
                shutdownArtifact=shutdown_paths[generation], ownerShutdownArtifact=str(destination / "owner-shutdown.json"),
                wireArtifact=str(destination / group["wire"].name))
        report = dict(status="native_matrix_passed_pending_slice_acceptance", transport="shared_appserver_v1",
            sourceHashes=self.hashes, variants=cases, nativePool="NB00", nativeCap=self.native_cap, nativeStarts=10,
            historicalStarts=self.entry_spent, totalSpent=self.entry_spent + 10,
            ordinaryRollout=False, schedulerIntegrationAccepted=False)
        candidate = destination / "candidate-native-proof.json"
        write(candidate, {**report, "status": "candidate_awaiting_validation"})
        bindings = {name: {**self.spec["nativeBindings"][name], "evidence": str(candidate)} for name in cases}
        assert_native_bindings(bindings, set(cases), Path.cwd(), sources=self.hashes, require_pass=True)
        write(HANDOFF / "nb00b-native.json", report)
        print("All ten native turns passed current feasibility validation", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--controlled-evidence", type=Path, required=True)
    args = parser.parse_args()
    with open("/private/tmp/foldcv-nb-native-live.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(Feasibility(args.root, args.controlled_evidence).run())
