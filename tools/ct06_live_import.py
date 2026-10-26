"""CT06 live import (D097, D100): one full Generic import of one CV through the real Codex CLI in an isolated store.

A run is charged to the ledger before it starts (D100: no fixed count, but no new run after three failed runs in a
row); every `codex exec` inside the run is recorded with its duration, outcome and event arrival times. The CLI profile is the existing FoldCV sign-in, used in place and never
copied. Sources, model replies, the project and the DOCX stay in the new /private/tmp root; the ledger in the
repository keeps only models, timings, counts and codes, never resume text or names.
"""

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'services/api/src')]
LEDGER = ROOT / 'docs/gui/handoffs/CONFIGURABLE-TEMPLATES/ct06-live-ledger.json'
PROFILE = Path.home() / 'Library/Application Support/FoldCV/cli-experiment'
MODELS = {'gpt-6.1-sol', 'gpt-6-luna'}
TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}
FAILURES_IN_A_ROW = 3


def now():
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    """Runs in separate processes share the ledger, so every read-modify-write holds a file lock (LIVE-09/10 ran
    together)."""

    def __init__(self, path):
        self.path, self.thread_lock = path, threading.Lock()

    @contextmanager
    def lock(self):
        import fcntl
        with self.thread_lock, open('/private/tmp/foldcv-ct06-ledger.lock', 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def read(self):
        if not self.path.exists():
            return {'schemaVersion': 1, 'decision': 'D097', 'unit': 'one full template import run (all of its model dispatches)',
                'runs': []}
        return json.loads(self.path.read_text())

    def write(self, ledger):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + '\n')
        os.replace(temporary, self.path)

    def charge(self, model, label, source_sha256, root, concurrency=1):
        with self.lock():
            ledger = self.read()
            # D100: after three failed runs in a row the work stops and is reported instead of trying again.
            recent = [run['status'] for run in ledger['runs'] if run.get('decision') in {'D100', 'D101', 'CT10'}][-FAILURES_IN_A_ROW:]
            if len(recent) == FAILURES_IN_A_ROW and 'saved' not in recent:
                raise SystemExit('three failed runs in a row: stop and report')
            # D101 (2026-10-25): three full imports; CT10 parallel runs have their own allowance. Each run is charged
            # here before any model call.
            decision, key = ('CT10', 'ct10') if concurrency > 1 else ('D101', 'd101')
            budget = ledger.get(key)
            if budget is None and key == 'ct10':
                raise SystemExit('a parallel run needs the ct10 allowance in the ledger')
            if budget is not None:
                if budget['runsSpent'] >= budget['runCap']:
                    raise SystemExit('%s run cap reached: %d of %d' % (decision, budget['runsSpent'], budget['runCap']))
                budget['runsSpent'] += 1
            else:
                decision = 'D100'
            run = {'id': 'LIVE-%02d' % (len(ledger['runs']) + 1), 'decision': decision, 'model': model, 'source': label,
                'sourceSha256': source_sha256, 'root': root.name, 'startedAt': now(), 'status': 'started', 'dispatches': [],
                **({'concurrency': concurrency} if concurrency > 1 else {})}
            ledger['runs'].append(run)
            self.write(ledger)
            return run['id']

    def update(self, run_id, change):
        with self.lock():
            ledger = self.read()
            change(next(run for run in ledger['runs'] if run['id'] == run_id))
            self.write(ledger)


def record_dispatches(ledger, run_id, evidence):
    from resume_api.providers.codex_cli import CodexCliProvider
    original = CodexCliProvider._run
    counter = iter(range(1, 10_000))

    def run(provider, files, args, deadline, cancel, **kwargs):
        if not args or args[0] != 'exec' or '--help' in args:
            return original(provider, files, args, deadline, cancel, **kwargs)
        index, started, wall, events = next(counter), time.monotonic(), now(), []
        on_line = kwargs.get('on_line')
        def observe(line):
            # Event types and arrival times only; a stall shows as turn.started with nothing after it.
            try:
                event = json.loads(line)
                events.append([round(time.monotonic() - started, 2), event.get('type'), (event.get('item') or {}).get('type')])
            except (ValueError, TypeError, AttributeError):
                events.append([round(time.monotonic() - started, 2), 'unparsed', None])
            on_line(line)
        if on_line is not None:
            kwargs = {**kwargs, 'on_line': observe}
        def finish(code, stdout=None):
            elapsed = round(time.monotonic() - started, 2)
            ledger.update(run_id, lambda record: record['dispatches'].append(
                {'index': index, 'startedAt': wall, 'elapsedSeconds': elapsed, 'code': code,
                    'events': [event for event in events if event[2] != 'error']}))
            if stdout is not None:
                (evidence / ('dispatch-%03d.stdout' % index)).write_bytes(stdout)
        try:
            result = original(provider, files, args, deadline, cancel, **kwargs)
        except Exception as error:
            finish(getattr(error, 'code', type(error).__name__))
            raise
        finish(None, result[0])
        return result

    CodexCliProvider._run = run


