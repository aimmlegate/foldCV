"""Owned crash peer: real local persistence, no native factory or transport."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def forbidden(*_args, **_kwargs):
    raise AssertionError("native processes and external transport are forbidden")


subprocess.Popen = forbidden
socket.create_connection = socket.getaddrinfo = forbidden
socket.socket.connect = socket.socket.connect_ex = socket.socket.sendto = forbidden
print(json.dumps({"type": "ready", "protocol": "NB00a-pipe-v1"}), flush=True)
command = json.loads(sys.stdin.readline())
source = Path(command["sourceRoot"]).resolve()
data = Path(command["dataRoot"]).resolve()
if not data.is_relative_to(Path.cwd().parent.resolve()) or data == Path.cwd().parent.resolve():
    raise AssertionError("crash peer data must be in its owned test root")
site = source / ".venv/lib" / ("python" + str(sys.version_info.major) + "." + str(sys.version_info.minor)) / "site-packages"
sys.path[:0] = [str(source), str(source / "services/api/src"), str(site)]
from resume_api.agent.runtime import CodexAgentRuntime
from resume_api.connection import ConnectionAdapter
from resume_api.providers.codex_cli import CodexCliProvider
for cls in (CodexAgentRuntime, ConnectionAdapter, CodexCliProvider):
    cls.__init__ = forbidden
from resume_api.agent.context import query_fingerprint
from packages.resume_core.agent_artifacts import JobArtifacts
from packages.resume_core.background_history import ScopeHistory
from packages.resume_core.background_publication import CanonicalCoordinator
from packages.resume_core.background_clock import ControlledDeadlines
from packages.resume_core.background_store import JobStore
from packages.resume_core.rich_project_store import RichProjectStore

jobs = JobStore(data, clock=lambda: command["wallNow"])
artifacts = JobArtifacts(jobs)
history = ScopeHistory(jobs, query_fingerprint)


def observe(name, project):
    if name == command["phase"]:
        print(json.dumps({"type": "cut", "name": name, "project": project, "pid": os.getpid()}), flush=True)
        if sys.stdin.readline() != "continue\n":
            raise AssertionError("crash peer was not released")


canonical = RichProjectStore(data)
coordinator = CanonicalCoordinator(jobs, history, canonical, artifacts.payload_unlocked, observer=observe)
coordinator.authority.clock = ControlledDeadlines()
state = jobs.load(command["project"])
if command.get("barrierAck") is not None:
    if state.barrier.model_dump(mode="json", by_alias=True) != command["barrierAck"] or state.writer.status != "attached":
        raise AssertionError("fresh synthetic barrier acknowledgment mismatch")
    coordinator.authority.acknowledged(state.writer, state.barrier)
loaded, errors, _registry = canonical.load_all()
if errors:
    raise AssertionError("crash peer canonical input is invalid")
_workspace, originals, rendered, images = loaded[command["project"]]
coordinator.publish(command["project"], command["job"], command["proposalSha256"],
    originals=originals, artifacts=rendered, images=images)
print('{"type":"complete"}', flush=True)
