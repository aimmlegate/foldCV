"""PUT /v1/settings/rewrite-reasoning and rewrite-model: only a level the rewrite model reports is saved, and both survive
in preferences; the rewrite model follows the processing model while unset."""

from dataclasses import replace
import json

import pytest

from packages.resume_core.reasoning import ModelReasoning
from tests.settings.support import MetadataAdapter, application, client_session
from tests.support.generation import CreationProvider


class Adapter(MetadataAdapter):
    def inspect(self, *args, **kwargs):
        return replace(super().inspect(*args, **kwargs), reasoning={
            'model-a': ModelReasoning(supported=['low', 'medium'], default='medium'),
            'model-b': ModelReasoning(supported=['high'], default='high')})


@pytest.mark.asyncio
async def test_reasoning_uses_reported_levels_persists_and_rejects_another_model_or_level(tmp_path):
    adapter, provider = Adapter(), CreationProvider()
    app = application(tmp_path, adapter, provider)
    async with client_session(app) as client:
        state = (await client.post('/v1/host/status', json={})).json()
        assert state['modelReasoning']['model-a']['supported'] == ['low', 'medium']
        await client.post('/v1/host/select', json={'model': 'model-a'})
        saved = await client.put('/v1/settings/rewrite-reasoning', json={'model': 'model-a', 'effort': 'low'})
        assert saved.status_code == 200 and saved.json()['rewriteReasoningEffort'] == 'low'
        for payload in ({'model': 'model-a', 'effort': 'high'}, {'model': 'model-b', 'effort': 'high'}):
            assert (await client.put('/v1/settings/rewrite-reasoning', json=payload)).status_code == 409
        assert (await client.get('/v1/settings/preferences')).json()['rewriteReasoningEffort'] == 'low'
    assert provider.calls == [] and adapter.inspections == 1
    assert json.loads((tmp_path / 'store/preferences.json').read_text())['rewriteReasoningEffort'] == 'low'


@pytest.mark.asyncio
async def test_a_rewrite_model_is_a_listed_model_and_keeps_only_a_level_it_reports(tmp_path):
    app = application(tmp_path, Adapter(), CreationProvider())
    async with client_session(app) as client:
        assert (await client.put('/v1/settings/rewrite-model', json={'model': 'model-b'})).status_code == 409
        await client.post('/v1/host/status', json={})
        await client.post('/v1/host/select', json={'model': 'model-a'})
        await client.put('/v1/settings/rewrite-reasoning', json={'model': 'model-a', 'effort': 'low'})
        assert (await client.put('/v1/settings/rewrite-model', json={'model': 'model-c'})).status_code == 409
        chosen = (await client.put('/v1/settings/rewrite-model', json={'model': 'model-b'})).json()
        assert (chosen['selectedRewriteModel'], chosen['rewriteReasoningEffort']) == ('model-b', None)
        # The level now belongs to the rewrite model, not to the processing model.
        assert (await client.put('/v1/settings/rewrite-reasoning', json={'model': 'model-a', 'effort': 'low'})).status_code == 409
        saved = await client.put('/v1/settings/rewrite-reasoning', json={'model': 'model-b', 'effort': 'high'})
        assert saved.status_code == 200 and saved.json()['rewriteReasoningEffort'] == 'high'
        followed = (await client.put('/v1/settings/rewrite-model', json={'model': None})).json()
        assert (followed['selectedRewriteModel'], followed['rewriteReasoningEffort']) == (None, None)
        assert (await client.put('/v1/settings/rewrite-reasoning', json={'model': 'model-a', 'effort': 'medium'})).status_code == 200
    stored = json.loads((tmp_path / 'store/preferences.json').read_text())
    assert (stored['selectedRewriteModel'], stored['rewriteReasoningEffort']) == (None, 'medium')
