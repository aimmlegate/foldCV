"""Controlled transports prove raw validation and honest post-return accounting."""

import json
import threading

import pytest

from tests.providers.fixtures import PROMPT, fake  # noqa: F401 (fake is a fixture)
from resume_api.lifecycle import OperationFiles
from resume_api.providers.codex_cli import CodexCliProvider, FixtureTransport
from resume_api.providers.content import ContentFailure, ContentInput, GenerationPolicy
from resume_api.providers.dynamic_result import dynamic_result
from packages.resume_core.templates.projection import SchemaFailure

SCHEMA={'type':'object','additionalProperties':False,'required':['year','journal'],
    'properties':{'year':{'type':'integer','minimum':2020,'maximum':2025},'journal':{'type':'string'}},
    'if':{'properties':{'year':{'const':2024}}},'then':{'properties':{'journal':{'const':'Systems Notes'}}}}
VALID={'year':2024,'journal':'Systems Notes'}


def direct(fake,value,*,on_return=None,**changes):
    cli,root,keep,configure,starts=fake
    configure('valid',result_text=json.dumps({'payload':value}),schema_required=['payload'])
    provider=CodexCliProvider(cli,fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        result=provider.generate(ContentInput(PROMPT,dynamic_result(SCHEMA),
            GenerationPolicy('gpt-6-luna',allow_repair=False,**changes),on_return=on_return),files,threading.Event())
    return result,starts()


def test_direct_dynamic_result_and_legacy_model_both_work(fake):
    result,calls=direct(fake,VALID)
    assert result.value.payload == VALID and calls == result.logical_attempts == 1
    assert result.cleanup_verified and result.dispatch_witness['dispatched']
    assert result.reasoning_effort == 'medium'
    assert result.usage.input_tokens is not None


@pytest.mark.parametrize('value',[{'year':'2024','journal':'Systems Notes'}, {'year':2010,'journal':'Systems Notes'},
    {'year':2024,'journal':'Wrong journal'}, {'year':2024}, {'year':2024,'journal':'Systems Notes','extra':True}])
def test_direct_raw_failures_retain_charge_usage_and_cleanup_without_repair(fake,value):
    with pytest.raises(ContentFailure) as caught: direct(fake,value)
    error=caught.value
    assert error.code == 'INVALID_RESULT' and error.logical_attempts == 1
    assert error.usage.input_tokens is not None and error.usage.output_tokens is not None
    assert error.cleanup_verified and error.dispatch_witness['dispatched']
    assert fake[-1]() == 1


def test_dynamic_call_cannot_enable_adapter_repair(fake):
    cli,root,keep,configure,starts=fake
    provider=CodexCliProvider(cli,fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files, pytest.raises(ContentFailure,match='INVALID_INPUT'):
        provider.generate(ContentInput(PROMPT,dynamic_result(SCHEMA),GenerationPolicy('gpt-6-luna')),files,threading.Event())
    assert starts() == 0


def test_dynamic_unsupported_effort_fails_before_generation(fake):
    with pytest.raises(ContentFailure,match='MODEL_DENIED') as caught: direct(fake,VALID,reasoning_effort='ultra')
    assert caught.value.logical_attempts == fake[-1]() == 0


def test_server_only_format_and_defaults_are_not_decoder_coercions():
    spec=dynamic_result({'type':'object','additionalProperties':False,'required':['date'],
        'properties':{'date':{'type':'string','format':'date','default':'2024-01-01'}}})
    with pytest.raises(SchemaFailure): spec.decode_value({'payload':{'date':'2024-02-31'}})
    with pytest.raises(SchemaFailure): spec.decode_value({'payload':{}})
    assert spec.decode_value({'payload':{'date':'2024-02-29'}}).payload == {'date':'2024-02-29'}


def test_direct_unexpected_post_return_decoder_failure_keeps_accounting(fake,monkeypatch):
    from resume_api.providers.codex_cli import Events
    def fail(*_args,**_kwargs): raise RuntimeError('synthetic decoder failure')
    monkeypatch.setattr(Events,'result',fail)
    with pytest.raises(ContentFailure,match='CLI_FAILED') as caught: direct(fake,VALID)
    assert caught.value.logical_attempts == 1 and caught.value.cleanup_verified
    assert caught.value.usage.input_tokens is not None
    assert caught.value.dispatch_witness['dispatched']


def test_direct_return_checkpoint_precedes_decoder_and_preserves_raw_failure(fake, monkeypatch):
    from resume_api.providers.codex_cli import Events
    frames, order = [], []
    original = Events.result
    def decode(self, *args, **kwargs):
        order.append('decode')
        assert len(frames) == 1
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Events, 'result', decode)
    def checkpoint(frame):
        order.append('checkpoint')
        frames.append(frame)
    with pytest.raises(ContentFailure, match='INVALID_RESULT') as caught:
        direct(fake, {'year': 'wrong', 'journal': 'Synthetic'}, on_return=checkpoint)
    assert order == ['checkpoint', 'decode'] and frames[0].outcome == 'completed'
    assert frames[0].raw_return == caught.value.raw_return
    assert frames[0].usage == caught.value.usage and frames[0].cleanup_verified
    assert fake[-1]() == frames[0].logical_attempts == 1
