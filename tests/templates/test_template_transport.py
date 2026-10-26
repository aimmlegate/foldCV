"""The provider transport runs under the job's inference permit and proves cleanup only from real evidence."""

import threading
from types import SimpleNamespace

import pytest

from resume_api.importer.template_transport import JOB_PERMIT, ProviderTemplateTransport
from resume_api.providers.content import ContentFailure


class Provider:
    def __init__(self, owned_result=None):
        self.calls, self.owned_result = [], owned_result

    def generate(self, _request, _files, _cancel):
        self.calls.append('generate')
        raise ContentFailure('BUSY')

    def generate_owned(self, _request, _files, _cancel, permit):
        self.calls.append(('owned', permit))
        return self.owned_result


def request(model='model-a'):
    return SimpleNamespace(policy=SimpleNamespace(model=model))


def test_a_job_permit_routes_to_owned_generation(tmp_path):
    provider = Provider(owned_result='result')
    transport = ProviderTemplateTransport(lambda: (provider, 'model-a'), tmp_path)
    token = JOB_PERMIT.set('permit-1')
    try:
        assert transport.generate(request(), threading.Event()) == 'result'
    finally:
        JOB_PERMIT.reset(token)
    assert provider.calls == [('owned', 'permit-1')]


def test_admission_refusal_before_launch_is_proved_undispatched(tmp_path):
    provider = Provider()
    transport = ProviderTemplateTransport(lambda: (provider, 'model-a'), tmp_path)
    with pytest.raises(ContentFailure) as refused:
        transport.generate(request(), threading.Event())
    assert refused.value.code == 'BUSY' and refused.value.cleanup_verified is True
    assert refused.value.dispatch_witness == {'neverDispatched': True}
    frame = SimpleNamespace(cleanup_verified=True, dispatch_witness=refused.value.dispatch_witness)
    proof = transport.prove_return(SimpleNamespace(id='attempt-1', owner={'leaseId': 'lease'}), frame)
    assert proof.never_dispatched is True


def test_model_mismatch_and_unexpected_errors_are_content_failures(tmp_path):
    provider = Provider()
    with pytest.raises(ContentFailure, match='MODEL_DENIED'):
        ProviderTemplateTransport(lambda: (provider, 'model-b'), tmp_path).generate(request(), threading.Event())
    class Broken:
        def generate(self, *_args):
            raise ValueError('unexpected')
    with pytest.raises(ContentFailure) as failed:
        ProviderTemplateTransport(lambda: (Broken(), 'model-a'), tmp_path).generate(request(), threading.Event())
    assert failed.value.code == 'PROCESS_FAILED' and failed.value.cleanup_verified is True
    assert ProviderTemplateTransport(lambda: (provider, 'model-a'), tmp_path).reconcile(object()) is None


@pytest.mark.parametrize('failure', ['connection', 'model', 'factory'])
def test_preprovider_refusals_prove_no_dispatch(tmp_path, failure):
    provider = Provider()
    def selected():
        if failure == 'factory':
            raise ContentFailure('CONNECTION_REQUIRED')
        return None if failure == 'connection' else (provider, 'other-model')
    transport = ProviderTemplateTransport(selected, tmp_path)
    with pytest.raises(ContentFailure) as caught:
        transport.generate(request(), threading.Event())
    assert caught.value.cleanup_verified
    assert caught.value.dispatch_witness == {'neverDispatched': True}
    assert provider.calls == []
    proof = transport.prove_return(SimpleNamespace(id='reserved', owner={'leaseId': 'lease'}), caught.value)
    assert proof.attempt_id == 'reserved' and proof.never_dispatched


@pytest.mark.asyncio
async def test_direct_import_passes_and_resets_its_shared_permit(tmp_path):
    from tests.templates.template_runtime_fixtures import RuntimeFixture
    from resume_api.importer.template_direct import TemplateDirect
    from resume_api.inference_admission import InferenceAdmission
    fixture, admission, calls = RuntimeFixture(tmp_path), InferenceAdmission(), []
    class OwnedProvider:
        def generate_owned(self, request, files, cancel, permit):
            calls.append('owned')
            with permit.hold(cancel):
                return fixture.transport.generate(request, cancel)
        def generate(self, *args):
            raise AssertionError('direct import lost its permit')
    fixture.pipeline.transport = ProviderTemplateTransport(
        lambda: (OwnedProvider(), fixture.command.capture.primary.model), tmp_path / 'transport')
    result = await TemplateDirect(fixture.pipeline, admission).run(fixture.project, fixture.command)
    assert result.state == 'published' and calls == ['owned', 'owned']
    assert JOB_PERMIT.get() is None and not admission.locked()


@pytest.mark.asyncio
async def test_missing_connection_can_finalize_fallback_without_unknown_cleanup(tmp_path):
    from tests.templates.template_runtime_fixtures import RuntimeFixture
    fixture = RuntimeFixture(tmp_path)
    fixture.pipeline.transport = ProviderTemplateTransport(lambda: None, tmp_path / 'transport')
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published'
    assert result.attempts[0].cleanup.state == 'verified'


@pytest.mark.parametrize('code', ['INPUT_TOO_LARGE', 'INVALID_INPUT', 'MODEL_DENIED'])
def test_provider_refusals_before_any_process_are_proved_undispatched(tmp_path, code):
    # LIVE-04: an oversized review was refused before launch but stayed unverified and fenced the import.
    class Refusing(Provider):
        def generate(self, _request, _files, _cancel):
            raise ContentFailure(code)
    transport = ProviderTemplateTransport(lambda: (Refusing(), 'model-a'), tmp_path)
    with pytest.raises(ContentFailure) as refused:
        transport.generate(request(), threading.Event())
    assert (refused.value.code, refused.value.cleanup_verified, refused.value.dispatch_witness) == (
        code, True, {'neverDispatched': True})
    # A refusal that already carries a witness is the provider's own account and is kept.
    class Witnessed(Provider):
        def generate(self, _request, _files, _cancel):
            raise ContentFailure(code, dispatch_witness={'transport': 'codex'})
    with pytest.raises(ContentFailure) as kept:
        ProviderTemplateTransport(lambda: (Witnessed(), 'model-a'), tmp_path).generate(request(), threading.Event())
    assert kept.value.dispatch_witness == {'transport': 'codex'} and kept.value.cleanup_verified is not True


def test_owned_codex_calls_under_one_permit_generate_at_once(tmp_path):
    # CT10: the job permit is the profile share key, so two blocks of one import are inside generation together.
    from contextlib import contextmanager
    from pathlib import Path
    from packages.resume_core.storage import private_directory
    from resume_api.providers.codex_cli import CodexCliProvider
    root = tmp_path / 'profile'
    private_directory(root)
    provider = CodexCliProvider(Path('/nonexistent/synthetic'),
        experimental_profile=SimpleNamespace(root=root, prepare=lambda: None, launch=None))
    together, results = threading.Barrier(2, timeout=3), []
    provider._generate = lambda _request, _files, _cancel: together.wait() is not None and 'generated'
    class Permit:
        @contextmanager
        def hold(self, _cancel):
            yield
    permit, files = Permit(), SimpleNamespace(root=tmp_path / 'operations')
    threads = [threading.Thread(target=lambda: results.append(provider.generate_owned(None, files, threading.Event(), permit)))
        for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert results == ['generated', 'generated']
