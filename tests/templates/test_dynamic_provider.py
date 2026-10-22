"""Controlled transports prove raw validation and honest post-return accounting."""

import asyncio
from dataclasses import replace
import json
import threading
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict
import pytest

from tests.cli_spike.test_codex_adapter import fake, PROMPT
from resume_api.lifecycle import OperationFiles
from resume_api.providers.codex_cli import CodexCliProvider, FixtureTransport
from resume_api.providers.content import ContentFailure, ContentInput, GenerationPolicy, outcome_state
from resume_api.providers.dynamic_result import DynamicResultSpec, dynamic_result
from resume_api.jobs.appserver import SharedContentProvider
from packages.resume_core.reasoning import ModelReasoning
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


class ControlledServer:
    cleanup_failed=False
    def __init__(self,raw,*,state='completed',error=None,cleanup=True,usage=True,global_cleanup_failed=False):
        self.cleanup_failed=global_cleanup_failed
        self.raw=raw; self.state=state; self.error=error; self.cleanup=cleanup; self.usage=usage
        self.clock=SimpleNamespace(now=lambda:1.0); self.live={}; self.calls=[]
        self.reasoning={'gpt-6-luna':ModelReasoning(supported=['low','medium','high'],default='medium')}
    async def prepare(self): pass
    async def run(self,value):
        await value.before_turn(); self.calls.append(value)
        return {'state':self.state,'error':self.error,'cleanupVerified':self.cleanup,'text':self.raw,
            'usage':{'inputTokens':100,'cachedInputTokens':20,'outputTokens':30} if self.usage else None,
            'witness':{'threadId':'synthetic-thread','turnId':'synthetic-turn','generation':1},'nativeStarted':False}


async def shared(raw,*,spec=None,effort=None,audit=lambda _value:None,on_return=None,**changes):
    server=ControlledServer(raw,**changes); provider=SharedContentProvider(server,native=False,audit=audit)
    provider.job_id='synthetic'; provider.cancelled=asyncio.Event()
    result=await provider.execute(ContentInput('Synthetic scope',spec or dynamic_result(SCHEMA),
        GenerationPolicy('gpt-6-luna',allow_repair=False,reasoning_effort=effort),on_return=on_return),threading.Event())
    return result,server


@pytest.mark.asyncio
async def test_shared_dynamic_and_basemodel_paths_keep_their_values():
    dynamic,server=await shared(json.dumps({'payload':VALID}))
    class Legacy(BaseModel):
        model_config=ConfigDict(extra='forbid')
        year:int
        journal:str
    legacy,_=await shared(json.dumps(VALID),spec=Legacy)
    assert dynamic.value.payload == VALID
    assert legacy.value.year == VALID['year']
    assert len(server.calls) == 1 and server.calls[0].reasoning_effort == 'medium'
    assert dynamic.cleanup_verified and dynamic.usage.input_tokens == 100


@pytest.mark.asyncio
@pytest.mark.parametrize('raw',['{invalid',json.dumps({'payload':{'year':'2024','journal':'Systems Notes'}}),
    json.dumps({'payload':{'year':2024,'journal':'Wrong'}}),json.dumps({'payload':None}), 'null'])
async def test_shared_invalid_final_keeps_returned_usage_and_dispatch(raw):
    with pytest.raises(ContentFailure) as caught: await shared(raw)
    error=caught.value
    assert error.code == 'INVALID_RESULT' and error.logical_attempts == 1
    assert (error.usage.input_tokens,error.usage.cached_input_tokens,error.usage.output_tokens) == (100,20,30)
    assert error.cleanup_verified and error.dispatch_witness['turnId'] == 'synthetic-turn'


@pytest.mark.asyncio
async def test_legacy_invalid_final_also_retains_shared_usage():
    class Legacy(BaseModel):
        model_config=ConfigDict(extra='forbid',strict=True)
        value:int
    with pytest.raises(ContentFailure) as caught: await shared('{"value":"wrong"}',spec=Legacy)
    assert caught.value.usage.input_tokens == 100 and caught.value.logical_attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('effort',['low','high','ultra'])
async def test_shared_structured_effort_is_never_silently_replaced(effort):
    server=ControlledServer(json.dumps({'payload':VALID})); provider=SharedContentProvider(server,native=False)
    provider.job_id='synthetic';provider.cancelled=asyncio.Event()
    with pytest.raises(ContentFailure,match='MODEL_DENIED') as caught:
        await provider.execute(ContentInput('Synthetic',dynamic_result(SCHEMA),
            GenerationPolicy('gpt-6-luna',allow_repair=False,reasoning_effort=effort)),threading.Event())
    assert caught.value.logical_attempts == 0 and server.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('state,error,cleanup,expected',[('failed','REFUSED',True,'refused'),
    ('failed','INCOMPLETE_STREAM',True,'incomplete'),('cancelled',None,True,'cancelled'),
    ('failed','DEADLINE',True,'timed_out'),('failed','CLEANUP_FAILED',False,'cleanup_failure'),
    ('failed','PROTOCOL',True,'transport_failure')])
