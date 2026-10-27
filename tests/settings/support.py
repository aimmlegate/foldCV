"""An app on a temporary store with a scripted connection, and an async client past the session exchange."""

from contextlib import asynccontextmanager

import httpx

from packages.resume_core.reasoning import ModelReasoning
from resume_api.app import create_app
from resume_api.connection import Metadata, Quota
from tests.support.generation import CreationProvider, frozen_now

ORIGIN = 'http://127.0.0.1:39272'
SECRET = 'synthetic-preferences-secret-0123456789'


class MetadataAdapter:
    """Reports two models; a native login or an unexpected probe is counted, never run."""

    def __init__(self):
        self.inspections = 0
        self.logins = 0

    def inspect(self, _files, _cancel, *, full=True):
        self.inspections += 1
        reasoning = {model: ModelReasoning(default='medium', supported=['low', 'medium', 'high']) for model in ('model-a', 'model-b')}
        return Metadata('fixture-cli', ('model-a', 'model-b'), 'plus', Quota('available', 25), reasoning)

    def login(self, _files, _cancel):
        self.logins += 1
        raise AssertionError('native login')


def application(tmp_path, adapter=None, provider=None, **options):
    dist = tmp_path / 'dist'
    dist.mkdir(exist_ok=True)
    (dist / 'index.html').write_text('fixture')
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / 'operations', dist=dist,
        connection_adapter=adapter or MetadataAdapter(), content_provider=provider or CreationProvider(), clock=frozen_now,
        data_root=tmp_path / 'store', **options)


@asynccontextmanager
async def client_session(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers={'Origin': ORIGIN}) as client:
        assert (await client.post('/v1/session/exchange', json={'secret': SECRET})).status_code == 200
        yield client
