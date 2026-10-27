"""An import call waits for the shared inference permit instead of failing its block (SR00 flag 2, permit lifecycle)."""

import asyncio
from pathlib import Path

import pytest

from resume_api.importer.template_transport import ProviderTemplateTransport
from resume_api.inference_admission import INFERENCE
from resume_api.projects.imports import ImportCommand, ImportService
from resume_api.projects.service import ProjectService
from resume_api.providers.codex_cli import CodexCliProvider
from tests.templates.template_runtime_fixtures import RuntimeFixture


@pytest.mark.asyncio
async def test_an_import_call_waits_while_another_turn_holds_the_inference_permit(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    controlled = fixture.transport
    provider = CodexCliProvider(Path('/nonexistent/synthetic-cli'))
    provider._generate = lambda request, _files, cancel: controlled.generate(request, cancel)
    fixture.pipeline.transport = ProviderTemplateTransport(lambda: (provider, fixture.command.capture.primary.model),
        tmp_path / 'transport')
    projects = ProjectService(fixture.repository)
    imports = ImportService(projects, fixture.pipeline, commands=lambda *_args: fixture.command)
    # An assistant turn holds the permit when the import starts.
    assert INFERENCE.acquire(blocking=False)
    try:
        identifier = await imports.start(fixture.project, ImportCommand(kind='start', clientRequestId='request'),
            asyncio.Event())
        runner = imports.runners[identifier]
        for _ in range(200):
            if runner.done() or INFERENCE.waiting:
                break
            await asyncio.sleep(0.01)
    finally:
        INFERENCE.release()
    await runner
    [status] = projects.tasks.list(fixture.project)
    operation = fixture.current().project.template_operations[0]
    assert status['state'] == 'succeeded'
    assert [attempt.error_code for attempt in operation.attempts] == [None, None]
    assert operation.tasks[0].state == 'accepted' and len(controlled.calls) == 2
