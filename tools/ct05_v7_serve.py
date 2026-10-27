"""Serve an isolated CT05 V7 editor proof: two synthetic template projects, scripted providers, no executions.

The root must be a new /private/tmp/foldcv-ct05-* directory. The one-shot browser secret is written only to
root/launch.json (mode 0600); stdout carries the origin and proof URL without it.
"""

import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'services/api/src')]

import uvicorn

from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.storage import atomic_write
from resume_api.agent.runtime import ScriptedAgentRuntime
from resume_api.app import create_app
from spikes.uir.fixtures import NOW
from spikes.uir.providers import ScriptedConnection, ScriptedContent, StoredWeb, scripted_agent
from tests.templates.address_map_fixtures import joined
from tests.templates.storage_fixtures import workspace as papers
from packages.resume_core.text_rewrite import PlainTextReply
from resume_api.providers.content import ContentResult, ReportedUsage


class TemplateConnection(ScriptedConnection):
    """The scripted catalog also names a default reasoning effort, as the real catalog does."""

    def inspect(self, files, cancel, *, full=True):
        from packages.resume_core.reasoning import ModelReasoning
        from dataclasses import replace
        metadata = super().inspect(files, cancel, full=full)
        return replace(metadata, reasoning={name: ModelReasoning(supported=['medium'], default='medium') for name in metadata.models})


class RewriteContent(ScriptedContent):
    """Scripted selected-text rewrite and template tasks: deterministic replies; every generation is counted."""
    template_adapter = 'ct05-scripted'

    def generate(self, request, files, cancel):
        from resume_api.providers.dynamic_result import DynamicResultSpec
        from tests.templates.scripted_template_provider import scripted_template_result
        if isinstance(request.result_type, DynamicResultSpec):
            return scripted_template_result(self, request)
        if request.result_type is not PlainTextReply:
            return super().generate(request, files, cancel)
        self.calls.append({'kind': 'selected_text_rewrite'})
        selected = request.text.rsplit('Selected text:\n', 1)[1].strip()
        return ContentResult(PlainTextReply(text=selected + ' (revised)'), ReportedUsage(), 'ct05-scripted', request.policy.model, 0, 1)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=1) + '\n').encode())


def renamed(workspace, identifier, title):
    value = workspace.model_dump(by_alias=True)
    value['projectId'] = value['project']['projectId'] = identifier
    value['title'] = title
    return WorkspaceV7.model_validate(value)


async def views_workspace(root):
    """CT06 S3: the published F06 import with Focus entries, a band heading and a bound portfolio link."""
    from tests.templates.test_template_view_adapters import published
    work = root / 'fixture'
    work.mkdir(mode=0o700)
    _fixture, value, originals = await published(work)
    return value, originals


async def generic_workspace(root, name):
    """CT06 S4: a published scripted import of one synthetic fixture with the bundled Generic template."""
    from tests.templates.generic_fixtures import generic_import
    work = root / 'fixture'
    work.mkdir(mode=0o700)
    _fixture, _result, value, originals = await generic_import(work, name)
    return value, originals


async def projects(root, employment_shape='issues'):
    """A: joined papers; B: plain papers; C: synthetic employment, either with two import issues (the E03 shape)
    or with two identical tasks and a second employer (the E04 shape), or the CT06 views import. All keep the
    pipeline project identity."""
    from tests.templates.test_materialize import issue_workspace
    from tests.templates.e04_fixtures import e04_workspace
    _workspace, sources = papers()
    if employment_shape == 'views':
        employment, employment_sources = await views_workspace(root)
    elif employment_shape.startswith('generic-'):
        employment, employment_sources = await generic_workspace(root, employment_shape.removeprefix('generic-').upper())
    else:
        employment, employment_sources = {'issues': issue_workspace, 'e04': e04_workspace}[employment_shape]()
    return [(joined(), sources), (renamed(papers()[0], 'template-project-b', 'Synthetic papers B'), sources),
        # Its captured operation is bound to its own distinct project identity, which is kept.
        (employment, employment_sources)]


def refuse_execution(*_args, **_kwargs):
    raise AssertionError('CT05 V7 proof runs no background execution')