async def test_observed_terminal_codes_preserve_distinct_outcomes(state,error,cleanup,expected):
    with pytest.raises(ContentFailure) as caught:
        await shared('',state=state,error=error,cleanup=cleanup)
    assert outcome_state(caught.value.code) == expected
    assert caught.value.logical_attempts == 1
    assert caught.value.cleanup_verified is cleanup
    assert caught.value.usage.output_tokens == 30


@pytest.mark.asyncio
async def test_unknown_usage_is_not_fabricated():
    with pytest.raises(ContentFailure) as caught: await shared('{invalid',usage=False)
    assert caught.value.usage.input_tokens is None and not caught.value.usage.complete


def test_server_only_format_and_defaults_are_not_decoder_coercions():
    spec=dynamic_result({'type':'object','additionalProperties':False,'required':['date'],
        'properties':{'date':{'type':'string','format':'date','default':'2024-01-01'}}})
    with pytest.raises(SchemaFailure): spec.decode_value({'payload':{'date':'2024-02-31'}})
    with pytest.raises(SchemaFailure): spec.decode_value({'payload':{}})
    assert spec.decode_value({'payload':{'date':'2024-02-29'}}).payload == {'date':'2024-02-29'}


@pytest.mark.asyncio
async def test_shared_server_cleanup_fence_rejects_even_a_completed_turn():
    with pytest.raises(ContentFailure,match='CLEANUP_FAILED') as caught:
        await shared(json.dumps({'payload':VALID}),global_cleanup_failed=True)
    assert caught.value.cleanup_verified is False
    assert caught.value.logical_attempts == 1 and caught.value.usage.output_tokens == 30


@pytest.mark.asyncio
async def test_shared_dynamic_decoder_uses_the_captured_output_limit():
    value='Synthetic '+('x'*70_000)
    result,server=await shared(json.dumps({'payload':value}),spec=dynamic_result({'type':'string'}))
    assert result.value.payload == value
    assert server.calls[0].text_limit == 262_144
    provider=SharedContentProvider(ControlledServer(json.dumps({'payload':value})),native=False)
    provider.job_id='bounded'; provider.cancelled=asyncio.Event()
    with pytest.raises(ContentFailure,match='INVALID_RESULT') as caught:
        await provider.execute(ContentInput('Synthetic',dynamic_result({'type':'string'}),
            GenerationPolicy('gpt-6-luna',allow_repair=False,max_total_output_bytes=65_536)),threading.Event())
    assert caught.value.usage.output_tokens == 30 and caught.value.logical_attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,code',[(OSError,'TEMP_FAILED'),(RuntimeError,'CLI_FAILED')])
async def test_shared_post_return_audit_failure_keeps_accounting(failure,code):
    def audit(_value): raise failure('synthetic audit failure')
    with pytest.raises(ContentFailure,match=code) as caught:
        await shared(json.dumps({'payload':VALID}),audit=audit)
    error=caught.value
    assert error.logical_attempts == 1 and error.cleanup_verified
    assert error.usage.input_tokens == 100 and error.usage.output_tokens == 30
    assert error.dispatch_witness['turnId'] == 'synthetic-turn'


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


@pytest.mark.asyncio
@pytest.mark.parametrize('audit_failure', [False, True])
async def test_shared_return_checkpoint_precedes_decode_and_audit(monkeypatch, audit_failure):
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
    def audit(_value):
        order.append('audit')
        raise OSError('controlled audit interruption')
    raw = json.dumps({'payload': VALID if audit_failure else {'year': 'wrong', 'journal': 'Synthetic'}})
    with pytest.raises(ContentFailure, match='TEMP_FAILED' if audit_failure else 'INVALID_RESULT') as caught:
        await shared(raw, on_return=checkpoint, audit=audit)
    assert order == (['checkpoint', 'decode', 'audit'] if audit_failure else ['checkpoint', 'decode'])
    assert len(frames) == 1 and frames[0].raw_return == caught.value.raw_return == raw
    assert frames[0].usage == caught.value.usage and frames[0].cleanup_verified


@pytest.mark.asyncio
async def test_shared_refusal_is_checkpointed_before_audit():
    frames = []
    with pytest.raises(ContentFailure, match='REFUSED') as caught:
        await shared('controlled refusal text', state='failed', error='REFUSED', on_return=frames.append)
    assert len(frames) == 1 and frames[0].outcome == 'refused' and frames[0].original_code == 'REFUSED'
    assert frames[0].raw_return == caught.value.raw_return == 'controlled refusal text'
