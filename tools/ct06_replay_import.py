"""CT06 replay: rerun a live import locally with its recorded first replies, to measure and profile local time.

No model is called. Each extraction answers with the first reply recorded for its block in an earlier live root;
every review answers that all checks hold. Work the pipeline sends to threads runs inline, so one profiler sees all
of it. The source, project and profile stay in the new /private/tmp output folder; only timings are printed.
"""

import argparse
import asyncio
import cProfile
import json
from pathlib import Path
import pstats
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'services/api/src')]


def recorded_replies(root):
    from types import SimpleNamespace
    from packages.resume_core.rich_project_store import RichProjectStore
    from tools.ct06_live_import import durable
    store = RichProjectStore(root / 'data')
    [project] = [path.name for path in (root / 'data/projects').iterdir() if path.is_dir()]
    workspace = durable(SimpleNamespace(storage=store), project)
    [operation] = (workspace.project or workspace.pre_draft).template_operations
    blocks = {task.id: task.block_id for task in operation.tasks}
    replies = {}
    for attempt in sorted(operation.attempts, key=lambda value: value.reserved_at):
        if attempt.slot == 'initial' and attempt.raw_return is not None:
            replies.setdefault(blocks[attempt.task_id], attempt.raw_return)
    return replies


class ReplayProvider:
    template_adapter = 'scripted'

    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def generate(self, request, _files, _cancel):
        from resume_api.providers.content import ContentFailure, ContentResult, ContentTransportReturn, ReportedUsage
        value = request.request_value
        review = value is None or 'targets' in value
        block = None if review else value['declaration']['id']
        raw = json.dumps({'payload': {'results': []}}) if review else self.replies.get(block, json.dumps({'payload': None}))
        self.calls.append(('review' if review else block))
        usage, witness = ReportedUsage(10, 0, 4, True), {'transport': 'replay', 'turnId': str(len(self.calls))}
        request.on_return(ContentTransportReturn(raw, 'completed', None, 1, usage, True, witness, 'medium'))
        try:
            decoded = request.result_type.decode_value(json.loads(raw))
        except ValueError:
            raise ContentFailure('INVALID_RESULT', logical_attempts=1, usage=usage, cleanup_verified=True,
                dispatch_witness=witness, raw_return=raw) from None
        return ContentResult(decoded, usage, 'replay', request.policy.model, 0, 1, cleanup_verified=True,
            dispatch_witness=witness, reasoning_effort='medium', raw_return=raw)


async def run(args, replies):
    import httpx
    from packages.resume_core.templates.store import TemplateStore
    from resume_api.agent.runtime import ScriptedAgentRuntime
    from resume_api.app import create_app
    from tests.templates.generic_fixtures import generic_package
    from tests.templates.test_template_import_app import CatalogAdapter, Tools, refuse_execution
    out = args.out
    data, dist = out / 'data', out / 'dist'
    for folder in (data, dist):
        folder.mkdir(mode=0o700)
    (dist / 'index.html').write_text('replay')
    origin, secret = 'http://127.0.0.1:39302', secrets.token_urlsafe(32)
    provider = ReplayProvider(replies)
    wrapped = create_app(origin=origin, secret=secret, temp_root=out / 'operations', dist=dist, data_root=data,
        connection_adapter=CatalogAdapter(), agent_runtime=ScriptedAgentRuntime(None), agent_tools=Tools(), gui_provider=provider,
        background_enabled=True, background_factory=refuse_execution, template_import_call_cap=60)
    app, service, jobs = wrapped.app, wrapped.app.state.rich_projects, wrapped.app.state.jobs
    TemplateStore(service.storage.root).activate(generic_package())
    timings = {}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url=origin,
                headers={'Origin': origin}, timeout=600) as client:
            assert (await client.post('/v1/session/exchange', json={'secret': secret})).status_code == 200
            assert (await client.post('/v1/host/status', json={})).status_code == 200
            assert (await client.post('/v1/host/select', json={'model': 'processing-model'})).status_code == 200
            created = await client.post('/v1/rich/projects/template-input',
                files={'file': ('replay.pdf', args.source.read_bytes(), 'application/pdf')})
            assert created.status_code == 201, created.text
            project = created.json()['workspace']['projectId']
            started = time.monotonic()
            job = (await client.post(f'/v1/rich/projects/{project}/template-import',
                json={'clientRequestId': 'replay', 'allowTextRewrite': True})).json()
            while job.get('templateOutcome') is None and job.get('execution') not in {'failed', 'cancelled', 'interrupted'}:
                await asyncio.sleep(0.2)
                job = (await client.post(f'/v1/rich/projects/{project}/jobs/{job["id"]}/read', json={})).json()
            timings['importSeconds'] = round(time.monotonic() - started, 2)
            timings['outcome'] = (job.get('templateOutcome') or {}).get('state')
            path = service.storage.projects / project / 'workspace.json'
            timings['workspaceBytes'] = path.stat().st_size if path.exists() else None
    await jobs.shutdown()
    service.request_shutdown()
    await service.shutdown()
    timings['calls'] = len(provider.calls)
    return timings


def main(args):
    out = args.out.resolve()
    if out.parent != Path('/private/tmp') or not out.name.startswith('foldcv-ct06-replay-') or out.exists():
        raise SystemExit('A new /private/tmp/foldcv-ct06-replay-* folder is required')
    out.mkdir(mode=0o700)
    args.out = out
    replies = recorded_replies(args.root.resolve())
    if args.inline:
        # Thread work runs inline, so the profiler sees it; the timing then includes no thread overlap.
        async def inline(function, /, *values, **named):
            return function(*values, **named)
        asyncio.to_thread = inline
    profile = cProfile.Profile() if args.profile else None
    if profile:
        profile.enable()
    timings = asyncio.run(run(args, replies))
    if profile:
        profile.disable()
        profile.dump_stats(out / 'replay.prof')
        stats = pstats.Stats(str(out / 'replay.prof'))
        stats.sort_stats('cumulative').print_stats(args.top)
    print(json.dumps(timings))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='a live root whose first replies are replayed')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--inline', action='store_true')
    parser.add_argument('--top', type=int, default=60)
    main(parser.parse_args())