async def main(args):
    root = args.root.resolve()
    if root.parent != Path('/private/tmp') or not root.name.startswith('foldcv-ct05-') or root.exists():
        raise ValueError('A new /private/tmp/foldcv-ct05-* root is required')
    dist = args.dist.resolve()
    if not (dist / 'index.html').is_file():
        raise ValueError('A built frontend directory is required')
    root.mkdir(mode=0o700)
    data, operations = root / 'data', root / 'operations'
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', args.port)); listener.listen(128)
    origin = 'http://127.0.0.1:' + str(listener.getsockname()[1]); secret = secrets.token_urlsafe(32)
    connection, content, web = TemplateConnection(), RewriteContent(), StoredWeb()
    runtime = ScriptedAgentRuntime(scripted_agent)
    with patch('resume_api.app.ConnectionAdapter', side_effect=AssertionError('native connection')), \
         patch('resume_api.app.CodexCliProvider', side_effect=AssertionError('native content')), \
         patch('resume_api.app.CodexAgentRuntime', side_effect=AssertionError('native agent')):
        app = create_app(origin=origin, secret=secret, temp_root=operations, data_root=data, dist=dist,
            experimental_profile=None, connection_adapter=connection, gui_provider=content,
            gui_clock=lambda: datetime.fromisoformat(NOW), agent_runtime=runtime,
            background_enabled=True, background_factory=refuse_execution,
            template_import_call_cap=args.template_call_cap, legacy_routes=False)
    app.app.state.agent.tools.fetcher = web
    service = app.app.state.rich_projects
    if args.template_call_cap is not None:
        # The store's active package for new strict imports: the synthetic employment subset.
        from packages.resume_core.templates.store import TemplateStore
        from tests.templates.employment_fixtures import employment_package
        TemplateStore(service.storage.root).activate(employment_package())
    identifiers = []
    for value, sources in await projects(root, args.employment):
        RichProjectStore(service.storage.root).save(value, {(value.project_id, key): raw for key, raw in sources.items()}, {})
        identifiers.append(value.project_id)
    service.ensure_loaded()
    info = {'schemaVersion': 1, 'root': str(root), 'dataRoot': str(data), 'operationRoot': str(operations), 'origin': origin,
        'ownedServicePid': os.getpid(), 'buildDirectory': str(dist), 'projects': identifiers,
        'providers': {'connection': 'ScriptedConnection', 'content': 'RewriteContent (ScriptedContent plus scripted plain rewrite)', 'agent': 'ScriptedAgentRuntime',
            'web': 'StoredWeb', 'background': 'refuse_execution'}, 'experimentalProfile': None,
        'nativeConstructorGuard': 'all three native factory branches guarded; zero calls', 'serviceState': 'running',
        'sourceSha256': {str(path.relative_to(ROOT)): digest(path) for path in [Path(__file__), ROOT / 'spikes/uir/providers.py',
            ROOT / 'tests/templates/address_map_fixtures.py', ROOT / 'tests/templates/storage_fixtures.py',
            ROOT / 'tests/templates/e04_fixtures.py', ROOT / 'tests/templates/test_template_view_adapters.py',
            ROOT / 'tests/templates/generic_fixtures.py',
            ROOT / 'services/api/src/resume_api/app.py']}}

    def diagnostics():
        return {**info, 'callCounts': {'connection': len(connection.calls), 'content': len(content.calls),
            'agent': len(runtime.calls), 'web': len(web.calls), 'nativeStarts': 0},
            'revisions': {identifier: service.read(identifier).project_revision for identifier in identifiers}}

    @app.app.get('/v1/ct05/diagnostics')
    async def read_diagnostics():
        return diagnostics()
    app.app.router.routes.insert(0, app.app.router.routes.pop())
    url = origin + '/?project=' + identifiers[0]
    launch = root / 'launch.json'
    write_json(launch, {'origin': origin, 'url': url + '#secret=' + secret, 'pid': os.getpid()}); launch.chmod(0o600)
    write_json(root / 'isolation.json', diagnostics())
    print(json.dumps({'origin': origin, 'proofUrl': url, 'pid': os.getpid()}), flush=True)
    try:
        await uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=listener.getsockname()[1], proxy_headers=False,
            access_log=False, server_header=False, log_level='warning', timeout_graceful_shutdown=2)).serve(sockets=[listener])
    finally:
        info['serviceState'] = 'stopped'
        write_json(root / 'final-diagnostics.json', diagnostics())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--employment', choices=['issues', 'e04', 'views', 'generic-f06', 'generic-f10'], default='issues')
    # Explicit test allowance for template imports; without it the import stays unavailable, as in production.
    parser.add_argument('--template-call-cap', type=int, default=None)
    asyncio.run(main(parser.parse_args()))
