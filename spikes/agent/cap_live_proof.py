"""Bound the CAP live proof to the persisted, explicitly authorized assistant-turn ceiling.

One attempt is one assistant model turn (turn/start), charged before it starts whatever its outcome.
Apply, Undo/Redo and export make no model call. The FoldCV CLI profile is used in place; credentials
are never read or copied. Only the synthetic CAP rich fixture in a new /private/tmp root is served.
"""

import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
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

from packages.resume_core.agent_store import AgentFailure

MODEL = "gpt-6-luna"
PROFILE = Path.home() / "Library/Application Support/FoldCV/cli-experiment"
LEDGER = ROOT / "docs/gui/handoffs/ASSISTANT-CAPABILITIES/cap-live-ledger.json"
PREFIX = "/private/tmp/foldcv-cap-live-"
BUDGET_LOCK = "/private/tmp/foldcv-cap-live-budget.lock"
REQUEST = ("Перепиши всё резюме: сделай формулировки короче и яснее. Сохрани язык, факты, даты, ссылки, контакты, "
    "порядок разделов и оформление. Подготовь один полный вариант для просмотра.")
PHASES = ("rewrite_apply", "check_only")
# Plain, deliberately wordy synthetic prose next to the rich fixture content, so a rewrite has real work.
WORDY = {
    "bullet": ("В течение всего периода работы в компании я занимался тем, что разрабатывал и поддерживал внутренние "
        "сервисы, которые потом использовались другими командами для решения их ежедневных рабочих задач."),
    "nested": ("Кроме того, я на регулярной основе принимал активное участие в процессе проведения ревью кода, в ходе "
        "которого внимательно проверял изменения коллег и давал им подробную обратную связь."),
}
STOPS = {"AGENT_AUTH_REQUIRED", "AGENT_QUOTA"}


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".next")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, ensure_ascii=False, indent=1); output.write("\n"); output.flush(); os.fsync(output.fileno())
    os.replace(temporary, path)


def phase_of(context):
    return "rewrite_apply" if context["allowEdits"] else "check_only"


def admit(context, model):
    """Only the authorized request, model and web-off mode may reach the budget."""
    if model != MODEL or context.get("message") != REQUEST or context.get("allowWeb"):
        raise AgentFailure("AGENT_TOOL_DENIED")
    return phase_of(context), context.get("continuedDraft") is not None