async def main(args):
    import httpx
    from packages.resume_core.storage import atomic_write
    from packages.resume_core.template_export import snapshot_identity
    from packages.resume_core.templates.store import TemplateStore
    from resume_api.app import create_app
    from resume_api.cli.experimental_profile import installed_profile
    from tests.templates.generic_fixtures import generic_package
    if args.source is None or args.label is None:
        raise SystemExit('--model, --source and --label are required for a run')
    if args.model not in MODELS:
        raise SystemExit('D097 and D100 cover ' + ', '.join(sorted(MODELS)))
    root = args.root.resolve()
    if root.parent != Path('/private/tmp') or not root.name.startswith('foldcv-ct06-live-') or root.exists():
        raise SystemExit('A new /private/tmp/foldcv-ct06-live-* root is required')
    raw = args.source.read_bytes()
    root.mkdir(mode=0o700)
    data, evidence, dist = root / 'data', root / 'evidence', root / 'dist'
    for folder in (data, evidence, dist):
        folder.mkdir(mode=0o700)
    (dist / 'index.html').write_text('live import run')
    atomic_write(data / 'preferences.json', json.dumps({'schemaVersion': 1, 'selectedModel': args.model,
        'selectedImportModel': args.model, 'automaticAnalysis': False, 'theme': 'system'}).encode())
    ledger = Ledger(LEDGER)
    run_id = ledger.charge(args.model, args.label, hashlib.sha256(raw).hexdigest(), root, args.concurrency)
    record_dispatches(ledger, run_id, evidence)
    origin, secret = 'http://127.0.0.1:39301', secrets.token_urlsafe(32)
    wrapped = create_app(origin=origin, secret=secret, temp_root=root / 'operations', dist=dist,
        experimental_profile=installed_profile(PROFILE), data_root=data, background_enabled=True,
        template_import_call_cap=args.call_cap, template_import_concurrency=args.concurrency)
    app, service, jobs = wrapped.app, wrapped.app.state.rich_projects, wrapped.app.state.jobs
    TemplateStore(service.storage.root).activate(generic_package())
    timings, outcome = {}, None
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url=origin,
                    headers={'Origin': origin}, timeout=600) as client:
                assert (await client.post('/v1/session/exchange', json={'secret': secret})).status_code == 200
                assert (await client.post('/v1/host/status', json={})).status_code == 200
                selected = await client.post('/v1/host/select', json={'model': args.model})
                assert selected.status_code == 200, selected.text
                started = time.monotonic()
                created = await client.post('/v1/rich/projects/template-input',
                    files={'file': (args.label.lower() + '.pdf', raw, 'application/pdf')})
                assert created.status_code == 201, created.text
                project = created.json()['workspace']['projectId']
                timings['uploadSeconds'] = round(time.monotonic() - started, 2)
                started = time.monotonic()
                job = (await client.post(f'/v1/rich/projects/{project}/template-import',
                    json={'clientRequestId': 'live-1', 'allowTextRewrite': not args.keep_wording})).json()
                # A failed job has no outcome (LIVE-04 polled one until stopped by hand); a completed job attaches its
                # outcome just after it ends (LIVE-05 left before it), so only that case waits a little longer.
                ended = None
                while job.get('templateOutcome') is None:
                    if job.get('execution') in TERMINAL - {'completed'}:
                        break
                    if job.get('execution') == 'completed':
                        ended = ended or time.monotonic()
                        if time.monotonic() - ended > 120:
                            break
                    await asyncio.sleep(2)
                    job = (await client.post(f'/v1/rich/projects/{project}/jobs/{job["id"]}/read', json={})).json()
                timings['importSeconds'] = round(time.monotonic() - started, 2)
                outcome = job.get('templateOutcome') or {'state': 'job_' + str(job.get('execution')),
                    'errorCode': (job.get('error') or {}).get('code')}
                workspace = service.storage.read_committed(project)[0]
                if outcome and outcome['state'] == 'saved':
                    started = time.monotonic()
                    exported = await client.post(f'/v1/rich/projects/{project}/export',
                        json={'schemaVersion': 1, 'snapshot': snapshot_identity(workspace).model_dump(mode='json', by_alias=True)})
                    timings['exportSeconds'] = round(time.monotonic() - started, 2)
                    if exported.status_code == 200:
                        atomic_write(root / 'output.docx', exported.content)
                    timings['exportStatus'] = exported.status_code
                summary = summarize(durable(service, project), service.storage.projects / project / 'workspace.json')
    finally:
        await jobs.shutdown()
        service.request_shutdown()
        await service.shutdown()
    result = {'run': run_id, 'model': args.model, 'source': args.label, 'callCap': args.call_cap, 'concurrency': args.concurrency,
        'rewrite': not args.keep_wording, 'outcome': outcome, 'timings': timings, **summary}
    atomic_write(root / 'result.json', json.dumps(result, ensure_ascii=False, indent=1).encode())
    def settle(record):
        model_seconds = round(sum(item['elapsedSeconds'] for item in record['dispatches']), 1)
        # Parallel calls overlap (CT10): the wall time with at least one call in flight is what the import waited for.
        busy = busy_seconds(record['dispatches'])
        record.update(status=(outcome or {}).get('state', 'no_outcome'), finishedAt=now(), timings=timings,
            modelSeconds=model_seconds, modelWallSeconds=busy, localSeconds=round(timings.get('importSeconds', 0) - busy, 1),
            counts=summary['counts'], workspaceBytes=summary['workspaceBytes'], errorCodes=summary['errorCodes'],
            calls=summary['calls'])
    ledger.update(run_id, settle)
    print(json.dumps({key: result[key] for key in ('run', 'model', 'source', 'timings', 'counts', 'errorCodes')}, ensure_ascii=False))


