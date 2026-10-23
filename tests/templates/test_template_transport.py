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
