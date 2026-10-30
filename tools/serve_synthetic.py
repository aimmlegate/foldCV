"""Serve the built frontend on synthetic V7 projects with scripted providers, for the T3 preview checks.

The root must be a new /private/tmp/foldcv-* directory. Projects are created through the project repository. The
connection, content provider, assistant runtime and web fetcher are scripted: no model or native process starts.
The one-shot browser secret is written only to root/launch.json (mode 0600); stdout carries the origin and URL.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import time
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
from resume_api.cli.installation import ClaudeInstallation
from resume_api.connection import Metadata, Quota
from resume_api.projects.errors import ProjectFailure
from resume_api.providers.content import ContentFailure, ContentResult, ReportedUsage
from resume_api.providers.dynamic_result import DynamicResultSpec

NOW = '2026-10-15T18:00:00+00:00'


class ScriptedConnection:
    """A connected account with two models; every model offers low, medium and high, with medium as the default."""

    def __init__(self):
        self.calls = []

    def inspect(self, _files, _cancel, *, full=True):
        self.calls.append('inspect')
        models = ('synthetic-processing', 'synthetic-assistant')
        return Metadata('synthetic-scripted', models, 'plus', Quota('available', 0),
            reasoning={name: ModelReasoning(supported=['low', 'medium', 'high'], default='medium') for name in models})

    def login(self, *_args, **_kwargs):
        self.calls.append('scripted_login')

    def detach(self, *_args, **_kwargs):
        self.calls.append('scripted_detach')


class ScriptedClaude(ScriptedConnection):
    """The unlisted Claude provider in preview: signed out until a code is pasted, then two catalog models and no
    usage read (decision 15)."""
    executable = None

    def __init__(self, installation=None):
        super().__init__()
        self.signed_in = False
        # Set with --claude-missing: no CLI until the scripted install puts one there.
        self.installation = installation

    def login(self, _files, cancel, code=None):
        self.calls.append('scripted_login')
        while not cancel.wait(0.05):
            if code is not None and code():
                self.signed_in = True
                return

    def inspect(self, _files, _cancel, *, full=True):
        self.calls.append('inspect_claude')
        from resume_api.connection import ConnectionFailure
        if self.installation is not None and not self.installation.executable.is_file():
            raise ConnectionFailure('CLI_MISSING')
        if full and not self.signed_in:
            raise ConnectionFailure('LOGIN_REQUIRED', '2.1.308 (Claude Code)')
        models = ('claude-sonnet-5-5', 'claude-opus-5-5')
        return Metadata('2.1.308 (Claude Code)', models, 'max', Quota('not_provided'),
            reasoning={name: ModelReasoning(supported=['low', 'medium', 'high'], default='medium') for name in models})


class ScriptedProfile:
    """A private directory for the scripted Claude slot's profile lock; it marks the slot as native mode."""

    def __init__(self, root, executable=Path(sys.executable)):
        self.root, self.executable = root, executable

    def prepare(self):
        self.root.mkdir(mode=0o700, exist_ok=True)


class ScriptedInstallation(ClaudeInstallation):
    """The managed Claude install with its real staging and checks; the download is a local stub paced for the screen."""
    STUB = b'#!/bin/sh\nexit 1\n' * 65536

    @property
    def size(self):
        return len(self.STUB)

    @property
    def sha256(self):
        return hashlib.sha256(self.STUB).hexdigest()

    def download(self, _files, target):
        step = len(self.STUB) // 20
        with target.open('wb') as output:
            for start in range(0, len(self.STUB), step):
                self.check_cancel()
                time.sleep(0.2)
                output.write(self.STUB[start:start + step])
                output.flush()
                self.update(downloadedBytes=target.stat().st_size)


def scripted_claude_slot(root, missing, runtime):
    """The assistant runs the same scripted runtime with Claude active."""
    if not missing:
        return ProviderSlot(ScriptedClaude(), profile=ScriptedProfile(root / 'claude-profile'), runtime=runtime)
    installation = ScriptedInstallation(root / 'claude-runtime')

    def rebind(slot, executable):
        return ProviderSlot(slot.connection, None, ScriptedProfile(slot.profile.root, executable), installation,
                            runtime, rebind=rebind)
    return ProviderSlot(ScriptedClaude(installation), None,
                        ScriptedProfile(root / 'claude-profile', installation.executable), installation, runtime,
                        rebind=rebind)


class ScriptedContent:
    """Template import tasks and selected-text rewrites with deterministic replies; other requests are refused."""
    template_adapter = 'synthetic-scripted'

    def __init__(self, delay=0.0):
        self.calls = []
        self.delay = delay

    def generate(self, request, _files, cancel):
        if isinstance(request.result_type, DynamicResultSpec):
            from tests.templates.scripted_template_provider import scripted_template_result
            # --template-delay keeps each call open long enough to watch the import screen; Stop ends the wait.
            if self.delay and cancel is not None:
                cancel.wait(self.delay)
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


