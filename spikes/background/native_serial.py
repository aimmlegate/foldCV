"""Final serial proof in an owned synthetic store and native profile."""

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket

import uvicorn

from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.agent import AgentSettingsRequest
from packages.resume_core.models.background import JobAgentRequestV1, WriterOpenV1
from packages.resume_core.models.rich_document import StyledText
from packages.resume_core.storage import atomic_write
from resume_api.app import create_app
from resume_api.agent.runtime import NativeSession
from resume_api.cli.process_runner import ProcessExit, ProcessRunner
from resume_api.lifecycle import SpikeError
from resume_api.cli.experimental_profile import BINARY, ExperimentalCliProfile
from spikes.agent.native_proof import Exclusion, ProofServer, alive
from resume_api.agent.host_profile import check_host
from tools.background_evidence import source_hashes
from tests.support.agent import isolated_project

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "docs/gui/handoffs/BACKGROUND-WORK"
LEDGER = HANDOFF / "native-attempts.json"
PROFILE = Path.home() / "Library/Application Support/FoldCV/cli-experiment"
MODEL = "gpt-6-luna"
TEXT = "Built REST APIs in Python. Wrote unit tests with pytest."
PROMPTS = (
    "В синтетическом резюме прочитай блок narrative. Замени только первое слово Built на Developed, "
    "сохрани остальной текст и факты. Подготовь и примени один пакет. Используй только FoldCV-инструменты. "
    "При waiting_for_sync или needs_review заверши ход без повторов, ожидания, опросов или заявления о сохранении. "
    "Только saved и durable:true означают сохранение. Ответь кратко по-русски.",
    "В синтетическом резюме прочитай блок narrative. Замени только слово Wrote на Added, "
    "сохрани остальной текст и факты. Подготовь и примени один пакет. Используй только FoldCV-инструменты. "
    "При waiting_for_sync или needs_review заверши ход без повторов, ожидания, опросов или заявления о сохранении. "
    "Только saved и durable:true означают сохранение. Ответь кратко по-русски.",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n")


def redact(value, secret, depth=0):
    if depth > 4:
        return "[bounded]"
    if isinstance(value, dict):
        return {str(key)[:128]: "[redacted]" if re.search(r"token|credential|authorization|secret", str(key), re.I)
            else redact(item, secret, depth + 1) for key, item in list(value.items())[:12]}
    if isinstance(value, list):
        return [redact(item, secret, depth + 1) for item in value[:8]]
    if isinstance(value, str):
        text = value.replace(secret, "[redacted]") if secret else value
        text = re.sub(r"(?i)Bearer\s+\S+", "Bearer [redacted]", text)
        text = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", text)
        text = re.sub(r'''(?i)((?:access_token|refresh_token|id_token|credential|authorization|secret)["'\s:=]+)[^\s",}]+''', r"\1[redacted]", text)
        return text[:2048]
    return value if value is None or isinstance(value, (bool, int, float)) else "[unknown]"


@contextmanager
def protocol_diagnostics(root):
    original = NativeSession.accept
    original_run = ProcessRunner.run
    captured = set()
    tokens = set()
    def label(value):
        return str(value)[:128] if value is None or isinstance(value, (str, int, bool)) else "[invalid]"
    def capture(session, raw):
        tokens.add(session.value.token)
        try:
            parsed = json.loads(raw)
            summary = dict(at=now(), method=label(parsed.get("method")), keys=[key[:128] for key in list(parsed)[:12]],
                thread=label(session.thread), turn=label(session.turn)) if isinstance(parsed, dict) else dict(shape="non_object")
            write(root / "protocol-last-frame.json", redact(summary, session.value.token))
        except (OSError, TypeError, ValueError):
            pass
        def retain(error):
            identity = hashlib.sha256(str(session.thread).encode()).hexdigest()[:16]
            if identity in captured:
                return
            try:
                try:
                    frame = json.loads(raw)
                except (TypeError, ValueError):
                    frame = {}
                frame = frame if isinstance(frame, dict) else {}
                params = frame.get("params", {})
                params = params if isinstance(params, dict) else {}
                row = dict(at=now(), exception=type(error).__name__ if error else None,
                    detail=str(error) if error else session.result.error,
                    code=getattr(error, "code", session.result.error), method=label(frame.get("method")),
                    requestId=label(frame.get("id")), parameterKeys=[key[:128] for key in list(params)[:12]],
                    error=frame.get("error", params.get("error", params.get("turn", {}).get("error")
                        if isinstance(params.get("turn"), dict) else None)), willRetry=params.get("willRetry"),
                    itemType=label(params.get("item", {}).get("type")) if isinstance(params.get("item"), dict) else None,
                    turn=label(params.get("turn", {}).get("status")) if isinstance(params.get("turn"), dict) else None)
                safe = redact(row, session.value.token)
                safe["error"] = json.dumps(safe["error"], ensure_ascii=False)[:4096]
                write(root / ("protocol-failure-" + identity + ".json"), safe)
                captured.add(identity)
            except (OSError, TypeError, ValueError):
                pass
        before = session.result.error
        try:
            result = original(session, raw)
        except Exception as error:
            retain(error)
            raise
        if session.result.error is not None and session.result.error != before:
            retain(None)
        return result
    def run(runner, *args, **kwargs):
        try:
            result = original_run(runner, *args, **kwargs)
            if kwargs.get("interactive") is True and isinstance(result, tuple) and len(result) == 2:
                output, errors = result
                if isinstance(output, bytes) and isinstance(errors, bytes):
                    detail = errors.decode("utf-8", "replace")
                    for token in tokens:
                        if token:
                            detail = detail.replace(token, "[redacted]")
                    try:
                        write(root / "protocol-process-exit.json", dict(at=now(), exit="clean_eof",
                            stdoutBytes=len(output), stderr=redact(detail, "")))
                    except OSError:
                        pass
            return result
        except (ProcessExit, SpikeError) as error:
            if kwargs.get("interactive") is True:
                detail = getattr(error, "stderr", b"").decode("utf-8", "replace")
                for token in tokens:
                    if token:
                        detail = detail.replace(token, "[redacted]")
                try:
                    write(root / "protocol-process-failure.json", dict(at=now(), exception=type(error).__name__,
                        code=error.code, stderr=redact(detail, "")))
                except OSError:
                    pass
            raise
    NativeSession.accept = capture
    ProcessRunner.run = run
    try:
        yield
    finally:
        NativeSession.accept = original
        ProcessRunner.run = original_run


def repair_retry_allowed(path, pool, recorded, variant, hashes):
    authority = path.parent / pool["retryAuthority"]
    try:
        grant = json.loads(authority.read_bytes())
        preserved = hashlib.sha256(json.dumps(recorded[:4], sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        previous = [row for row in recorded if row["variant"] == variant]
        deferred_passed = any(row["variant"] == "NB-X03:v02" and row["status"] == "passed"
            and row["sourceHashes"] == hashes for row in recorded)
        valid = (pool.get("retryAuthoritySha256") == hashlib.sha256(authority.read_bytes()).hexdigest()
            and grant["authorized"] is True and grant["schemaVersion"] in {2, 3}
            and grant["baseCap"] == grant["baseSpent"] == 4 and grant["additionalStarts"] == 10
            and grant["capTotal"] == pool["cap"] == 14 and len(recorded) >= 4
            and grant["preservedAttemptsSha256"] == preserved and grant["failedStartsCount"] is True
            and grant["variants"] == ["NB-X03:v01", "NB-X03:v02"] and variant in grant["variants"]
            and grant["allowStalePassedVariant"] is True and grant["reserveDeferredStarts"] == 1)
        if not valid:
            return False
        if grant["schemaVersion"] == 2:
            return (authority.name == "native-repair-authorization.json"
                and all(row["status"] == "failed" or row["status"] == "passed" and row["sourceHashes"] != hashes
                    for row in previous)
                and (variant != "NB-X03:v01" or deferred_passed or pool["cap"] - pool["spent"] >= 2))
        current = [row for row in recorded if row["sourceHashes"] == hashes]
        passed = [row["variant"] for row in current if row["status"] == "passed"]
        order = ["NB-X03:v01", "NB-X03:v02", "NB-X03:v01", "NB-X03:v02"]
        return (authority.name == "native-four-successes-authorization.json"
            and grant["requiredCurrentSuccesses"] == 4 and grant["successesPerVariant"] == 2
            and grant["successOrder"] == order and grant["stopAfterSuccesses"] is True
            and all(row["status"] in {"failed", "passed"} for row in current)
            and len(passed) < 4 and passed == order[:len(passed)] and variant == order[len(passed)]
            and pool["cap"] - pool["spent"] >= 4 - len(passed))
    except (OSError, KeyError, TypeError, ValueError):
        return False


def spend(path, *, variant, job, project, hashes):
    with (path.parent / ".native-attempts.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = json.loads(path.read_bytes())
        pool = ledger["pools"]["NB07a"]
        recorded = [row for row in ledger["attempts"] if row["pool"] == "NB07a"]
        if (variant not in {"NB-X03:v01", "NB-X03:v02"}
                or pool.get("dispatchClosed") is True or not pool["authorized"]
                or type(pool["cap"]) is not int or pool["spent"] >= pool["cap"]
                or type(pool["spent"]) is not int or pool["spent"] != len(recorded)
                or any(row.get("error") in {"AGENT_AUTH_REQUIRED", "AGENT_QUOTA", "AUTH_REQUIRED", "RATE_LIMITED"}
                    for row in ledger["attempts"])):
            raise BackgroundFailure("JOB_DISABLED")
        previous = [row for row in recorded if row["variant"] == variant]
        if pool.get("retryAuthority") in {"native-repair-authorization.json", "native-four-successes-authorization.json"}:
            if not repair_retry_allowed(path, pool, recorded, variant, hashes):
                raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
        elif previous:
            authority = path.parent / "native-retry-authorization.json"
            try:
                grant = json.loads(authority.read_bytes())
                allowed = (pool.get("retryAuthority") == authority.name and grant["authorized"] is True
                    and pool.get("retryAuthoritySha256") == hashlib.sha256(authority.read_bytes()).hexdigest()
                    and grant["capTotal"] == pool["cap"] == 4 and grant["failedStartsCount"] is True
                    and variant == "NB-X03:v01" and len(previous) < grant["retryVariants"][variant] == 3
                    and all(row["status"] == "failed" for row in previous) and pool["cap"] - pool["spent"] >= 2)
            except (OSError, KeyError, TypeError, ValueError):
                allowed = False
            if not allowed:
                raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
        pool["spent"] += 1
        row = dict(id="NB07a-" + str(pool["spent"]), pool="NB07a", number=pool["spent"], variant=variant,
            jobId=job, projectId=project, model=MODEL, effort="medium", startedAt=now(), status="started",
            sourceHashes=hashes, failedStartsCount=True)
        ledger["attempts"].append(row)
        write(path, ledger)
        return row["id"]


class SerialProof:
    def __init__(self, root, dist, controlled):
        self.root, self.dist = root.resolve(), dist.resolve()
        if self.root.parent != Path("/private/tmp") or not self.root.name.startswith("foldcv-nb07a-native-") or self.root.exists():
            raise ValueError("A fresh owned NB07a native root is required")
        spec = json.loads((ROOT / "tests/requirements.json").read_bytes())["backgroundExecution"]
        self.hashes = source_hashes(spec["sources"])
        context = json.loads((controlled / "context.json").read_bytes())
        validation = json.loads((controlled / "validation.json").read_bytes())
        if context["sourceHashes"] != self.hashes or validation["outcome"] != "passed" or validation["runId"] != context["runId"]:
            raise ValueError("Current complete controlled fast evidence is required")
        if hashlib.sha256((controlled / "execution.json").read_bytes()).hexdigest() != validation["reportSha256"]:
            raise ValueError("Controlled execution evidence changed")
        ExperimentalCliProfile(PROFILE).check_binary(); check_host()
        if not (PROFILE / ".foldcv-cli-experiment-v1").is_file():
            raise ValueError("The existing isolated authenticated profile is required; never copy credentials")
        self.root.mkdir(mode=0o700)
        self.exclusion = Exclusion(self.root)
        self.sessions, self.attempts, self.tasks = {}, {}, set()
        self.phase = 0
        self.dist_hashes = {str(path.relative_to(self.dist)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.dist.rglob("*") if path.is_file()}
        if "index.html" not in self.dist_hashes:
            raise ValueError("A complete final frontend build is required")

    async def authorize(self, control):
        self.exclusion.check()
        _, artifact = self.service.artifacts.record(control.project_id, control.run_id)
        index = PROMPTS.index(artifact.request.message)
        job = control.job
        if (not job.submission.allow_edits or job.submission.allow_web or len(job.submission.models) != 1
                or job.submission.models[0].model != MODEL or self.hashes != source_hashes(self.hashes)):
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        variant = f"NB-X03:v{index + 1:02d}"
        self.attempts[job.id] = spend(LEDGER, variant=variant, job=job.id, project=control.project_id, hashes=self.hashes)
        write(self.root / "attempts.json", self.attempts)

    def audit(self, report):
        control = self.service.supervisor.active
        identifier = self.attempts.get(control.run_id)
        session = self.sessions.get(control.run_id)
        report.update(checkedAt=now(), jobId=control.run_id, attemptId=identifier,
            profileExclusionLost=self.exclusion.lost, profileExclusionChecks=self.exclusion.checks,
            ownedPidsGone=all(not alive(pid) for pid in [report["nativePid"], *report["hostPids"]] if pid is not None),
            mcpListenerClosed=session is not None and session.listener.fileno() < 0 and not session.active and session.token == "")
        write(self.root / (identifier + "-runtime.json" if identifier else "prestart-failure.json"), report)
        if identifier:
            with (LEDGER.parent / ".native-attempts.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                ledger = json.loads(LEDGER.read_bytes())
                row = next(row for row in ledger["attempts"] if row["id"] == identifier)
                row.update(status="native_completed_unvalidated" if report["state"] == "completed" else "failed",
                    error=report["error"], finishedAt=now(), runtimeEvidence=str(self.root / (identifier + "-runtime.json")))
                write(LEDGER, ledger)

    def session(self, control):
        session = self.original_session(control)
        self.sessions[control.run_id] = session
        call = session.call
        async def record(name, arguments):
            result = await call(name, arguments)
            path = self.root / (control.run_id + "-tools.jsonl")
            row = dict(at=now(), jobId=control.run_id, name=name,
                arguments=arguments.model_dump(mode="json", by_alias=True) if hasattr(arguments, "model_dump") else arguments,
                result=result)
            descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "a") as output:
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
            return result
        session.call = record
        return session

    async def submit(self):
        index = self.phase
        if index >= 2 or self.service.supervisor.active is not None:
            raise BackgroundFailure("BUSY")
        project = self.project
        if index == 1:
            first = self.service.store.read(project, self.jobs[0])
            if first.receipt is None or first.execution != "completed":
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            current, checksum = self.service.projects.storage.read_committed(project)
            await asyncio.to_thread(self.service.writers.open, project, WriterOpenV1(schemaVersion=1,
                sessionId="synthetic-native-deferred", incarnation="held-native-proof",
                credential=secrets.token_urlsafe(32), canonicalRevision=current.project_revision,
                canonicalSha256=checksum, actionCursor=0))
        state = self.service.project(project)
        current = self.service.projects.storage.read_committed(project)[0]
        request = JobAgentRequestV1(schemaVersion=1, lineage=state.lineage, requestEpoch=state.request_epoch,
            request=dict(clientRequestId="native-serial-" + str(index + 1), conversationId=self.conversation,
                message=PROMPTS[index], allowEdits=True, allowWeb=False, scope={"kind": "resume"},
                settingsRevision=2, projectRevision=current.project_revision, documentRevision=current.document_revision,
                factsRevision=current.project.facts.revision))
        job, created = await self.service.submit(project, request)
        assert created
        self.jobs.append(job.id); self.phase += 1
        write(self.root / "jobs.json", dict(project=project, jobs=self.jobs, phase=self.phase, at=now()))

    async def serve(self):
        data = self.root / "data"
        _, storage, workspace, conversation = isolated_project(data)
        block = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
        block.content = [StyledText(type="text", text=TEXT, styles={})]
        storage.save(workspace, {}, {})
        AgentSettingsStore(data).save(AgentSettingsRequest(expectedRevision=1, enabled=True, selectedAgentModel=MODEL), (MODEL,))
        self.project, self.conversation, self.jobs = workspace.project_id, conversation.id, []
        write(self.root / "baseline.json", workspace.model_dump(mode="json", by_alias=True))
        write(self.root / "source-context.json", dict(sourceHashes=self.hashes, protocol="apply_v2", model=MODEL,
            prompts=PROMPTS, root=str(self.root), nativePool="NB07a", dist=str(self.dist), distHashes=self.dist_hashes))
        self.exclusion.start()
        listener = socket.socket(); listener.bind(("127.0.0.1", 0)); listener.listen(128)
        origin = "http://127.0.0.1:" + str(listener.getsockname()[1]); secret = secrets.token_urlsafe(32)
        app = create_app(origin=origin, secret=secret, temp_root=self.root / "operations", dist=self.dist,
            cli_executable=BINARY, experimental_profile=ExperimentalCliProfile(PROFILE), data_root=data,
            background_enabled=True, background_native_authority=self.authorize)
        self.service = app.app.state.jobs
        self.service.runtime.audit = self.audit
        self.original_session = self.service.tools.session
        self.service.tools.session = self.session
        self.exclusion.on_lost = lambda: [control.stop() for control in self.service.supervisor.controls.values()]
        server = ProofServer(uvicorn.Config(app, host="127.0.0.1", port=listener.getsockname()[1], proxy_headers=False,
            access_log=False, server_header=False, log_level="warning"))
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGUSR1, setattr, server, "should_exit", True)
        def launch():
            async def dispatch():
                try:
                    await self.submit()
                except Exception as error:
                    write(self.root / "dispatch-error.json", dict(at=now(), type=type(error).__name__, reason=str(error)))
            task = asyncio.create_task(dispatch()); self.tasks.add(task); task.add_done_callback(self.tasks.discard)
        loop.add_signal_handler(signal.SIGUSR2, launch)
        write(self.root / "launch.json", dict(origin=origin, url=origin + "/#secret=" + secret, pid=os.getpid(), project=self.project))
        print(origin, flush=True)
        try:
            await server.serve(sockets=[listener])
        finally:
            await asyncio.gather(*self.tasks, return_exceptions=True)
            self.exclusion.stop(); listener.close()
            write(self.root / "shutdown.json", dict(at=now(), stopped=True, active=self.service.supervisor.active is not None,
                admissionHeld=self.service.admission.locked(), operationDirectories=[p.name for p in (self.root / "operations").glob("op-*")]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--controlled-evidence", type=Path, required=True)
    options = parser.parse_args()
    with open("/private/tmp/foldcv-nb-native-live.lock", "a") as lock, protocol_diagnostics(options.root):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(SerialProof(options.root, options.dist, options.controlled_evidence).serve())
