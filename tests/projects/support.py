"""An app with synthetic projects in a temporary store and a client that goes through the same-origin boundary."""

from contextlib import contextmanager
import hashlib

from fastapi.testclient import TestClient

from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.templates.presentation import snapshot_identity
from tests.support.foundation import ForbiddenContentProvider

ORIGIN = 'http://127.0.0.1:8765'
SECRET = 'synthetic-startup-secret-0123456789abcdef'


def source_blobs(sources):
    return [('sources', key, raw, hashlib.sha256(raw).hexdigest()) for key, raw in sources.items()]


@contextmanager
def v2_app(root, projects=(), **options):
    from resume_api.app import create_app
    if not {'experimental_profile', 'provider_slots'} & options.keys():
        options.setdefault('content_provider', ForbiddenContentProvider())
    dist = root / 'dist'
    dist.mkdir(parents=True, exist_ok=True)
    (dist / 'index.html').write_text('v2 projects')
    wrapped = create_app(origin=ORIGIN, secret=SECRET, temp_root=root / 'operations', dist=dist, data_root=root / 'data', **options)
    repository = wrapped.app.state.projects.repository
    for workspace, sources in projects:
        repository.create(workspace, blobs=source_blobs(sources))
    with TestClient(wrapped, base_url=ORIGIN, headers={'Origin': ORIGIN}) as client:
        assert client.post('/v1/session/exchange', json={'secret': SECRET}).status_code == 200
        yield client, wrapped.app


class Editor:
    """One open project as the editor page sees it: token, last response, history state."""

    def __init__(self, client, project):
        self.client, self.project = client, project
        opened = self.call('post', '/open', {})
        self.token, self.response, self.history = opened['editorToken'], opened['response'], opened['history']

    def call(self, method, path, body=None, *, status=200):
        reply = getattr(self.client, method)('/v2/projects/' + self.project + path, **({'json': body} if body is not None else {}))
        assert reply.status_code == status, (reply.status_code, reply.text[:400])
        return reply.json()

    def refused(self, method, path, body, status):
        reply = self.client.request(method.upper(), '/v2/projects/' + self.project + path, json=body)
        assert reply.status_code == status, (reply.status_code, reply.text[:400])
        return reply.json()

    @property
    def revision(self):
        return self.response['workspace']['projectRevision']

    def workspace(self):
        return WorkspaceV7.model_validate(self.response['workspace'])

    def adopt(self, result):
        self.response, self.history = result['response'], result['history']
        return result

    def edit(self, preparation, *, base=None, status=200):
        body = {'editorToken': self.token, 'baseRevision': self.revision if base is None else base, 'preparation': preparation}
        if status != 200:
            return self.refused('post', '/edits', body, status)
        return self.adopt(self.call('post', '/edits', body))

    def step(self, direction, identifier, *, expected=None, base=None, status=200):
        body = {'editorToken': self.token, 'baseRevision': self.revision if base is None else base, 'direction': direction,
            'clientMutationId': identifier, 'expectedActionId': expected}
        if status != 200:
            return self.refused('post', '/history', body, status)
        return self.adopt(self.call('post', '/history', body))

    def capture(self, selection, identifier='capture-1'):
        workspace = self.workspace()
        return self.call('post', '/clipboard', {'editorToken': self.token, 'clientCaptureId': identifier,
            'snapshot': snapshot_identity(workspace).model_dump(mode='json', by_alias=True), 'selection': selection})


def v2_client(store, workspace, sources):
    """For bench.py --api v2: an open editor on the fixture project; `edit` takes a preparation model."""
    context = v2_app(store, [(workspace, sources)])
    client, _app = context.__enter__()
    editor = Editor(client, workspace.project_id)

    class Bench:
        # The app context must outlive setup: dropping it would close the sessions and forget the editor token.
        app_context = context

        def edit(self, preparation):
            import time
            body = {'editorToken': editor.token, 'baseRevision': editor.revision,
                'preparation': preparation.model_dump(mode='json', by_alias=True)}
            started = time.perf_counter()
            reply = client.post('/v2/projects/' + editor.project + '/edits', json=body)
            elapsed = time.perf_counter() - started
            assert reply.status_code == 200, reply.text[:400]
            editor.adopt(reply.json())
            return {'request': round(elapsed * 1000), 'bytes': len(reply.content)}

        def current(self):
            return editor.workspace()

        def close(self):
            context.__exit__(None, None, None)
    return Bench(), workspace.project_id