def charge(ledger_path, phase, *, run_id, continuation, extra=None):
    with open(BUDGET_LOCK, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = json.loads(ledger_path.read_text())
        stop = next((row["error"] for row in ledger["attempts"] if row.get("error") in STOPS), None)
        if stop is not None:
            raise AgentFailure(stop)
        if ledger["spent"] >= ledger["cap"]:
            raise AgentFailure("AGENT_TOOL_LIMIT")
        passed = {row["phase"] for row in ledger["attempts"] if row.get("status") == "passed"}
        if phase not in ledger["phaseCap"] or phase in passed:
            raise AgentFailure("AGENT_TOOL_DENIED")
        # Each scenario has its own share, so one failing scenario cannot use the other's starts.
        if sum(row["phase"] == phase for row in ledger["attempts"]) >= ledger["phaseCap"][phase]:
            raise AgentFailure("AGENT_TOOL_LIMIT")
        number = ledger["spent"] + 1
        ledger["spent"] = number
        ledger["attempts"].append({"number": number, "phase": phase, "continuation": continuation, "status": "started",
            "runId": run_id, "model": MODEL, "startedAt": now(), **(extra or {})})
        write(ledger_path, ledger)
        return number


def settle(ledger_path, number, status, *, error=None, note=None, evidence=None):
    with open(BUDGET_LOCK, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = json.loads(ledger_path.read_text())
        row = ledger["attempts"][number - 1]
        row.update({key: value for key, value in {"status": status, "error": error, "note": note, "evidence": evidence,
            "settledAt": now()}.items() if value is not None or key in {"status", "settledAt"}})
        write(ledger_path, ledger)


def competitors(owned):
    rows = subprocess.check_output(["/bin/ps", "-axo", "pid=,command="], text=True, timeout=2)
    modules = {"resume_api.launcher", "spikes.agent.proof", "spikes.agent.gui_proof", "spikes.agent.native_proof"}
    scripts = {"gui_native_cycle.py", "foldcv-open-launch.py", "foldcv-gui-cycle-server.py", "ct05_live_import.py",
        "ct05_v7_serve.py", "cap_live_proof.py"}
    found = []
    for line in rows.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or int(parts[0]) == owned:
            continue
        try:
            args = shlex.split(parts[1])
        except ValueError:
            continue
        if not args or "python" not in Path(args[0]).name.lower():
            continue
        # A ledger --settle call is not a service; only a served root competes for the profile.
        if len(args) >= 2 and Path(args[1]).name == "cap_live_proof.py" and "--root" not in args:
            continue
        name = Path(args[1]).name if len(args) >= 2 else ""
        # Any CT live import or V7 serve tool uses the same FoldCV CLI profile.
        if ((len(args) >= 3 and args[1] == "-m" and args[2] in modules) or name in scripts
                or re.fullmatch(r"ct\d+_(live_import|v7_serve)\.py", name)):
            found.append(int(parts[0]))
    return found


class Exclusion:
    def __init__(self, root):
        self.root, self.stopped, self.lost, self.checks, self.foreign = root, threading.Event(), False, 0, []
        self.on_lost = lambda: None
        self.thread = threading.Thread(target=self.watch, daemon=True)

    def check(self):
        self.foreign = competitors(os.getpid()); self.checks += 1
        if self.foreign:
            self.lost = True
        if self.lost:
            raise AgentFailure("AGENT_BUSY")

    def watch(self):
        while not self.stopped.wait(.5):
            try:
                self.check()
            except Exception:
                self.lost = True; self.on_lost(); return

    def start(self):
        self.check(); self.thread.start()

    def stop(self):
        self.stopped.set(); self.thread.join(3)
        write(self.root / "exclusion.json", {"checkedAt": now(), "checks": self.checks, "lost": self.lost,
            "competingServicePids": self.foreign})


async def seed(root):
    from packages.resume_core.agent_settings import AgentSettingsStore
    from packages.resume_core.assistant_proposals import content_digest
    from packages.resume_core.models.agent import AgentSettingsRequest
    from tests.support.assistant_fidelity import environment
    from packages.resume_core.models.rich_document import StyledText
    service, _, projects, workspace, session = environment(root / "seed")
    await session.close()
    service.store.finish(workspace.project_id, session.run.id, "interrupted", error="AGENT_INTERRUPTED",
        text="Синтетический стенд подготовлен без вызова модели.")
    current = projects.workspaces[workspace.project_id]
    for block in current.project.document.blocks():
        if block.id in WORDY:
            block.content = [StyledText(type="text", text=WORDY[block.id], styles={})]
    assert projects.persist(workspace.project_id) == "durable"
    workspace = projects.read(workspace.project_id)
    data = projects.storage.root
    settings = AgentSettingsStore(data)
    current = settings.load()
    settings.save(AgentSettingsRequest(expectedRevision=current.revision, enabled=True, selectedAgentModel=MODEL), (MODEL,))
    write(root / "task-spec.json", {"createdAt": now(), "model": MODEL, "request": REQUEST, "projectId": workspace.project_id,
        "fixture": "tests/support/assistant_fidelity.py environment: Cyrillic/emoji, link, table, image caption, user-corrected fact, extraction gap",
        "wordyBlocks": WORDY,
        "baselineContentSha256": content_digest(workspace), "dataRoot": str(data), "allowWeb": False,
        "scenarios": {"rewrite_apply": "edits on: review, delayed Apply, native Undo/Redo, DOCX export and reopen",
            "check_only": "edits off: useful proposal, Apply denied; enabling edits does not apply"}})
    return data, workspace.project_id


class Diagnostics:
    """Tool names, codes and assembly counts only; no document text."""

    @staticmethod
    def row(session, name, arguments, result):
        row = {"runId": session.run.id, "name": name, "allowEdits": session.run.allow_edits,
            "code": ((result or {}).get("error") or {}).get("code") if isinstance(result, dict) else None}
        if name == "prepare_edit_batch" and isinstance(result, dict):
            row.update({key: result.get(key) for key in ("disposition", "proposalId", "version", "unresolvedUnits") if key in result})
            row.update({"taskId": getattr(arguments, "task_id", None), "requestPhase": getattr(arguments, "phase", None),
                "operations": len(getattr(arguments, "operations", None) or []),
                "unchanged": len(getattr(arguments, "unchanged", None) or [])})
        return row

    @staticmethod
    def rejected(session, params, code):
        arguments = params.get("arguments") if isinstance(params, dict) else None
        request = arguments.get("request") if isinstance(arguments, dict) else None
        return {"runId": session.run.id, "name": params.get("name") if isinstance(params, dict) else None, "preflight": code,
            "issues": session.argument_issues, "argumentKeys": sorted(arguments) if isinstance(arguments, dict) else None,
            "requestKeys": sorted(request) if isinstance(request, dict) else None}


def build(root, data, project_id, exclusion):
    import uvicorn
    from resume_api.agent.runtime import CodexAgentRuntime
    from resume_api.agent.tools import AgentTools, ToolSession
    from resume_api.app import create_app
    from resume_api.cli.experimental_profile import BINARY, ExperimentalCliProfile
    from resume_api.providers.codex_cli import CodexCliProvider
    from resume_api.providers.content import ContentFailure

    class EvidenceSession(ToolSession):
        def record(self, row):
            try:
                descriptor = os.open(root / "tool-diagnostics.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, "a") as output:
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
            except Exception:
                pass

        def preflight(self, params):
            code = super().preflight(params)
            if code:
                self.record(Diagnostics.rejected(self, params, code))
            return code

        async def call(self, name, arguments):
            result = await super().call(name, arguments)
            try:
                self.record(Diagnostics.row(self, name, arguments, result))
            except Exception:
                pass
            return result

    class EvidenceTools(AgentTools):
        async def open(self, control, run, journal):
            session = EvidenceSession(self.service, control, run, self.fetcher)
            session.prompt = session.book.initial(run, journal); await session.start()
            return session

    class BoundedRuntime:
        native = True

        def __init__(self, connection):
            self.runtime = CodexAgentRuntime(connection, root / "operations", audit=self.audit)
            self.attempt = self.phase = self.run_id = None

        async def run(self, value, cancel, emit):
            context = json.loads(value.prompt.partition("\n")[2])
            phase, continuation = admit(context, value.model)
            self.attempt, self.phase = None, phase
            self.run_id = (((context.get("outline") or {}).get("snapshot") or {}).get("runId"))

            def start():
                value.before_start()
                exclusion.check()
                self.attempt = charge(LEDGER, phase, run_id=self.run_id, continuation=continuation,
                    extra={"root": str(root), "effort": getattr(value, "reasoning_effort", None)})

            def guarded(kind, payload):
                if exclusion.lost:
                    cancel.set()
                emit(kind, payload)
            return await self.runtime.run(replace(value, before_start=start), cancel, guarded)

        def audit(self, report):
            report.update({"attempt": self.attempt, "phase": self.phase, "runId": self.run_id, "checkedAt": now(),
                "exclusionLost": exclusion.lost})
            name = f"attempt-{self.attempt}-runtime.json" if self.attempt else "prestart-failure.json"
            write(root / name, report)
            if self.attempt:
                settle(LEDGER, self.attempt, "native_completed_unvalidated" if report.get("state") == "completed" else "failed",
                    error=report.get("error"), evidence=str(root / name))

    def deny_structured(*_args, **_kwargs):
        raise ContentFailure("MODEL_DENIED")
    CodexCliProvider._generate = deny_structured
    listener = socket.socket(); listener.bind(("127.0.0.1", 0)); listener.listen(128)
    origin = "http://127.0.0.1:" + str(listener.getsockname()[1]); secret = secrets.token_urlsafe(32)
    app = create_app(origin=origin, secret=secret, temp_root=root / "operations", dist=ROOT / "apps/web/dist",
        cli_executable=BINARY, experimental_profile=ExperimentalCliProfile(PROFILE), data_root=data)
    service = app.app.state.agent
    service.assistant_protocol_enabled = True
    service.runtime = BoundedRuntime(service.runtime.connection)
    service.tools = EvidenceTools(service)
    exclusion.on_lost = lambda: service.request_stop(reason="AGENT_INTERRUPTED")
    write(root / "launch.json", {"origin": origin, "url": origin + f"/?project={project_id}#secret=" + secret, "pid": os.getpid()})
    print(json.dumps({"origin": origin, "root": str(root), "pid": os.getpid()}), flush=True)

    class Server(uvicorn.Server):
        @contextmanager
        def capture_signals(self):
            prior = {number: signal.signal(number, self.handle_exit) for number in (signal.SIGINT, signal.SIGTERM)}
            try:
                yield
            finally:
                for number, handler in prior.items():
                    signal.signal(number, handler)

    return Server(uvicorn.Config(app, host="127.0.0.1", port=listener.getsockname()[1], proxy_headers=False,
        access_log=False, server_header=False, log_level="critical", timeout_graceful_shutdown=2)), listener


def profile_audit(root):
    """Record only file counts and names; credential files are skipped without reading."""
    skipped, sockets, count = [], [], 0
    for path in PROFILE.rglob("*"):
        mode = path.lstat().st_mode
        relative = str(path.relative_to(PROFILE))
        if stat.S_ISSOCK(mode):
            sockets.append(relative); continue
        if not stat.S_ISREG(mode):
            continue
        if path.name == "auth.json" or any(word in path.name.lower() for word in ("credential", "token", "secret", "private_key")):
            skipped.append(relative); continue
        count += 1
    write(root / "profile-audit.json", {"checkedAt": now(), "nonCredentialFiles": count, "skippedCredentialFiles": skipped,
        "sockets": sockets, "credentialsReadOrCopied": False})


async def serve(root):
    root.mkdir(mode=0o700)
    data, project_id = await seed(root)
    exclusion = Exclusion(root); exclusion.start()
    server, listener = build(root, data, project_id, exclusion)
    try:
        await server.serve(sockets=[listener])
    finally:
        exclusion.stop(); profile_audit(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--settle", type=int)
    parser.add_argument("--status", choices=("passed", "failed"))
    parser.add_argument("--note")
    options = parser.parse_args()
    if options.settle:
        settle(LEDGER, options.settle, options.status, note=options.note)
        return
    root = options.root.absolute()
    if not str(root).startswith(PREFIX) or root.exists():
        raise SystemExit("A new " + PREFIX + "* root is required")
    with open("/private/tmp/foldcv-cap-live.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(serve(root))


if __name__ == "__main__":
    main()
