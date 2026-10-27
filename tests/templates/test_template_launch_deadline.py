"""Durable launch transitions cannot carry a stale inference deadline."""

import pytest

from packages.resume_core.template_import import CleanupProof, digest, spent_calls
from tests.templates.template_runtime_fixtures import RuntimeFixture


def never_dispatched(attempt):
    return CleanupProof(attempt.id, digest(attempt.owner), digest({'unlaunched': attempt.id}),
        'controlled-never-dispatched', True)


def observing(original, react):
    """Launch steps save to the sidecar (S7e); both save paths are observed."""
    def update(*args, **kwargs):
        workspace = original(*args, **kwargs)
        react((workspace.project or workspace.pre_draft).template_operations[0])
        return workspace
    return update


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['reserved', 'dispatch_started'])
@pytest.mark.parametrize('verified', [False, True])
async def test_elapsed_expiry_during_durable_launch_never_enters_transport(tmp_path, phase, verified):
    fixture = RuntimeFixture(tmp_path)
    elapsed, observed = [0.0], []
    pipeline = fixture.pipeline
    pipeline.elapsed = lambda: elapsed[0]
    def react(operation):
        if not observed and operation.attempts and operation.attempts[-1].state == phase:
            observed.append(phase)
            elapsed[0] = 301.0
    pipeline.update, pipeline.update_operation = observing(pipeline.update, react), observing(pipeline.update_operation, react)
    if verified:
        fixture.transport.reconcile = never_dispatched
    await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    current = fixture.current()
    result = (current.project or current.pre_draft).template_operations[0]
    assert observed == [phase] and fixture.transport.calls == []
    assert result.inference_closed and len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.error_code == 'IMPORT_PROCESSING_EXHAUSTED' and attempt.raw_return is None
    if verified:
        assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
        assert attempt.state == 'released' and attempt.cleanup.state == 'verified'
        assert spent_calls(result) == 0
    else:
        assert result.state == 'fenced' and current.project is None
        assert attempt.state == 'outcome_unknown' and attempt.cleanup.state == 'unknown'
        assert spent_calls(result) == 1
        fixture.transport.reconcile = never_dispatched
        recovered = await pipeline.recover(fixture.project, result.id)
        assert recovered.attempts[0].state == 'released' and spent_calls(recovered) == 0


@pytest.mark.asyncio
async def test_transport_timeout_is_refreshed_after_durable_dispatch(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    elapsed, timeouts = [0.0], []
    pipeline = fixture.pipeline
    pipeline.elapsed = lambda: elapsed[0]
    original_generate = fixture.transport.generate
    def react(operation):
        if operation.attempts and operation.attempts[-1].state == 'dispatch_started':
            elapsed[0] = 299.0
    def generate(request, cancel):
        timeouts.append(request.policy.timeout_seconds)
        return original_generate(request, cancel)
    pipeline.update, pipeline.update_operation = observing(pipeline.update, react), observing(pipeline.update_operation, react)
    fixture.transport.generate = generate
    await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert timeouts == [1.0, 1.0] and fixture.current().project is not None
