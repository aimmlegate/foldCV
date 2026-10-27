"""Prove the six authorized final turns through one parallel JobService."""

import argparse
import asyncio
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
from types import SimpleNamespace

from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.agent_store import digest
from packages.resume_core.models.agent import AgentSettingsRequest
from packages.resume_core.models.background import JobAgentRequestV1, WriterBarrierAckV1, WriterOpenV1, WriterProofV1
from packages.resume_core.models.rich_document import NarrativeCitation, StyledText
from packages.resume_core.rules import RulesStore
from resume_api.agent.service import AgentConnection
from resume_api.cli.experimental_profile import BINARY, ExperimentalCliProfile
from resume_api.inference_admission import AdmissionTimeout, InferenceAdmission
from resume_api.jobs.appserver import SharedContentProvider
from resume_api.jobs.service import JobService
from resume_api.profile_ownership import native_profile
from resume_api.rich_projects import RichProjectService
from resume_api.agent.host_profile import check_host
from tests.recovery.test_background_agent import hold_writer
from tests.recovery.test_background_fixed_jobs import completion_command, fixed_request, rewrite_command
from tests.recovery.test_rich_synchronization import selection
from tests.support.agent import isolated_project
from tools.background_evidence import assert_native_bindings, assert_report, source_hashes, digest as source_digest
from tools.checks import background_spec
from .appserver_driver import SharedAppServer
from .appserver_offline import alive
from .native_parallel import Participant, PROFILE, MODEL, now, write
from .native_turn_budget import ROLES, spend_turn, matrix_budget

HANDOFF = Path("docs/gui/handoffs/BACKGROUND-WORK")
LEDGER = HANDOFF / "native-attempts.json"
GROUPS = ("NB-X03:v03", "NB-X03:v04")
TEXT = "Built REST APIs in Python. Wrote unit tests with pytest."


