"""PUT /v1/settings/rewrite-reasoning: only a level the selected model reports is saved, and it survives in preferences."""

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
