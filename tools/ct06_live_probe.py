"""CT06 live probe (D100): re-send one stored template request through the real Codex CLI and time its events.

The request and schema come from an attempt saved in an earlier live root, so the prompt is exactly what that run
sent. Raw event lines (model text) stay in the new /private/tmp output folder; the ledger keeps only the block, slot,
effort, durations, token counts and event types with their arrival times.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'services/api/src')]
from tools.ct06_live_import import LEDGER, PROFILE, Ledger, durable  # noqa: E402


def stored_request(root, block, slot):
    from types import SimpleNamespace
    from packages.resume_core.models.template_import import ReferenceTable
    from packages.resume_core.rich_project_store import RichProjectStore
    from packages.resume_core.template_identity import offered_evidence
    from packages.resume_core.templates.replies import proposal_schema
    store = RichProjectStore(root / 'data')
    [project] = [path.name for path in (root / 'data/projects').iterdir() if path.is_dir()]
    workspace = durable(SimpleNamespace(storage=store), project)
    data = workspace.project or workspace.pre_draft
    [operation] = data.template_operations
    tasks = {task.id: task for task in operation.tasks}
    attempt = next(value for value in sorted(operation.attempts, key=lambda value: value.reserved_at)
        if tasks[value.task_id].block_id == block and value.slot == slot and value.request_value)
    if slot not in {'initial', 'primary_repair', 'fallback_repair'}:
        raise SystemExit('only extraction slots are supported')
    value = attempt.request_value
    offered = offered_evidence(value)
    references = ReferenceTable.model_validate(value['references']) if value.get('references') else None
    full = next(item.full_schema for item in data.template_package.blocks if item.id == block)
    return value, proposal_schema(full, None if offered is None else list(offered), references), attempt.model.model


def probe(value, schema, model, effort, out, index):
    from resume_api.cli.experimental_profile import installed_profile
    from resume_api.lifecycle import OperationFiles
    from resume_api.providers.codex_cli import CodexCliProvider
    from resume_api.providers.content import ContentFailure, ContentInput, GenerationPolicy
    from resume_api.providers.dynamic_result import dynamic_result
    from packages.resume_core.template_prompt import model_prompt
    profile = installed_profile(PROFILE)
    provider = CodexCliProvider(profile.executable, experimental_profile=profile)
    timeline, raw, started = [], [], [None]
    original = CodexCliProvider._run

    def run(self, files, args, deadline, cancel, **kwargs):
        # The provider's `exec --help` feature check must see its output unchanged.
        if not args or args[0] != 'exec' or '--help' in args or kwargs.get('on_line') is None:
            return original(self, files, args, deadline, cancel, **kwargs)
        on_line = kwargs['on_line']
        started[0] = time.monotonic()
        def observe(line):
            at = round(time.monotonic() - started[0], 2)
            raw.append(line if isinstance(line, bytes) else str(line).encode())
            try:
                event = json.loads(line)
                item = event.get('item') or {}
                timeline.append([at, event.get('type'), item.get('type')])
            except (ValueError, TypeError, AttributeError):
                timeline.append([at, 'unparsed', None])
            on_line(line)
        return original(self, files, args, deadline, cancel, **{**kwargs, 'on_line': observe})

    CodexCliProvider._run = run
    temp = out / ('operations-%d' % index)
    temp.mkdir(mode=0o700)
    from packages.resume_core.templates.replies import BOOKKEEPING_KEYS
    request = ContentInput(model_prompt(value), dynamic_result(schema, BOOKKEEPING_KEYS),
        GenerationPolicy(model, timeout_seconds=180, allow_repair=False, reasoning_effort=effort), request_value=value)
    began, outcome, code, usage = time.monotonic(), 'completed', None, None
    try:
        files = OperationFiles(temp)
        with files.open():
            result = provider.generate(request, files, threading.Event())
        usage = result.usage
    except ContentFailure as error:
        outcome, code, usage = 'failed', error.code, error.usage
    finally:
        CodexCliProvider._run = original
    (out / ('probe-%d.jsonl' % index)).write_bytes(b'\n'.join(raw))
    total = round(time.monotonic() - began, 2)
    process = round(time.monotonic() - started[0], 2) if started[0] else None
    return {'index': index, 'effort': effort, 'outcome': outcome, 'code': code, 'seconds': total, 'processSeconds': process,
        'inputTokens': getattr(usage, 'input_tokens', None), 'cachedTokens': getattr(usage, 'cached_input_tokens', None),
        'outputTokens': getattr(usage, 'output_tokens', None), 'events': timeline}


def main(args):
    root, out = args.root.resolve(), args.out.resolve()
    if out.parent != Path('/private/tmp') or not out.name.startswith('foldcv-ct06-probe-') or out.exists():
        raise SystemExit('A new /private/tmp/foldcv-ct06-probe-* folder is required')
    value, schema, model = stored_request(root, args.block, args.slot)
    from packages.resume_core.template_prompt import model_prompt
    out.mkdir(mode=0o700)
    ledger = Ledger(LEDGER)
    entry = {'decision': 'D100', 'source': args.label, 'fromRun': args.from_run, 'block': args.block, 'slot': args.slot,
        'model': model, 'promptChars': len(model_prompt(value)), 'startedAt': datetime.now(timezone.utc).isoformat(),
        'folder': out.name, 'calls': []}
    def add(record):
        record.setdefault('probes', []).append({'id': 'PROBE-%02d' % (len(record.get('probes', [])) + 1), **entry})
    ledger_value = ledger.read()
    add(ledger_value)
    probe_id = ledger_value['probes'][-1]['id']
    ledger.write(ledger_value)
    for index, effort in enumerate(args.effort, 1):
        call = probe(value, schema, model, effort, out, index)
        print(json.dumps({key: call[key] for key in call if key != 'events'}, ensure_ascii=False), flush=True)
        with ledger.lock():
            current = ledger.read()
            next(item for item in current['probes'] if item['id'] == probe_id)['calls'].append(call)
            ledger.write(current)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='an earlier live root to take the request from')
    parser.add_argument('--from-run', required=True)
    parser.add_argument('--label', required=True, choices=['CV-A', 'CV-B'])
    parser.add_argument('--block', required=True)
    parser.add_argument('--slot', default='initial')
    parser.add_argument('--effort', nargs='+', default=['medium'])
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args())