class IntegratedProof:
    def __init__(self, root, controlled):
        if root.parent != Path("/private/tmp") or not root.name.startswith("foldcv-nb07b-native-") or root.exists():
            raise ValueError("Use a new owned /private/tmp/foldcv-nb07b-native-* root")
        spec = background_spec()
        hashes = source_hashes(spec["sources"])
        context = json.loads((controlled / "context.json").read_bytes())
        validation = json.loads((controlled / "validation.json").read_bytes())
        if (validation["outcome"] != "passed" or validation["runId"] != context["runId"]
                or context["sourceHashes"] != hashes or validation["sourceSha256"] != source_digest(hashes)
                or validation["reportSha256"] != hashlib.sha256((controlled / "execution.json").read_bytes()).hexdigest()):
            raise ValueError("The complete current fast gate is required")
        assert_report(controlled / "execution.json", run_id=context["runId"], suite="fast", sources=hashes,
            started_at=context["startedAt"], bindings={**spec["bindings"], **spec["checks"]},
            required_traces=spec["requiredTraces"], required_actions=set(spec["requiredActions"]), required_orders=set(spec["requiredOrders"]))
        ledger = json.loads(LEDGER.read_bytes())
        cap, rows, _, _ = matrix_budget(ledger, "NB07b")
        if rows or cap != 6:
            raise ValueError("This six-turn proof cannot retry or resume a native matrix")
        ExperimentalCliProfile(PROFILE).check_binary()
        check_host()
        if not (PROFILE / ".foldcv-cli-experiment-v1").is_file():
            raise ValueError("The existing isolated authenticated profile is required")
        self.initialize(root, controlled, spec, hashes)

    def initialize(self, root, controlled, spec, hashes):
        root.mkdir(mode=0o700)
        self.root, self.controlled, self.spec, self.hashes = root, controlled, spec, hashes
        self.groups, self.participants, self.services = [], [], []
        self.failed = False
        self.exclusion_lost, self.exclusion_checks = False, []
        write(root / "entry-native-ledger.json", json.loads(LEDGER.read_bytes()))
        write(root / "source-context.json", dict(at=now(), sourceHashes=hashes, controlledEvidence=str(controlled),
            nativePool="NB07b", nativeCap=6, ordinaryRollout=False,
            scope="One integrated capacity-three JobService owns one shared App Server per group."))

    def wire(self, value):
        with self.wire_path.open("a") as output:
            output.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")

    def audit(self, value):
        participant = next(p for p in self.participants if p.job.id == value["job"])
        participant.runtime = {**value, "error": value.get("error")}
        write(self.directory / (participant.attempt["id"] + "-raw-runtime.json"), participant.runtime)

    async def observe(self, name, identifier):
        if name == "slot_granted":
            self.service.runtime.audit = self.audit
            provider, _model = self.service.content_provider()
            provider.audit = self.audit
        if name == "child_started":
            self.started.add(identifier)
            if len(self.started) == 3:
                await asyncio.to_thread(self.check_exclusion)
                self.overlap.set()
        self.resources.append(dict(at=now(), event=name, job=identifier,
            positions=len(self.service.supervisor.active_controls), permits=len(self.service.parallel_owner.permits)))

    def check_exclusion(self):
        if self.server.owner_context is None:
            self.exclusion_lost = True
            raise ValueError("The integrated server lost its profile owner")
        for action in ("second-api", "maintenance", "login"):
            try:
                with native_profile(ExperimentalCliProfile(PROFILE), threading.Event(), deadline=time.monotonic() + 2,
                        blocking=False, operations_root=self.directory / "operations"):
                    raise ValueError("A second profile owner entered during the final triple")
            except AdmissionTimeout:
                self.exclusion_checks.append(dict(at=now(), variant=self.variant, action=action, result="BUSY"))
            except BaseException:
                self.exclusion_lost = True
                raise

    async def authorize(self, control):
        if self.failed or source_hashes(self.spec["sources"]) != self.hashes:
            raise ValueError("The frozen final native source changed")
        participant = next(p for p in self.participants if p.workspace.project_id == control.project_id)
        self.arrived.add(participant.role)
        if len(self.arrived) == 3:
            self.ready.set()
        await asyncio.wait_for(self.ready.wait(), 12)
        async with self.condition:
            await asyncio.wait_for(self.condition.wait_for(lambda: self.failed or self.charged < 3
                and ROLES[self.variant][self.charged] == participant.role), 12)
            if self.failed:
                raise ValueError("Native dispatch is stopped")
            participant.attempt = spend_turn(LEDGER, pool="NB07b", variant=self.variant,
                job=control.run_id, source_hashes=self.hashes)
            self.charged += 1
            self.condition.notify_all()

    def session(self, control):
        session = self.original_session(control)
        participant = next(p for p in self.participants if p.workspace.project_id == control.project_id)
        participant.session = session
        call = session.call
        async def recorded(name, arguments):
            await asyncio.wait_for(self.overlap.wait(), 20)
            result = await call(name, arguments)
            participant.calls.append(dict(name=name, result=result))
            with (self.directory / (participant.attempt["id"] + "-tools.jsonl")).open("a") as output:
                output.write(json.dumps(dict(at=now(), jobId=control.run_id, name=name,
                    arguments=arguments.model_dump(mode="json", by_alias=True) if hasattr(arguments, "model_dump") else arguments,
                    result=result), ensure_ascii=False) + "\n")
            return result
        session.call = recorded
        return session

    async def prepare(self, variant):
        self.variant, self.charged, self.arrived, self.started = variant, 0, set(), set()
        self.ready, self.overlap, self.condition = asyncio.Event(), asyncio.Event(), asyncio.Condition()
        self.resources = []
        self.directory = self.root / variant.replace(":", "-")
        self.directory.mkdir(mode=0o700)
        self.wire_path = self.directory / "wire.jsonl"
        data = self.directory / "data"
        journal, storage, baseline, _conversation = isolated_project(data)
        AgentSettingsStore(data).save(AgentSettingsRequest(expectedRevision=1, enabled=True, selectedAgentModel=MODEL), (MODEL,))
        projects = RichProjectService(self.directory / "fixed-operations", RulesStore(data), lambda: None, storage=storage)
        projects.ensure_loaded()
        connection = SimpleNamespace(executable=BINARY, experimental_profile=ExperimentalCliProfile(PROFILE))
        self.server = SharedAppServer.native(self.directory / "operations", connection, wire_audit=self.wire)
        projects.provider_factory = lambda: (SharedContentProvider(self.server), MODEL)
        self.service = JobService(projects, None, lambda: AgentConnection(True, (MODEL,), "synthetic-final-owned-metadata"),
            enabled=True, parallel=True, shared_native=True, server_factory=lambda: self.server,
            admission=InferenceAdmission(), authorize_native=self.authorize, observer=self.observe)
        self.services.append(self.service)
        self.original_session = self.service.tools.session
        self.service.tools.session = self.session
        self.participants = []
        for index, role in enumerate(ROLES[variant]):
            workspace = baseline.model_copy(deep=True)
            workspace.project_id = workspace.project.project_id = "final-project-" + str(index + 1)
            marker = variant + "/" + role
            block = next(b for b in workspace.project.document.blocks() if b.id == "narrative")
            text = marker + ". " + TEXT
            if role == "structured-sync-C":
                text = marker + ". Current job title: Python API Engineer. " + TEXT
                block.provenance = [NarrativeCitation(kind="citation", id="final-title-link",
                    recordId="candidate-1", fieldKeys=["title"], evidence=[])]
            block.content = [StyledText(type="text", text=text, styles={})]
            storage.save(workspace, {}, {})
            current, checksum = storage.read_committed(workspace.project_id)
            self.service.publication.adopt(workspace.project_id, current, checksum, preserve=False)
            conversation = journal.create_conversation(workspace.project_id)
            participant = Participant(role, self.service, workspace, conversation.id, marker, digest(workspace))
            participant.calls = []
            self.participants.append(participant)
            write(self.directory / (role + "-baseline.json"), workspace.model_dump(mode="json", by_alias=True))
        await self.service.start()
        if variant == "NB-X03:v03":
            self.deferred_proof = hold_writer(self.service, self.participants[1].workspace)
        self.service.supervisor.pause("RATE_LIMITED")

    async def submit(self, participant):
        service, workspace = self.service, participant.workspace
        project, state = workspace.project_id, service.project(workspace.project_id)
        key = self.variant.replace(":", "-") + "-" + participant.role
        if participant.role.startswith("agent-"):
            editing = self.variant == "NB-X03:v03"
            message = ("Read the whole narrative block with get_resume_context. Replace only the exact word Built with Developed. "
                "Preserve the marker, all other text, facts and formatting. Prepare exactly one batch and apply it exactly once. "
                "If waiting_for_sync or needs_review, finish without retry, polling or claiming saved. "
                "Only saved with durable:true is saved. Include the exact narrative marker in your short final reply."
                if editing else "Read narrative with get_resume_context and call get_working_facts. Make no edits. "
                "Include the exact narrative marker and a short factual summary in your final reply.")
            request = JobAgentRequestV1(schemaVersion=1, lineage=state.lineage, requestEpoch=state.request_epoch,
                request=dict(clientRequestId=key, conversationId=participant.conversation, message=message,
                    allowEdits=editing, allowWeb=False, scope={"kind": "resume"}, settingsRevision=2,
                    projectRevision=workspace.project_revision, documentRevision=workspace.document_revision,
                    factsRevision=workspace.project.facts.revision))
            participant.job = (await service.submit(project, request))[0]
        else:
            command = completion_command(action="final-auto-sync", block="narrative", interpret=True) if participant.role == "structured-sync-C" else rewrite_command(workspace)
            if participant.role != "structured-sync-C":
                block = next(b for b in workspace.project.document.blocks() if b.id == "narrative")
                command["request"]["selection"] = selection(workspace,
                    end=len(block.content[0].text.encode("utf-16-le")) // 2).model_dump(by_alias=True)
                command["request"]["instruction"] = "Replace exactly 'Python. Wrote' with 'Python; Wrote'. Preserve the exact marker, all other text, facts and formatting."
            participant.job = (await service.fixed.submit(project, fixed_request(service, project, key, command)))[0].job

    async def execution(self, participant):
        await asyncio.wait_for(self.ready.wait(), 15)
        await asyncio.wait_for(asyncio.shield(self.service.supervisor.controls[participant.job.id].task), 210)
        job = self.service.store.read(participant.workspace.project_id, participant.job.id)
        write(self.directory / (participant.role + "-after-execution.json"), job.model_dump(mode="json", by_alias=True))
        if job.execution != "completed" or not job.attempts[-1].cleanup_verified or participant.runtime is None:
            raise ValueError("Final native execution failed: " + participant.role + "/" + str(job.error))
        runtime = participant.runtime
        if any(runtime.get(key) is not True for key in ("nativeStarted", "cleanupVerified", "toolsClosed", "parserClosed", "operationRemoved", "turnResourcesClosed")):
            raise ValueError("Final native turn resources did not close")
        if runtime["sharedProcessDead"] is not False:
            raise ValueError("A turn claimed ownership of the shared process")
        return job

    def return_writer(self, participant):
        project, service, old = participant.workspace.project_id, self.service, self.deferred_proof
        service.writers.suspend(project, old)
        current, checksum = service.projects.storage.read_committed(project)
        credential = old.credential
        view = service.writers.open(project, WriterOpenV1(schemaVersion=1, sessionId=old.session_id,
            incarnation="final-returned-editor", credential=credential, previousEpoch=old.epoch,
            previousIncarnation=old.incarnation, canonicalRevision=current.project_revision, canonicalSha256=checksum, actionCursor=0))
        proof = WriterProofV1(schemaVersion=1, lineage=view.writer.lineage, epoch=view.writer.epoch,
            sessionId=view.writer.session_id, incarnation=view.writer.incarnation, credential=credential)
        service.writers.barrier(project, WriterBarrierAckV1(schemaVersion=1, proof=proof,
            canonicalRevision=current.project_revision, canonicalSha256=checksum, actionCursor=0, touches=[],
            generation=view.writer.barrier_generation + 1, touchGeneration=view.writer.touch_generation,
            token="synthetic_final_barrier_token_0123456789"))
        from packages.resume_core.background_publication import proposal_in
        job = service.store.read(project, participant.job.id)
        proposal = proposal_in(service.store.load(project), job)
        return service.publication.publish(project, job.id, proposal.payload_sha256)

    async def finish(self, participant):
        service, project = self.service, participant.workspace.project_id
        job = await self.execution(participant)
        deferred = self.variant == "NB-X03:v03" and participant.role == "agent-B"
        if deferred:
            if job.publication != "waiting_for_sync" or job.receipt is not None or digest(service.projects.storage.read_committed(project)[0]) != participant.before:
                raise ValueError("Deferred canonical content changed before writer return")
            job = await asyncio.to_thread(self.return_writer, participant)
        if project in service.publication_tasks:
            await asyncio.wait_for(asyncio.shield(service.publication_tasks[project]), 15)
        job = service.store.read(project, participant.job.id)
        current = service.projects.storage.read_committed(project)[0]
        runtime = {**participant.runtime, "jobId": job.id, "role": participant.role, "profileExclusionLost": self.exclusion_lost}
        agent = participant.role.startswith("agent-")
        if agent:
            session = participant.session
            runtime["mcpListenerClosed"] = session is not None and session.listener.fileno() == -1 and not session.token
            record = service.artifacts.record(project, job.id)[1]
            if record.reply is None or participant.marker not in record.reply.text or any(p.marker in record.reply.text for p in self.participants if p is not participant):
                raise ValueError("Agent reply lost or crossed its captured project")
            if self.variant == "NB-X03:v03":
                prepared = [c for c in participant.calls if c["name"] == "prepare_edit_batch"]
                applied = [c for c in participant.calls if c["name"] == "apply_edit_batch"]
                if len(prepared) != 1 or len(applied) != 1 or len(record.batches) != 1 or job.publication != "saved" or job.receipt is None or not job.receipt.durable:
                    raise ValueError("Exact one-batch agent publication was not proved")
                disposition = "waiting_for_sync" if deferred else "saved"
                if applied[0]["result"]["disposition"] != disposition:
                    raise ValueError("Wrong immediate/deferred apply result")
                self.exact_document(participant, current, "Built", "Developed")
                runtime["publication"] = dict(exactRequestedText=True, onePreparedBatch=True, oneApply=True,
                    durableReceipt=True, noNewTurnForSave=True, factsAndOtherContentUnchanged=True,
                    turnResourcesExitedBeforeSave=deferred, canonicalUnchangedUntilReturn=deferred)
            elif digest(current) != participant.before:
                raise ValueError("The check-only final agent changed canonical content")
        else:
            if job.publication != "saved" or job.receipt is None or not job.receipt.durable:
                raise ValueError("The fixed result has no durable receipt")
            if participant.role == "structured-sync-C":
                from packages.resume_core.rich_fields import set_text
                expected = participant.workspace.project.facts.model_copy(deep=True)
                candidate = next(r for r in expected.records if r.id == "candidate-1")
                actual = next(r for r in current.project.facts.records if r.id == "candidate-1")
                set_text(candidate, "title", "Python API Engineer")
                candidate.revision, candidate.title.revision = actual.revision, actual.title.revision
                expected.revision = current.project.facts.revision
                document = participant.workspace.project.document.model_copy(deep=True)
                document.revision = current.project.document.revision
                if current.project.facts != expected or current.project.document != document:
                    raise ValueError("Automatic sync changed more than its captured title")
            else:
                self.exact_document(participant, current, "Python. Wrote", "Python; Wrote")
            runtime["fixedPublication"] = dict(exactRequestedChange=True,
                jobArtifact=str(HANDOFF / "nb07b-evidence" / self.root.name / self.directory.name / (participant.attempt["id"] + "-job.json")))
        participant.runtime = runtime
        write(self.directory / (participant.attempt["id"] + "-runtime.json"), runtime)
        write(self.directory / (participant.attempt["id"] + "-job.json"), job.model_dump(mode="json", by_alias=True))
        write(self.directory / (participant.role + "-final.json"), current.model_dump(mode="json", by_alias=True))

    @staticmethod
    def exact_document(participant, current, before, after):
        expected = participant.workspace.project.document.model_copy(deep=True)
        block = next(b for b in expected.blocks() if b.id == "narrative")
        block.content[0].text = block.content[0].text.replace(before, after, 1)
        expected.revision = current.project.document.revision
        for left, right in zip(expected.regions, current.project.document.regions):
            left.revision = right.revision
        actual = {b.id: b for b in current.project.document.blocks()}
        for b in expected.blocks():
            b.revision = actual[b.id].revision
        actual_document = current.project.document.model_copy(deep=True)
        for document in (expected, actual_document):
            changed = next(b for b in document.blocks() if b.id == "narrative")
            merged = []
            for span in changed.content:
                if merged and span.type == merged[-1].type == "text" and span.styles == merged[-1].styles:
                    merged[-1].text += span.text
                else:
                    merged.append(span.model_copy(deep=True))
            changed.content = merged
        if expected != actual_document or current.project.facts != participant.workspace.project.facts:
            raise ValueError("The final edit changed more than its exact requested text")

    def mark(self, status, error=None):
        with (LEDGER.parent / ".native-attempts.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            ledger = json.loads(LEDGER.read_bytes())
            ids = {p.attempt["id"] for p in self.participants if p.attempt is not None}
            for row in ledger["attempts"]:
                if row["id"] in ids:
                    row.update(status=status, error=error, finishedAt=now())
            write(LEDGER, ledger)

    async def group(self, variant):
        await self.prepare(variant)
        tasks = []
        try:
            for participant in self.participants:
                await self.submit(participant)
            self.service.supervisor.resume(1)
            tasks = [asyncio.create_task(self.finish(p)) for p in self.participants]
            await asyncio.gather(*tasks)
            intervals = [p.runtime for p in self.participants]
            if len({r["serverPid"] for r in intervals}) != 1 or max(r["startedAt"] for r in intervals) >= min(r["endedAt"] for r in intervals):
                raise ValueError("The integrated final triple has no true overlap")
            if source_hashes(self.spec["sources"]) != self.hashes:
                raise ValueError("The final native source changed")
            if self.exclusion_lost or len([r for r in self.exclusion_checks if r["variant"] == variant]) != 3:
                raise ValueError("Final live profile exclusion was not proved")
            await self.service.shutdown()
            await self.server.close()
            self.shutdown()
            self.mark("passed")
            self.groups.append(dict(variant=variant, directory=self.directory, participants=list(self.participants)))
            print(variant + " passed three integrated turns", flush=True)
        except BaseException as error:
            self.failed = True
            self.mark("failed", getattr(error, "code", "FINAL_NATIVE_FAILED"))
            write(self.directory / "failure.json", dict(at=now(), error=str(error), errorType=type(error).__name__,
                transportCause=self.server.fence_code, chargedTurns=self.charged, noRetry=True, nativePool="NB07b"))
            raise
        finally:
            for control in self.service.supervisor.controls.values():
                if control.task is not None and not control.task.done():
                    control.stop()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await self.service.shutdown()
            finally:
                await self.server.close()
                self.shutdown()

    def shutdown(self):
        pids = [r["processPid"] for r in self.server.shutdowns]
        hosts = sorted({pid for r in self.server.shutdowns for pid in r["hostPids"]})
        write(self.directory / "owner-shutdown.json", dict(status="stopped", at=now(),
            profileLockReleased=self.server.owner_context is None and self.service.parallel_owner.login_allowed(),
            ownedPidsGone=all(not alive(pid) for pid in [*pids, *hosts]),
            operationRemoved=not list((self.directory / "operations").glob("op-*")), profileExclusionLost=self.exclusion_lost,
            serverGenerations=self.server.shutdowns))
        write(self.directory / "profile-exclusion.json", dict(lost=self.exclusion_lost,
            checks=[r for r in self.exclusion_checks if r["variant"] == self.variant]))
        write(self.directory / "resources.json", dict(events=self.resources, capacity=3, noninteractiveCapacity=2,
            activePositions=len(self.service.supervisor.active_controls), permits=len(self.service.parallel_owner.permits),
            admissionHeld=self.service.admission.locked(), pendingPublication=len(self.service.publication_tasks)))
        for row in self.server.shutdowns:
            write(self.directory / ("generation-" + str(row["generation"]) + "-shutdown.json"), dict(status="stopped",
                serverPid=row["processPid"], hostPids=row["hostPids"], ownedPidsGone=row["ownedGroupCleanupVerified"] and row["ownedHostPidsGone"],
                operationRemoved=row["operationRemoved"], profileExclusionLost=self.exclusion_lost))

    async def run(self):
        for variant in GROUPS:
            await self.group(variant)
        self.finalize()

    def finalize(self):
        if self.failed or len(self.groups) != 2 or source_hashes(self.spec["sources"]) != self.hashes:
            raise ValueError("The complete unchanged six-turn final proof is required")
        destination = HANDOFF / "nb07b-evidence" / self.root.name
        destination.mkdir(mode=0o700, parents=True)
        for path in self.root.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".jsonl"} and "data" not in path.relative_to(self.root).parts:
                target = destination / path.relative_to(self.root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        artifacts = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob("*") if p.is_file()}
        cases = {}
        for group in self.groups:
            directory = destination / group["directory"].name
            participants = group["participants"]
            cases[group["variant"]] = dict(outcome="passed", layer="native", artifacts=artifacts,
                turns=[dict(role=p.role, attemptId=p.attempt["id"], runtimeArtifact=str(directory / (p.attempt["id"] + "-runtime.json"))) for p in participants],
                shutdownArtifact=str(directory / ("generation-" + str(participants[0].runtime["generation"]) + "-shutdown.json")),
                ownerShutdownArtifact=str(directory / "owner-shutdown.json"), wireArtifact=str(directory / "wire.jsonl"))
        for alias, index in (("NB-X03:v01", 0), ("NB-X03:v02", 1)):
            parent = cases[GROUPS[0]]
            cases[alias] = {**parent, "turns": [parent["turns"][index]], "coveredBy": GROUPS[0]}
        report = dict(status="native_final_matrix_passed_pending_slice_acceptance", transport="shared_appserver_v1",
            sourceHashes=self.hashes, variants=cases, nativePool="NB07b", nativeCap=6, nativeStarts=6,
            ordinaryRollout=False, schedulerIntegrationAccepted=True)
        candidate = destination / "candidate-native-proof.json"
        write(candidate, report)
        bindings = {name: {**self.spec["nativeBindings"][name], "evidence": str(candidate)} for name in cases}
        assert_native_bindings(bindings, set(cases), Path.cwd(), sources=self.hashes, require_pass=True)
        write(HANDOFF / "nb07b-native.json", report)
        print("All six final integrated turns passed native validation", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--controlled-evidence", type=Path, required=True)
    args = parser.parse_args()
    with open("/private/tmp/foldcv-nb-native-live.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(IntegratedProof(args.root, args.controlled_evidence).run())