async def finish(args):
    """Summarize and export a run whose tool stopped early, from its own root and without any model call."""
    import httpx
    from packages.resume_core.storage import atomic_write
    from packages.resume_core.template_export import snapshot_identity
    from resume_api.app import create_app
    root = args.root.resolve()
    if root.parent != Path('/private/tmp') or not root.name.startswith('foldcv-ct06-live-') or not root.exists():
        raise SystemExit('an existing /private/tmp/foldcv-ct06-live-* root is required')
    ledger = Ledger(LEDGER)
    [run] = [run for run in ledger.read()['runs'] if run['root'] == root.name]
    origin, secret = 'http://127.0.0.1:39301', secrets.token_urlsafe(32)
    wrapped = create_app(origin=origin, secret=secret, temp_root=root / 'operations', dist=root / 'dist',
        data_root=root / 'data', background_enabled=True, template_import_call_cap=args.call_cap)
    app, service, jobs = wrapped.app, wrapped.app.state.rich_projects, wrapped.app.state.jobs
    [project] = [path.name for path in (root / 'data/projects').iterdir() if path.is_dir()]
    timings = dict(run.get('timings') or {})
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url=origin,
                    headers={'Origin': origin}, timeout=600) as client:
                assert (await client.post('/v1/session/exchange', json={'secret': secret})).status_code == 200
                workspace = service.storage.read_committed(project)[0]
                [operation] = (workspace.project or workspace.pre_draft).template_operations
                outcome = operation.publication.state if operation.publication is not None else 'no_outcome'
                if workspace.project is not None:
                    started = time.monotonic()
                    exported = await client.post(f'/v1/rich/projects/{project}/export',
                        json={'schemaVersion': 1, 'snapshot': snapshot_identity(workspace).model_dump(mode='json', by_alias=True)})
                    timings['exportSeconds'] = round(time.monotonic() - started, 2)
                    timings['exportStatus'] = exported.status_code
                    if exported.status_code == 200:
                        atomic_write(root / 'output.docx', exported.content)
                    else:
                        timings['exportError'] = (exported.json().get('code') if exported.headers.get('content-type', '').startswith(
                            'application/json') else None)
                summary = summarize(durable(service, project), service.storage.projects / project / 'workspace.json')
    finally:
        await jobs.shutdown()
        service.request_shutdown()
        await service.shutdown()
    ledger.update(run['id'], lambda record: record.update(status=outcome, timings=timings, counts=summary['counts'],
        workspaceBytes=summary['workspaceBytes'], errorCodes=summary['errorCodes'], calls=summary['calls'],
        finishedLocally=now()))
    print(json.dumps({'run': run['id'], 'status': outcome, 'timings': timings, 'counts': summary['counts']}, ensure_ascii=False))


