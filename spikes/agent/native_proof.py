"""Bound AG08 GUI tasks to the persisted, explicitly authorized start ceiling."""

import argparse
import asyncio
from dataclasses import replace
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import signal
import socket
import stat
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

import uvicorn
from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.models.agent import AgentSettingsRequest
from packages.resume_core.models.rich_document import StyledText
from packages.resume_core.rich_project_store import rich_snapshot_bytes
from resume_api.agent.runtime import CodexAgentRuntime
from resume_api.agent.tools import AgentTools, ToolSession
from packages.resume_core.models.agent import AgentQuery
from resume_api.app import create_app
from resume_api.cli.experimental_profile import BINARY, ExperimentalCliProfile
from spikes.agent.proof import STATE
from tests.support.agent import isolated_project

MODEL = "gpt-6-luna"
PROFILE = Path.home() / "Library/Application Support/FoldCV/cli-experiment"
NAME = "Alex ProofEvergreen"
VACANCY = "https://www.python.org/jobs/8134/"
TEXT = "Built REST APIs in Python. Wrote unit tests with pytest."
RESEARCH = ("Сравни резюме с вакансией https://www.python.org/jobs/8134/. Обязательно найди эту вакансию живым поиском и открой её страницу. "
    "Прочитай текущий текст резюме и сохрани привязанные замечания о совпадениях и пробелах. Затем измени только абзац «Built REST APIs in Python. Wrote unit tests with pytest.»: "
    "объедини его в одну ясную английскую фразу с акцентом на уже указанные Python, REST API и unit tests with pytest. Сохрани смысл, стиль и все остальные блоки; "
    "не добавляй стаж, PostgreSQL, Polars, Linux, AWS, метрики или другой неподтверждённый опыт. Подготовь и примени один пакет правок, дождись сохранения, "
    "перечитай изменённый абзац и проверь результат. В ответе укажи ID сохранённого источника и кратко назови неподтверждённые требования. Выполни правку, не ограничивайся советом.")
