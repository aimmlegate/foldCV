"""The bundled two-column import through the Claude provider and the CLI stand-in, offline (MP05 gate and schema list).

The product transport drives `ClaudeCliProvider` under the import's permit, as the import task does; only the CLI is
the stand-in, which answers each task with the scripted two-column reply left under its prompt's hash.
"""

import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path
import sys

from packages.resume_core.project_limits import finalization_seconds, import_seconds
from packages.resume_core.templates.operations import derive_task
from resume_api.importer.template_transport import JOB_PERMIT, ProviderTemplateTransport
from resume_api.inference_admission import INFERENCE
from resume_api.providers.claude_cli import ClaudeCliProvider, FixtureTransport
from tests.templates.evidence_references import by_reference
from tests.templates.generic_fixtures import REVIEWS, TABLES, generic_package, generic_script, source_fixture
from tests.templates.template_runtime_fixtures import EmploymentFixture

STAND_IN = Path(__file__).resolve().parent / "fake_claude.py"
MODEL, EFFORT = "claude-sonnet-5-5", "high"


class RelayTransport(ProviderTemplateTransport):
    """The product transport over the Claude provider; the fixture's captured model is served as Sonnet."""

    def __init__(self, provider, temp_root, script, answers):
        super().__init__(lambda: (provider, MODEL), temp_root)
        self.script, self.answers = script, answers

    def generate(self, request, cancel):
        value = request.request_value if request.request_value is not None else json.loads(request.text)
        reply = json.dumps({"payload": by_reference(self.script(request, value), value)})
        (self.answers / (hashlib.sha256(request.text.encode()).hexdigest() + ".json")).write_text(reply)
        policy = dataclasses.replace(request.policy, model=MODEL, reasoning_effort=EFFORT)
        return super().generate(dataclasses.replace(request, policy=policy), cancel)


def stand_in(directory: Path) -> Path:
    (directory / "answers").mkdir(parents=True)
    cli = directory / "claude"
    cli.write_text("#!" + sys.executable + "\n" + STAND_IN.read_text().split("\n", 1)[1])
    cli.chmod(0o700)
    (directory / "fixture.json").write_text(json.dumps({"case": "relay", "value": {}}))
    return cli


def audit(directory: Path) -> list[list[str]]:
    return [json.loads(line)["args"] for line in (directory / "audit.jsonl").read_text().splitlines()]


async def relay_import(root: Path, name: str = "F10"):
    """One published two-column import of a synthetic fixture, three blocks at once; returns (fixture, result, stand-in)."""
    directory, operations = root / "claude stand-in", root / "operations"
    cli = stand_in(directory)
    operations.mkdir(mode=0o700)
    src, raw = source_fixture(name)
    fixture = EmploymentFixture(root / "import", captured=generic_package(), src=src, original_bytes=raw, cap=60,
                                fallback=False, concurrency=3)
    fixture.command.capture.allow_text_rewrite = True
    fixture.command.capture.policy.processing_seconds = import_seconds()
    fixture.command.capture.policy.finalization_seconds = finalization_seconds()
    fixture.transport = RelayTransport(ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli)), operations,
                                       generic_script(src, TABLES[name](True), REVIEWS.get(name)), directory / "answers")
    fixture.pipeline = fixture.fresh_pipeline()
    fixture.pipeline.derive = derive_task
    permit = await INFERENCE.reserve(asyncio.Event())
    token = JOB_PERMIT.set(permit)
    try:
        result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    finally:
        JOB_PERMIT.reset(token)
        permit.release()
    return fixture, result, directory
