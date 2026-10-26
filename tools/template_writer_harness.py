"""Serve one isolated synthetic V7 writer for nonbrowser client queue tests.

The store lives under the given resolved temporary root. No provider, model,
network service or user project is used. The first stdout line is the handshake.
"""

import asyncio
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/api/src'))


class ScriptedRewrite:
    """A scripted content provider for selected-text rewrites: deterministic text, a held call for cancellation."""

    def __init__(self):
        self.calls, self.held = [], {}

    async def text(self, _project, request_id, instruction, source):
        from packages.resume_core.background_store import BackgroundFailure
        self.calls.append({'requestId': request_id, 'instruction': instruction, 'source': source})
        if instruction == 'hold':
            event = self.held[request_id] = asyncio.Event()
            await event.wait()
            raise BackgroundFailure('CANCELLED')
        if instruction == 'fail':
            raise BackgroundFailure('MODEL_DENIED')
        return source.upper() if instruction == 'upper' else source + ' (revised)'

    def cancel(self, _project, request_id):
        event = self.held.pop(request_id, None)
        if event is not None:
            event.set()
        return event is not None


def application(root, scenario):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from resume_api.jobs.writers import mount_writers
    from packages.resume_core.background_store import BackgroundFailure
    from tests.templates.address_map_fixtures import joined
    from tests.templates.storage_fixtures import workspace
    from tests.templates.test_template_writers import TemplateWriterFixture
    linked = lambda ref: [{'type': 'text', 'text': 'See ', 'styles': {}, 'presentation': ref}, {'type': 'link',
        'href': 'https://example.test/x', 'presentation': ref, 'content': [{'type': 'text', 'text': 'example page',
            'styles': {}, 'presentation': ref}]}, {'type': 'text', 'text': ' now', 'styles': {}, 'presentation': ref}]
    from tests.templates.test_materialize import issue_workspace
    if scenario == 'issues':
        # Employment with two import issues (role and result metric): the E03 shape.
        value, sources = issue_workspace()
    elif scenario == 'e04':
        # Two identically worded tasks, a team result and a second employer: the E04 shape.
        from tests.templates.e04_fixtures import e04_workspace
        value, sources = e04_workspace()
    elif scenario == 'publications':
        # CT08: the second template; two equal-title papers and two employers, the first with an owned award and an
        # extension-of division (D03/E04 for extension ownership).
        from tests.templates.publications_fixtures import publications_workspace
        value, sources = publications_workspace('F11')
    else:
        from tests.templates.test_bound_links import linked_workspace
        value, sources = {'joined': joined, 'linked': lambda: joined(linked), 'papers': lambda: workspace()[0],
            'bound': lambda: linked_workspace()[0]}[scenario](), workspace()[1]
    fixture = TemplateWriterFixture(root, value, sources)
    rewrites = ScriptedRewrite()
    service = SimpleNamespace(enabled=True, writers=fixture.writers, store=fixture.jobs, publisher=fixture.publisher,
        projects=SimpleNamespace(originals=fixture.originals, artifacts={}, images={}, state_lock=threading.RLock(),
            template_rewrite_text=rewrites.text, template_rewrite_cancel=rewrites.cancel),
        publication=SimpleNamespace(adopt=lambda *_args: None),
        # No background publication supervisor runs in this harness.
        wake_publication=lambda _project: None)
    app = FastAPI()
    mount_writers(app, service)

    @app.post('/harness/advance')
    async def advance():
        # An outside metadata-only canonical advance, as an export record makes; the document is unchanged.
        from packages.resume_core.background_history import digest_bytes
        from packages.resume_core.models.template_workspace import WorkspaceV7
        before = fixture.canonical.read_committed(fixture.project)[0]
        data = before.model_dump(by_alias=True)
        data['projectRevision'] += 1
        data['project']['revision'] += 1
        data['updatedAt'] = '2026-10-21T00:00:01Z'
        saved, _duplicate = fixture.publisher.snapshot(fixture.project, digest_bytes(before), WorkspaceV7.model_validate(data),
            'metadata_harness_' + str(data['projectRevision']), originals=fixture.originals)
        return {'projectRevision': saved.project_revision}

    @app.get('/harness/rewrites')
    async def rewrite_calls():
        return {'calls': rewrites.calls}

    @app.exception_handler(BackgroundFailure)
    async def failure(_request, error):
        return JSONResponse({'error': {'code': error.code}}, status_code=409)

    view = fixture.view.model_dump(mode='json', by_alias=True)
    handshake = {'project': fixture.project, 'proof': fixture.proof.model_dump(mode='json', by_alias=True),
        'view': view, 'credentialHint': 'synthetic'}
    return app, handshake


async def serve(root, scenario):
    import uvicorn
    app, handshake = application(root, scenario)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=0, log_level='warning', lifespan='off'))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    print(json.dumps({**handshake, 'origin': 'http://127.0.0.1:' + str(port)}), flush=True)
    # Exit when the test closes stdin so no orphaned service survives.
    await asyncio.get_running_loop().run_in_executor(None, sys.stdin.read)
    server.should_exit = True
    await task


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: template_writer_harness.py <resolved-empty-root> <joined|linked|papers|issues|e04|publications>')
    root = Path(sys.argv[1])
    if root != root.resolve() or not root.is_dir() or any(root.iterdir()):
        raise SystemExit('harness root must be an existing empty resolved directory')
    asyncio.run(serve(root, sys.argv[2]))


if __name__ == '__main__':
    main()
