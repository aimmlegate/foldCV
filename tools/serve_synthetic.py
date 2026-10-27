"""Serve the built frontend on synthetic V7 projects with scripted providers, for the T3 preview checks.

The root must be a new /private/tmp/foldcv-* directory. Projects are created through the project repository. The
connection, content provider, assistant runtime and web fetcher are scripted: no model or native process starts.
The one-shot browser secret is written only to root/launch.json (mode 0600); stdout carries the origin and URL.
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

from packages.resume_core.models.agent import AgentWebSource
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.reasoning import ModelReasoning
from packages.resume_core.storage import atomic_write
from packages.resume_core.text_rewrite import PlainTextReply
from resume_api.agent.runtime import RuntimeResult, ScriptedAgentRuntime
from resume_api.app import ProviderSlot, create_app
from resume_api.providers.registry import ProviderRegistry
from resume_api.connection import Metadata, Quota
from resume_api.providers.content import ContentFailure, ContentResult, ReportedUsage
from resume_api.providers.dynamic_result import DynamicResultSpec

NOW = '2026-10-15T18:00:00+00:00'


class ScriptedConnection:
    """A connected account with two models; every model offers the medium effort as its default."""

    def __init__(self):
        self.calls = []

    def inspect(self, _files, _cancel, *, full=True):
        self.calls.append('inspect')
        models = ('synthetic-processing', 'synthetic-assistant')
        return Metadata('synthetic-scripted', models, 'plus', Quota('available', 0),
            reasoning={name: ModelReasoning(supported=['medium'], default='medium') for name in models})

    def login(self, *_args, **_kwargs):
        self.calls.append('scripted_login')

    def detach(self, *_args, **_kwargs):
        self.calls.append('scripted_detach')


class ScriptedClaude(ScriptedConnection):
    """The unlisted Claude provider in preview: two catalog models and no usage read (decision 15)."""
    executable = None

    def inspect(self, _files, _cancel, *, full=True):
        self.calls.append('inspect_claude')
        models = ('claude-sonnet-5-5', 'claude-opus-5-5')
        return Metadata('2.1.308 (Claude Code)', models, 'max', Quota('not_provided'),
            reasoning={name: ModelReasoning(supported=['low', 'medium', 'high'], default='medium') for name in models})


class ScriptedContent:
    """Template import tasks and selected-text rewrites with deterministic replies; other requests are refused."""
    template_adapter = 'synthetic-scripted'

    def __init__(self):
        self.calls = []

    def generate(self, request, _files, _cancel):
        if isinstance(request.result_type, DynamicResultSpec):
            from tests.templates.scripted_template_provider import scripted_template_result
            return scripted_template_result(self, request)
        if request.result_type is not PlainTextReply:
            raise ContentFailure('UNSCRIPTED_PROVIDER_PATH')
        self.calls.append({'kind': 'selected_text_rewrite'})
        selected = request.text.rsplit('Selected text:\n', 1)[1].strip()
        return ContentResult(PlainTextReply(text=selected + ' (revised)'), ReportedUsage(), 'synthetic-scripted',
            request.policy.model, 0, 1)


class StoredWeb:
    """The public page fetcher of the assistant, answered from one stored synthetic page."""

    def __init__(self):
        self.calls = []

    async def fetch(self, request, _cancel):
        url = getattr(request, 'url', request)
        self.calls.append(url)
        text = 'Synthetic stored page. No external retrieval.'
        return AgentWebSource(id='synthetic-stored-page-' + str(len(self.calls)), runId='unbound', requestedUrl=url,
            finalUrl=url, title='Synthetic page', retrievedAt=NOW, contentSha256=hashlib.sha256(text.encode()).hexdigest(),
            text=text, truncated=False, originalBytes=len(text.encode()))


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
    """The published F06 import with Focus entries, a band heading and a bound portfolio link."""
    from tests.templates.test_template_view_adapters import published
    work = root / 'fixture'
    work.mkdir(mode=0o700)
    _fixture, value, originals = await published(work)
    return value, originals


async def generic_workspace(root, name):
    """A published scripted import of one synthetic fixture with the bundled Generic template."""
    from tests.templates.generic_fixtures import generic_import
    work = root / 'fixture'
    work.mkdir(mode=0o700)
    _fixture, _result, value, originals = await generic_import(work, name)
    return value, originals


async def projects(root, employment_shape='issues'):
    """A: joined papers; B: plain papers; C: synthetic employment with two import issues, or the views import, or an
    Generic import. Each keeps its own project identity."""
    from tests.templates.storage_fixtures import joined, workspace as papers
    from tests.templates.test_materialize import issue_workspace
    _workspace, sources = papers()
    if employment_shape == 'views':
        employment, employment_sources = await views_workspace(root)
    elif employment_shape.startswith('generic-'):
        employment, employment_sources = await generic_workspace(root, employment_shape.removeprefix('generic-').upper())
    else:
        employment, employment_sources = issue_workspace()
    return [(joined(), sources), (renamed(papers()[0], 'template-project-b', 'Synthetic papers B'), sources),
        (employment, employment_sources)]


async def assistant_script(value, cancel, emit):
    """A scripted assistant that calls the real run tools over the private MCP listener; no model is started."""
    import httpx
    message = json.loads(value.prompt.split('\n', 1)[1])['message'].lower()
    headers = {'Authorization': 'Bearer ' + value.token, 'Accept': 'application/json, text/event-stream'}
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        counter = [0]

        async def call(name, arguments=None):
            counter[0] += 1
            reply = await client.post(value.url, json={'jsonrpc': '2.0', 'id': counter[0], 'method': 'tools/call',
                'params': {'name': name, 'arguments': arguments or {}}})
            result = reply.json()['result']
            return json.loads(result['content'][0]['text']) if result.get('content') else {}
        await client.post(value.url, json={'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'synthetic', 'version': '1'}}})
        emit('activity.updated', {'itemId': 'read', 'kind': 'summary', 'text': 'Читаю резюме'})
        page = await call('read_resume', {'page': 0})
        first = next(item for item in page['items'] if item['type'] != 'section' and item['containers']
            and item['containers'][0]['text'].strip())
        if 'долго' in message:
            while not cancel.is_set():
                await asyncio.sleep(0.05)
            return RuntimeResult(state='cancelled', error='AGENT_CANCELLED', native_started=True)
        if 'docx' in message:
            await call('export_document', {'format': 'docx'})
            text = 'Файл DOCX готов, ссылка ниже.'
        elif 'перепиши' in message or 'сократи' in message:
            container = first['containers'][0]
            op = {'op': 'set_block_text', 'blockId': first['id'], 'text': container['text'] + ' (короче)'}
            if container['key'] not in {'content', 'caption'}:
                op['cellId'] = container['key']
            result = await call('propose_changes', {'request': {'summary': 'Сократить первый абзац', 'ops': [op]}})
            text = 'Подготовил вариант. Посмотрите и примените.' if 'proposalId' in result else 'Не удалось подготовить вариант.'
        else:
            await call('check_resume')
            await call('publish_findings', {'request': {'findings': [{'severity': 'info',
                'message': 'Уточните формулировку первого абзаца.', 'targets': [{'blockId': first['id']}]}]}})
            text = 'Проверил резюме: одно замечание.'
        emit('message.delta', {'text': text})
        return RuntimeResult(state='completed', text=text, native_started=True, tool_calls=counter[0])


async def main(args):
    root = args.root.resolve()
    if root.parent != Path('/private/tmp') or not root.name.startswith('foldcv-') or root.exists():
        raise ValueError('A new /private/tmp/foldcv-* root is required')
    dist = args.dist.resolve()
    if not (dist / 'index.html').is_file():
        raise ValueError('A built frontend directory is required')
    root.mkdir(mode=0o700)
    data, operations = root / 'data', root / 'operations'
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', args.port))
    listener.listen(128)
    origin = 'http://127.0.0.1:' + str(listener.getsockname()[1])
    secret = secrets.token_urlsafe(32)
    connection, content, web = ScriptedConnection(), ScriptedContent(), StoredWeb()
    runtime = ScriptedAgentRuntime(assistant_script)
    with patch('resume_api.app.ConnectionAdapter', side_effect=AssertionError('native connection')), \
         patch('resume_api.app.CodexCliProvider', side_effect=AssertionError('native content')), \
         patch('resume_api.app.CodexAgentRuntime', side_effect=AssertionError('native agent')):
        app = create_app(origin=origin, secret=secret, temp_root=operations, data_root=data, dist=dist,
            experimental_profile=None, connection_adapter=connection, content_provider=content,
            clock=lambda: datetime.fromisoformat(NOW), agent_runtime=runtime,
            template_import_call_cap=args.template_call_cap,
            provider_registry=ProviderRegistry(frozenset({'claude_cli'})) if args.preview_claude else None,
            provider_slots={'claude_cli': ProviderSlot(ScriptedClaude())} if args.preview_claude else None)
    app.app.state.assistant._fetcher = web
    repository = app.app.state.projects.repository
    if args.template_call_cap is not None:
        # The store's active package for new imports: the synthetic employment subset.
        from packages.resume_core.templates.store import TemplateStore
        from tests.templates.employment_fixtures import employment_package
        TemplateStore(repository.root).activate(employment_package())
    identifiers = []
    for value, sources in await projects(root, args.employment):
        repository.create(value, blobs=[('sources', key, raw, hashlib.sha256(raw).hexdigest()) for key, raw in sources.items()])
        identifiers.append(value.project_id)
    info = {'schemaVersion': 1, 'root': str(root), 'dataRoot': str(data), 'operationRoot': str(operations), 'origin': origin,
        'ownedServicePid': os.getpid(), 'buildDirectory': str(dist), 'projects': identifiers,
        'providers': {'connection': 'ScriptedConnection', 'content': 'ScriptedContent', 'agent': 'ScriptedAgentRuntime',
            'web': 'StoredWeb'}, 'experimentalProfile': None,
        'nativeConstructorGuard': 'all three native factory branches guarded; zero calls', 'serviceState': 'running',
        'sourceSha256': {str(path.relative_to(ROOT)): digest(path) for path in [Path(__file__),
            ROOT / 'tests/templates/storage_fixtures.py', ROOT / 'tests/templates/test_materialize.py',
            ROOT / 'services/api/src/resume_api/app.py']}}

    def diagnostics():
        return {**info, 'callCounts': {'connection': len(connection.calls), 'content': len(content.calls),
            'agent': len(runtime.calls), 'web': len(web.calls), 'nativeStarts': 0},
            'revisions': {identifier: repository.read(identifier).project_revision for identifier in identifiers}}

    @app.app.get('/v1/synthetic/diagnostics')
    async def read_diagnostics():
        return diagnostics()
    # Ahead of the static frontend route, which answers every other GET.
    app.app.router.routes.insert(0, app.app.router.routes.pop())
    url = origin + '/?project=' + identifiers[0]
    launch = root / 'launch.json'
    write_json(launch, {'origin': origin, 'url': url + '#secret=' + secret, 'pid': os.getpid()})
    launch.chmod(0o600)
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
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--employment', choices=['issues', 'views', 'generic-f06', 'generic-f10'], default='issues')
    # Explicit test allowance for template imports; without it the import stays unavailable, as in production.
    parser.add_argument('--template-call-cap', type=int, default=None)
    # Lists the scripted Claude provider next to Codex, as `preview_kinds` does in tests.
    parser.add_argument('--preview-claude', action='store_true')
    asyncio.run(main(parser.parse_args()))