def durable(service, project):
    """The saved project with the sidecar steps of an import that did not publish (S7e)."""
    from types import SimpleNamespace
    from resume_api.importer.template_sidecar import OperationSidecar
    workspace = service.storage.read_committed(project)[0]
    sidecar, data = OperationSidecar(SimpleNamespace(canonical=service.storage)), workspace.project or workspace.pre_draft
    data.template_operations = [sidecar.overlay(project, workspace.project_revision, value)[0] for value in data.template_operations]
    return workspace


def seconds(start, end):
    if not start or not end:
        return None
    return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 2)


def busy_seconds(dispatches):
    """The length of the union of the dispatch intervals: sequential calls give their sum, parallel ones less."""
    spans = sorted((datetime.fromisoformat(item['startedAt']).timestamp(),
        datetime.fromisoformat(item['startedAt']).timestamp() + item['elapsedSeconds']) for item in dispatches)
    total, end = 0.0, None
    for start, stop in spans:
        if end is None or start > end:
            total, end = total + stop - start, stop
        elif stop > end:
            total, end = total + stop - end, stop
    return round(total, 1)


def summarize(workspace, path):
    """Counts, codes and one row per model call (block ids and numbers only, never resume text)."""
    from packages.resume_core.template_prompt import model_prompt
    owner = workspace.project or workspace.pre_draft
    [operation] = owner.template_operations
    blocks = {task.id: task.block_id for task in operation.tasks}
    slots, codes = {}, {}
    for attempt in operation.attempts:
        slots[attempt.slot] = slots.get(attempt.slot, 0) + 1
        if attempt.error_code:
            codes[attempt.error_code] = codes.get(attempt.error_code, 0) + 1
    # A review attempt's request is its review input record (stored once since S8).
    reviews = {record.attempt_id: record.value.model_dump(mode='json', by_alias=True) for record in operation.review_inputs}
    def prompt_chars(attempt):
        request = attempt.request_value or reviews.get(attempt.id)
        return len(model_prompt(request)) if request else None
    calls = [{'slot': attempt.slot, 'block': blocks[attempt.task_id], 'outcome': attempt.outcome, 'code': attempt.error_code,
        'seconds': seconds(attempt.dispatched_at, attempt.returned_at), 'inputTokens': attempt.usage.input_tokens,
        'cachedTokens': attempt.usage.cached_input_tokens, 'outputTokens': attempt.usage.output_tokens,
        'promptChars': prompt_chars(attempt)} for attempt in sorted(operation.attempts, key=lambda value: value.reserved_at)]
    tasks = {}
    for task in operation.tasks:
        tasks[task.state] = tasks.get(task.state, 0) + 1
    # A refused first reply (by the transport or the coordinator) and whether its one repair was accepted.
    rejected = {attempt.task_id for attempt in operation.attempts if attempt.slot == 'initial' and attempt.outcome == 'invalid_payload'}
    repaired = {task.id for task in operation.tasks if task.id in rejected and task.state == 'accepted'}
    project = workspace.project
    return {'workspaceBytes': path.stat().st_size, 'errorCodes': codes, 'calls': calls,
        'counts': {'calls': len(operation.attempts), 'slots': slots, 'tasks': tasks, 'rejectedInitial': len(rejected),
            'repaired': len(repaired), 'fallbacks': tasks.get('source_fallback', 0),
            'issues': len(project.import_issues) if project else None,
            'records': len(project.facts.records) if project else None,
            'blocks': sum(1 for _ in project.document.blocks()) if project else None}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--model')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--label', choices=['CV-A', 'CV-B', 'CV-C'])
    parser.add_argument('--call-cap', type=int, default=60)
    parser.add_argument('--concurrency', type=int, default=1, help='independent blocks in flight at once (CT10)')
    parser.add_argument('--keep-wording', action='store_true')
    parser.add_argument('--finish', action='store_true', help='summarize and export an existing root; no model call')
    arguments = parser.parse_args()
    asyncio.run(finish(arguments) if arguments.finish else main(arguments))