CHECK = ("Теперь только проверь отредактированное резюме по уже сохранённой вакансии, без интернета. Прочитай текущий абзац и сохранённый источник из диалога, "
    "сохрани привязанные замечания и проверь резюме. Для проверки режима один раз вызови prepare_edit_batch с корректной заменой одного слова: "
    "сервер обязан отказать, потому что включена «Только проверка». Не применяй и не повторяй правку. Все тексты и факты должны остаться прежними. "
    "Ответь кратко по-русски и процитируй ID уже сохранённого источника.")


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".next")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, ensure_ascii=False, indent=2); output.write("\n"); output.flush(); os.fsync(output.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def alive(pid):
    try: os.kill(pid, 0); return True
    except ProcessLookupError: return False


def source_manifest(number):
    paths = [*ROOT.glob("packages/resume_core/**/*.py"), *ROOT.glob("services/api/src/resume_api/**/*.py"),
        *ROOT.glob("spikes/agent/*.py"), *ROOT.glob("apps/web/src/**/*.ts"), *ROOT.glob("apps/web/src/**/*.tsx"),
        *ROOT.glob("apps/web/src/**/*.css"), *ROOT.glob("contracts/json-schema/*.json"), *ROOT.glob("apps/web/dist/**/*")]
    paths += [ROOT / "requirements-service.txt", ROOT / "apps/web/package.json", ROOT / "apps/web/package-lock.json"]
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(set(paths)) if path.is_file()}
    path = ROOT / f"docs/gui/handoffs/AGENT-ASSISTANT/evidence/ag08-native-{number}-source-manifest.json"
    write(path, {"schemaVersion": 1, "checkedAt": now(), "baseRevision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "sourceSha256": hashes})
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def competitors(owned):
    rows = subprocess.check_output(["/bin/ps", "-axo", "pid=,command="], text=True, timeout=2)
    found = []
    for line in rows.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or int(parts[0]) == owned: continue
        try: args = shlex.split(parts[1])
        except ValueError: continue
        if not args or "python" not in Path(args[0]).name.lower(): continue
        modules = {"resume_api.launcher", "spikes.agent.proof", "spikes.agent.gui_proof", "spikes.agent.native_proof"}
        scripts = {"gui_native_cycle.py", "foldcv-open-launch.py", "foldcv-gui-cycle-server.py"}
        if (len(args) >= 3 and args[1] == "-m" and args[2] in modules
                or len(args) >= 2 and Path(args[1]).name in scripts): found.append(int(parts[0]))
    return found


class Exclusion:
    def __init__(self, root):
        self.root, self.stopped, self.lost, self.checks = root, threading.Event(), False, 0
        self.foreign = []
        self.on_lost = lambda: None
        self.thread = threading.Thread(target=self.watch)

    def check(self):
        self.foreign = competitors(os.getpid()); self.checks += 1
        if self.foreign: self.lost = True
        if self.lost: raise AgentFailure("AGENT_BUSY")

    def watch(self):
        while not self.stopped.wait(.2):
            try: self.check()
            except Exception:
                self.lost = True; self.on_lost(); return

    def start(self):
        self.check(); self.thread.start()

    def stop(self):
        self.stopped.set(); self.thread.join(3)
        write(self.root / "exclusion.json", {"checkedAt": now(), "checks": self.checks,
            "lost": self.lost, "competingServicePids": self.foreign, "scope": "entire owned live service; runtime also holds the native profile flock per turn"})


def seed(root):
    data = root / "data"
    if (data / "projects").exists(): return
    _, canonical, workspace, _ = isolated_project(data)
    def rename(value):
        if isinstance(value, str): return value.replace("Alex Example", NAME)
        if isinstance(value, list): return [rename(item) for item in value]
        if isinstance(value, dict): return {key: rename(item) for key, item in value.items()}
        return value
    workspace = type(workspace).model_validate(rename(workspace.model_dump(by_alias=True)))
    block = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
    block.content = [StyledText(type="text", text=TEXT, styles={"bold": True})]
    canonical.save(workspace, {}, {})
    settings = AgentSettingsStore(data)
    settings.save(AgentSettingsRequest(expectedRevision=1, enabled=True, selectedAgentModel=MODEL), (MODEL,))
    write(root / "baseline.json", workspace.model_dump(mode="json", by_alias=True))
    budget = json.loads(STATE.read_text())["nativeBudgets"]["AG08"]
    write(root / "task-spec.json", {"createdAt": now(), "vacancy": VACANCY, "candidate": NAME,
        "model": MODEL, "effort": "medium", "baselineSha256": hashlib.sha256(rich_snapshot_bytes(workspace)).hexdigest(),
        "editableBlock": "narrative", "beforeText": TEXT, "factsMustStayUnchanged": True,
        "allowedClaims": ["Python", "REST APIs", "unit tests", "pytest"],
        "unsupportedClaimsMustRemainFindings": ["seven years experience", "PostgreSQL", "Polars", "Linux", "AWS", "metrics"],
        "researchPrompt": RESEARCH, "checkPrompt": CHECK, "nativeBudgetAtSelection": {"spent": budget["spent"], "cap": budget["cap"]}})


class EvidenceTools(AgentTools):
    def __init__(self, service):
        super().__init__(service); self.sessions = {}

    async def open(self, control, run, journal):
        session = EvidenceSession(self.service, control, run, self.fetcher)
        session.prompt = session.book.initial(run, journal); await session.start(); self.sessions[run.id] = session
        return session


class EvidenceSession(ToolSession):
    def record(self, row):
        path = self.service.runtime.root / "tool-diagnostics.jsonl"
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a") as output: output.write(json.dumps({"runId": self.run.id, **row}) + "\n")

    def preflight(self, params):
        result = super().preflight(params)
        if result and self.argument_issues: self.record({"phase": "shape_rejected", "issues": self.argument_issues, "code": result})
        return result

    async def call(self, name, arguments):
        result = await super().call(name, arguments)
        try:
            row = {"phase": "validated_call", "name": name, "allowEdits": self.run.allow_edits,
                "allowWeb": self.run.allow_web, "code": (result.get("error") or {}).get("code")}
            if name == "get_conversation_context" and isinstance(arguments, AgentQuery): row["storedIds"] = arguments.ids
            if name == "prepare_edit_batch":
                row["operations"] = [{"kind": operation.kind, **({"target": operation.target.model_dump(by_alias=True)} if operation.kind == "replace_text" else {})}
                    for operation in arguments.operations]
            self.record(row)
        except Exception:
            self.diagnostic_errors = getattr(self, "diagnostic_errors", 0) + 1
        return result


class ProofServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        prior = {number: signal.signal(number, self.handle_exit) for number in (signal.SIGINT, signal.SIGTERM)}
        try: yield
        finally:
            for number, handler in prior.items(): signal.signal(number, handler)


class BoundedRuntime:
    native = True
    def __init__(self, connection, root, exclusion, *, enabled):
        self.root, self.exclusion, self.enabled = root, exclusion, enabled
        self.runtime = CodexAgentRuntime(connection, root / "operations", audit=self.audit)
        self.attempt, self.phase, self.run_id, self.tools = None, None, None, None

    def spend(self, phase, run_id):
        self.exclusion.check()
        with open("/private/tmp/foldcv-ag08-budget.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(STATE.read_text()); budget = state["nativeBudgets"]["AG08"]
            error = next((row["error"] for row in budget["attempts"] if row.get("error") in {"AGENT_AUTH_REQUIRED", "AGENT_QUOTA"}), None)
            if error is not None: raise AgentFailure(error)
            if budget["spent"] >= budget["cap"]: raise AgentFailure("AGENT_TOOL_LIMIT")
            passed = {row["phase"] for row in budget["attempts"] if row.get("status") == "passed"}
            required = {"research_edit", "check_only"} - passed
            if phase not in required: raise AgentFailure("AGENT_TOOL_DENIED")
            if budget["cap"] - budget["spent"] < len(required): raise AgentFailure("AGENT_TOOL_LIMIT")
            number = budget["spent"] + 1; budget["spent"] = number
            budget["attempts"].append({"number": number, "phase": phase, "status": "started", "runId": run_id,
                "model": MODEL, "effort": "medium", "startedAt": now(), "taskSpecSha256": hashlib.sha256((self.root / "task-spec.json").read_bytes()).hexdigest(),
                "sourceManifest": source_manifest(number)})
            write(STATE, state)
            return number

    async def run(self, value, cancel, emit):
        context = json.loads(value.prompt.partition("\n")[2])
        phase = "research_edit" if context["allowEdits"] else "check_only"
        if (not self.enabled or value.model != MODEL or context["message"] != (RESEARCH if phase == "research_edit" else CHECK)
                or context["allowWeb"] != (phase == "research_edit")):
            raise AgentFailure("AGENT_TOOL_DENIED")
        self.attempt, self.phase = None, phase
        self.run_id = context["outline"]["snapshot"]["runId"]
        def start():
            value.before_start(); self.attempt = self.spend(phase, self.run_id)
        def guarded_emit(kind, payload):
            if self.exclusion.lost: cancel.set()
            emit(kind, payload)
        return await self.runtime.run(replace(value, before_start=start), cancel, guarded_emit)

    def audit(self, report):
        report.update({"attempt": self.attempt, "phase": self.phase, "runId": self.run_id,
            "checkedAt": now(), "profileExclusionLost": self.exclusion.lost, "profileExclusionChecks": self.exclusion.checks})
        report["ownedPidsGone"] = all(not alive(pid) for pid in [report["nativePid"], *report["hostPids"]] if pid is not None)
        session = self.tools.sessions.get(self.run_id) if self.tools else None
        report["mcpListenerClosed"] = session is not None and session.listener.fileno() < 0 and not session.active and session.token == ""
        report["diagnosticErrors"] = getattr(session, "diagnostic_errors", 0)
        report["operationDirectories"] = [path.name for path in (self.root / "operations").glob("op-*")]
        write(self.root / (f"attempt-{self.attempt}-runtime.json" if self.attempt else "prestart-failure.json"), report)
        if self.attempt:
            state = json.loads(STATE.read_text()); row = state["nativeBudgets"]["AG08"]["attempts"][self.attempt - 1]
            row.update(status="native_completed_unvalidated" if report["state"] == "completed" else "failed",
                error=report["error"], finishedAt=now(), evidence=str(self.root / f"attempt-{self.attempt}-runtime.json"))
            write(STATE, state)


def profile_audit(root):
    identifiers = []
    for path in [*root.glob("attempt-*-runtime.json"), *root.glob("prestart-failure.json")]:
        record = json.loads(path.read_text()); identifiers += [value for key in ("threadId", "turnId") if (value := record.get(key))]
    needles = [NAME.encode(), *[value.encode() for value in identifiers]]
    matches, skipped, sockets, count = [], [], [], 0
    for path in PROFILE.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISSOCK(mode): sockets.append(str(path.relative_to(PROFILE))); continue
        if not stat.S_ISREG(mode): continue
        relative = str(path.relative_to(PROFILE))
        if path.name == "auth.json" or any(word in path.name.lower() for word in ("credential", "token", "secret", "private_key")):
            skipped.append(relative); continue
        count += 1; tail = b""
        with path.open("rb") as source:
            while raw := source.read(65536):
                chunk = tail + raw
                if any(needle in chunk for needle in needles): matches.append(relative); break
                tail = chunk[-256:]
    result = {"checkedAt": now(), "scannedNonCredentialFiles": count, "skippedCredentialFiles": skipped,
        "matches": matches, "sockets": sockets, "credentialsReadOrCopied": False}
    write(root / "profile-audit.json", result)
    return result


async def serve(root, read_only):
    root = root.resolve()
    if not str(root).startswith("/private/tmp/foldcv-agent-ag08-"): raise ValueError("Dedicated AG08 root required")
    root.mkdir(parents=True, exist_ok=True); root.chmod(0o700); seed(root)
    exclusion = Exclusion(root); exclusion.start()
    listener = socket.socket(); listener.bind(("127.0.0.1", 0)); listener.listen(128)
    origin = "http://127.0.0.1:" + str(listener.getsockname()[1]); secret = secrets.token_urlsafe(32)
    profile = ExperimentalCliProfile(PROFILE)
    from resume_api.providers.codex_cli import CodexCliProvider
    from resume_api.providers.content import ContentFailure
    def deny_structured(*args, **kwargs):
        raise ContentFailure("MODEL_DENIED")
    CodexCliProvider._generate = deny_structured
    app = create_app(origin=origin, secret=secret, temp_root=root / "operations", dist=ROOT / "apps/web/dist",
        cli_executable=BINARY, experimental_profile=profile, data_root=root / "data")
    service = app.app.state.agent
    runtime = BoundedRuntime(service.runtime.connection, root, exclusion, enabled=not read_only)
    tools = EvidenceTools(service); service.runtime, service.tools, runtime.tools = runtime, tools, tools
    exclusion.on_lost = lambda: service.request_stop(reason="AGENT_INTERRUPTED")
    write(root / "launch.json", {"origin": origin, "url": origin + "/?project=project-1#secret=" + secret, "pid": os.getpid(), "readOnly": read_only})
    print(origin, flush=True)
    try:
        await ProofServer(uvicorn.Config(app, host="127.0.0.1", port=listener.getsockname()[1], proxy_headers=False,
            access_log=False, server_header=False, log_level="critical", timeout_graceful_shutdown=2)).serve(sockets=[listener])
    finally:
        exclusion.stop(); profile_audit(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--read-only", action="store_true"); parser.add_argument("--seed-only", action="store_true")
    options = parser.parse_args()
    if options.seed_only:
        if not str(options.root.resolve()).startswith("/private/tmp/foldcv-agent-ag08-"): raise ValueError("Dedicated AG08 root required")
        options.root.mkdir(parents=True, exist_ok=True); seed(options.root)
    else:
        with open("/private/tmp/foldcv-ag08-live.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            asyncio.run(serve(options.root, options.read_only))