async def generic_workspace(root, name, template=None):
    """A published scripted import of one synthetic fixture with a bundled template, the Generic one by default."""
    from packages.resume_core.templates.compiler import compile_template
    from packages.resume_core.templates.store import BUNDLED_TEMPLATES
    from tests.templates.generic_fixtures import generic_import
    work = root / 'fixture'
    work.mkdir(mode=0o700)
    package = compile_template(BUNDLED_TEMPLATES[template]) if template else None
    _fixture, _result, value, originals = await generic_import(work, name, package=package)
    return value, originals


async def projects(root, employment_shape='issues', template=None):
    """A: joined papers; B: plain papers; C: synthetic employment with two import issues, or the views import, or an
    import through a bundled template. Each keeps its own project identity."""
    from tests.templates.storage_fixtures import joined, workspace as papers
    from tests.templates.test_materialize import issue_workspace
    _workspace, sources = papers()
    if employment_shape == 'views':
        employment, employment_sources = await views_workspace(root)
    elif employment_shape.startswith('generic-'):
        employment, employment_sources = await generic_workspace(root, employment_shape.removeprefix('generic-').upper(), template)
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


LIVE_PROFILE = Path.home() / 'Library/Application Support/FoldCV/cli-experiment'
LEDGER = ROOT / 'docs/gui/handoffs/SIMPLIFY/logs/sr08-live-ledger.jsonl'
LIVE_LIMIT = 20
OUTCOMES = ROOT / 'docs/gui/handoffs/SIMPLIFY/logs/sr08-live-outcomes.jsonl'


class LiveBudget:
    """Counts native assistant starts in a ledger kept across restarts and refuses any start past the limit."""
    native = True

    def __init__(self, runtime_for, ledger, limit):
        self.runtime_for, self.ledger, self.limit = runtime_for, ledger, limit
        self.calls = []

    def used(self):
        return len(self.ledger.read_text().splitlines()) if self.ledger.is_file() else 0

    async def run(self, value, cancel, emit):
        from resume_api.agent.runtime import RuntimeResult
        if self.used() >= self.limit:
            return RuntimeResult(state='failed', error='AGENT_QUOTA')
        # Charged before the start, so an unknown outcome still counts.
        with self.ledger.open('a') as handle:
            handle.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'model': value.model,
                'message': json.loads(value.prompt.split('\n', 1)[1])['message'][:200]}, ensure_ascii=False) + '\n')
        self.calls.append(value.model)
        result = await self.runtime_for(value.model).run(value, cancel, emit)
        with OUTCOMES.open('a') as handle:
            handle.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'model': value.model, 'state': result.state,
                'error': result.error, 'toolCalls': result.tool_calls, 'text': (result.text or '')[:600]}, ensure_ascii=False) + '\n')
        return result


def install_live_limits(app, ledger, limit):
    """Every assistant start goes through one budget, whichever provider runs the model. The budget does not count
    rewrites, so they are refused here, before a native process starts."""
    assistant = app.app.state.assistant
    budget = LiveBudget(assistant.runtime_for, ledger, limit)
    assistant.runtime = budget
    assistant.runtime_for = lambda model: None if budget.runtime_for(model) is None else budget

    async def refused(*_args):
        raise ProjectFailure('CONNECTION_REQUIRED', 409)
    app.app.state.projects.rewrite_text = refused
    return budget


