"""Isolated synthetic assistant inputs and scripted peers; no native model work."""

import asyncio
import json
from pathlib import Path
import shutil

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from packages.resume_core.agent_store import AgentStore
from packages.resume_core.models.agent import AgentRunRequest
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.rich_project_store import RichProjectStore

NOW = "2026-10-15T12:00:00+00:00"
OWNER_TOKEN = "synthetic_owner_capability_0123456789"


def isolated_project(root):
    workspace = WorkspaceV6.model_validate(json.loads(Path("tests/fixtures/rich_workspace.json").read_text()))
    from packages.resume_core.rendering.rich_template import require_rich_template
    workspace.project.template = require_rich_template().manifest
    workspace.project.sources = []
    workspace.project.assets = []
    workspace.project.document.regions[2].blocks = [block for block in workspace.project.document.regions[2].blocks if block.type != "image"]
    canonical = RichProjectStore(root)
    canonical.save(workspace, {}, {})
    store = AgentStore(root, clock=lambda: NOW)
    conversation = store.create_conversation(workspace.project_id)
    return store, canonical, workspace, conversation


def run_request(conversation_id, **changes):
    return AgentRunRequest.model_validate({"clientRequestId": "send_1", "conversationId": conversation_id,
        "owner": {"token": OWNER_TOKEN, "epoch": 1}, "message": "Check the Python evidence.",
        "allowEdits": True, "allowWeb": True, "scope": {"kind": "resume"}, "settingsRevision": 1,
        "projectRevision": 1, "documentRevision": 1, "factsRevision": 1, **changes})


def fake_agent_cli(root, steps, *, fragment_bytes=None):
    root.mkdir(parents=True)
    source = Path("tests/cli_spike")
    for name in ("fake_cli.py", "fake_agent.py"):
        shutil.copyfile(source / name, root / name)
    executable = root / "fake_cli.py"
    executable.chmod(0o700)
    config = {"agent": steps}
    if fragment_bytes is not None:
        config["fragmentBytes"] = fragment_bytes
    (root / "fixture.json").write_text(json.dumps(config))
    return executable


class ScriptedMcp:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.sdk = FastMCP("foldcv-scripted", stateless_http=True, json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

        @self.sdk.tool()
        async def get_resume_context() -> dict:
            """Read the next synthetic context result."""
            self.calls.append("get_resume_context")
            self.started.set()
            value = self.replies.pop(0)
            if value == "wait":
                await self.release.wait()
                return {"text": "Released synthetic context"}
            if isinstance(value, Exception):
                raise value
            return value

        self.application = self.sdk.streamable_http_app()
