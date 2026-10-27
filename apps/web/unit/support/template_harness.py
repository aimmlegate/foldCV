"""Serve one synthetic V7 project on the /v2 project routes for the client editor tests.

The store lives under the given empty resolved temporary root. No provider, model, network service or user project is
used. The first stdout line is the handshake; the service stops when stdin closes.
"""

import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / 'services/api/src')]


class ScriptedRewrite:
    """Selected-text rewrites with deterministic text, and one held call for cancellation."""

    def __init__(self):
        self.calls, self.held = [], {}

    async def text(self, _project, request_id, instruction, source):
        from packages.resume_core.project_repository import RepositoryFailure
        self.calls.append({'requestId': request_id, 'instruction': instruction, 'source': source})
        if instruction == 'hold':
            event = self.held[request_id] = asyncio.Event()
            await event.wait()
            raise RepositoryFailure('CANCELLED')
        if instruction == 'fail':
            raise RepositoryFailure('MODEL_DENIED')
        return source.upper() if instruction == 'upper' else source + ' (revised)'

    def cancel(self, _project, request_id):
        event = self.held.pop(request_id, None)
        if event is not None:
            event.set()
        return event is not None


def linked(ref):
    return [{'type': 'text', 'text': 'See ', 'styles': {}, 'presentation': ref}, {'type': 'link',
        'href': 'https://example.test/x', 'presentation': ref, 'content': [{'type': 'text', 'text': 'example page',
            'styles': {}, 'presentation': ref}]}, {'type': 'text', 'text': ' now', 'styles': {}, 'presentation': ref}]


def scenario_workspace(scenario):
    from tests.templates.storage_fixtures import joined, workspace
    if scenario == 'issues':
        # Employment with two import issues (role and result metric): the E03 shape.
        from tests.templates.test_materialize import issue_workspace
        return issue_workspace()
    if scenario == 'e04':
        # Two identically worded tasks, a team result and a second employer: the E04 shape.
        from tests.templates.e04_fixtures import e04_workspace
        return e04_workspace()
    if scenario == 'publications':
        # CT08: the second template; two equal-title papers and two employers.
        from tests.templates.publications_fixtures import publications_workspace
        return publications_workspace('F11')
    if scenario == 'bound':
        from tests.templates.test_bound_links import linked_workspace
        return linked_workspace()[0], workspace()[1]
    values = {'joined': joined, 'linked': lambda: joined(linked), 'papers': lambda: workspace()[0]}
    return values[scenario](), workspace()[1]


def application(root, scenario):
    from fastapi import FastAPI
    from packages.resume_core.project_repository import ProjectRepository
    from resume_api.projects.routes import mount_projects_v2
    from resume_api.projects.service import ProjectService
    value, sources = scenario_workspace(scenario)
    repository = ProjectRepository(root)
    repository.create(value, blobs=[('sources', key, raw, hashlib.sha256(raw).hexdigest()) for key, raw in sources.items()])
    projects = ProjectService(repository)
    rewrites = ScriptedRewrite()
    projects.rewrite_text, projects.rewrite_cancel = rewrites.text, rewrites.cancel
    app = FastAPI()
    mount_projects_v2(app, projects)
    project = value.project_id

    @app.post('/harness/advance')
    async def advance():
        # An outside metadata-only commit, as an export record makes; the document is unchanged.
        before = repository.read(project)
        after = before.model_copy()
        after.updated_at = '2026-10-21T00:00:01Z'
        saved = repository.replace(project, base_revision=before.project_revision, workspace=after)
        return {'projectRevision': saved.revision}

    @app.get('/harness/rewrites')
    async def rewrite_calls():
        return {'calls': rewrites.calls}

    return app, {'project': project}


async def serve(root, scenario):
    import uvicorn
    app, handshake = application(root, scenario)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=0, log_level='warning', lifespan='off'))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    print(json.dumps({**handshake, 'origin': 'http://127.0.0.1:' + str(port)}), flush=True)
    await asyncio.get_running_loop().run_in_executor(None, sys.stdin.read)
    server.should_exit = True
    await task


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: template_harness.py <resolved-empty-root> <joined|linked|papers|bound|issues|e04|publications>')
    root = Path(sys.argv[1])
    if root != root.resolve() or not root.is_dir() or any(root.iterdir()):
        raise SystemExit('harness root must be an existing empty resolved directory')
    asyncio.run(serve(root, sys.argv[2]))


if __name__ == '__main__':
    main()