async def main(args):
    if args.live_assistant and args.template_call_cap is not None:
        raise ValueError('--template-call-cap is refused with --live-assistant: the live budget does not count imports')
    root = args.root.resolve()
    # --reopen restarts on a root this tool created (isolation.json present), keeping its store.
    if root.parent != Path('/private/tmp') or not root.name.startswith('foldcv-') or \
            (not (root / 'isolation.json').is_file() if args.reopen else root.exists()):
        raise ValueError('An existing root of this tool is required' if args.reopen else 'A new /private/tmp/foldcv-* root is required')
    dist = args.dist.resolve()
    if not (dist / 'index.html').is_file():
        raise ValueError('A built frontend directory is required')
    if not args.reopen:
        root.mkdir(mode=0o700)
    data, operations = root / 'data', root / 'operations'
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', args.port))
    listener.listen(128)
    origin = 'http://127.0.0.1:' + str(listener.getsockname()[1])
    secret = secrets.token_urlsafe(32)
    connection, content, web = ScriptedConnection(), ScriptedContent(args.template_delay), StoredWeb()
    runtime = ScriptedAgentRuntime(assistant_script)
    if args.live_assistant:
        # The user's existing Codex sign-in is used in place (allowed 2026-10-27); projects stay in this temp root.
        from resume_api.cli.experimental_profile import installed_profile
        profile = installed_profile(LIVE_PROFILE)
        app = create_app(origin=origin, secret=secret, temp_root=operations, data_root=data, dist=dist,
            experimental_profile=profile)
        runtime = install_live_limits(app, LEDGER, LIVE_LIMIT)
    else:
        with patch('resume_api.app.ConnectionAdapter', side_effect=AssertionError('native connection')), \
             patch('resume_api.app.CodexCliProvider', side_effect=AssertionError('native content')), \
             patch('resume_api.app.CodexAgentRuntime', side_effect=AssertionError('native agent')):
            app = create_app(origin=origin, secret=secret, temp_root=operations, data_root=data, dist=dist,
                experimental_profile=None, connection_adapter=connection, content_provider=content,
                clock=lambda: datetime.fromisoformat(NOW), agent_runtime=runtime,
                template_import_call_cap=args.template_call_cap,
                provider_slots={'claude_cli': scripted_claude_slot(root, args.claude_missing, runtime)})
        app.app.state.assistant._fetcher = web
    repository = app.app.state.projects.repository
    if args.template_call_cap is not None and not args.reopen:
        # The store's active package for new imports: the synthetic employment subset.
        from packages.resume_core.templates.store import TemplateStore
        from tests.templates.employment_fixtures import employment_package
        TemplateStore(repository.root).activate(employment_package())
    identifiers = json.loads((root / 'isolation.json').read_text())['projects'] if args.reopen else []
    # A chosen template imports the F10 employment fixture unless another import is named, and opens first.
    employment = args.employment or ('generic-f10' if args.template else 'issues')
    for value, sources in [] if args.reopen else await projects(root, employment, args.template):
        repository.create(value, blobs=[('sources', key, raw, hashlib.sha256(raw).hexdigest()) for key, raw in sources.items()])
        identifiers.append(value.project_id)
    info = {'schemaVersion': 1, 'root': str(root), 'dataRoot': str(data), 'operationRoot': str(operations), 'origin': origin,
        'ownedServicePid': os.getpid(), 'buildDirectory': str(dist), 'projects': identifiers,
        'providers': {'connection': 'native' if args.live_assistant else 'ScriptedConnection',
            'content': 'refused' if args.live_assistant else 'ScriptedContent',
            'agent': 'CodexAgentRuntime (LiveBudget)' if args.live_assistant else 'ScriptedAgentRuntime',
            'web': 'PublicFetcher' if args.live_assistant else 'StoredWeb'},
        'experimentalProfile': 'cli-experiment (in place)' if args.live_assistant else None,
        'nativeConstructorGuard': 'not guarded: live assistant' if args.live_assistant else 'all three native factory branches guarded; zero calls',
        'serviceState': 'running',
        'sourceSha256': {str(path.relative_to(ROOT)): digest(path) for path in [Path(__file__),
            ROOT / 'tests/templates/storage_fixtures.py', ROOT / 'tests/templates/test_materialize.py',
            ROOT / 'services/api/src/resume_api/app.py']}}

    def diagnostics():
        return {**info, 'callCounts': {'connection': len(connection.calls), 'content': len(content.calls),
            'agent': len(runtime.calls), 'web': len(web.calls),
            'nativeStarts': len(runtime.calls) if args.live_assistant else 0},
            'revisions': {identifier: repository.read(identifier).project_revision for identifier in identifiers}}

    @app.app.get('/v1/synthetic/diagnostics')
    async def read_diagnostics():
        return diagnostics()
    # Ahead of the static frontend route, which answers every other GET.
    app.app.router.routes.insert(0, app.app.router.routes.pop())
    url = origin + '/?project=' + identifiers[-1 if args.template else 0]
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
    parser.add_argument('--employment', choices=['issues', 'views', 'generic-f06', 'generic-f10'], default=None)
    # The bundled template of the generic-* imports; with it the default import is generic-f10.
    parser.add_argument('--template', choices=['generic-two-column', 'generic-one-column'], default=None)
    # Explicit test allowance for template imports; without it the import stays unavailable, as in production.
    parser.add_argument('--template-call-cap', type=int, default=None)
    # Claude starts without a CLI and Settings installs a stub through the managed installer.
    parser.add_argument('--claude-missing', action='store_true')
    # Seconds each scripted template call waits before its reply, to watch a running import in the preview.
    parser.add_argument('--template-delay', type=float, default=0.0)
    # Native assistant runs on the user's Codex sign-in, charged to the SR08 ledger (at most LIVE_LIMIT starts).
    parser.add_argument('--live-assistant', action='store_true')
    parser.add_argument('--reopen', action='store_true')
    asyncio.run(main(parser.parse_args()))
