"""CT06 live probe (D100/D101): re-send one stored template request through the real Codex CLI and time its events.

The request and schema come from an attempt saved in an earlier live root, so the prompt is exactly what that run sent,
unless a variant replaces the reply protocol text (--protocol-rules) or keeps the full schema shape (--schema full).
The fresh reply can be checked offline the way the import would check it (--validate): schema, completion and binding
for an extraction, decode and receipt for a review. Several sends at once (--concurrent) probe the CLI profile for
parallel sessions. Raw event lines (model text) stay in the new /private/tmp output folder; the ledger keeps the block,
slot, effort, variant, durations, token counts, event types and the validation class. Calls under D101 are charged to
its probe cap before dispatch, whatever their outcome.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'services/api/src')]
from tools.ct06_live_import import LEDGER, PROFILE, Ledger, durable  # noqa: E402

EXTRACTION = {'initial', 'primary_repair', 'fallback_repair'}
REVIEW = {'review', 'replacement_review'}
# Concurrent probes share one class attribute patch; each wrapper only observes its own provider instance's lines.
PATCH_LOCK = threading.Lock()


def stored_request(root, block, slot, schema_mode='content', rules=None, quotes=False):
    """The captured request, its reply schema, the model and the records needed to validate a fresh reply offline."""
    from types import SimpleNamespace
    from packages.resume_core.rich_project_store import RichProjectStore
    from packages.resume_core.template_identity import offered_evidence, offered_references
    from packages.resume_core.templates.replies import proposal_schema, review_schema
    store = RichProjectStore(root / 'data')
    [project] = [path.name for path in (root / 'data/projects').iterdir() if path.is_dir()]
    workspace = durable(SimpleNamespace(storage=store), project)
    data = workspace.project or workspace.pre_draft
    [operation] = data.template_operations
    tasks = {task.id: task for task in operation.tasks}
    attempt = next(value for value in sorted(operation.attempts, key=lambda value: value.reserved_at)
        if tasks[value.task_id].block_id == block and value.slot == slot)
    if slot in REVIEW:
        stored = next(value for value in operation.review_inputs if value.attempt_id == attempt.id)
        value = stored.value.model_dump(mode='json', by_alias=True)
        schema = review_schema(stored.value)
    elif slot in EXTRACTION and attempt.request_value:
        value = dict(attempt.request_value)
        offered = offered_evidence(value)
        references = offered_references(value) if offered is not None else None
        full = next(item.full_schema for item in data.template_package.blocks if item.id == block)
        # 'full' keeps the pre-I3 shape with discoveries, lineage and relations for a control variant.
        schema = proposal_schema(full, None if offered is None else list(offered), None if schema_mode == 'full' else references)
    else:
        raise SystemExit('the attempt has no stored request')
    if rules is not None:
        if slot in REVIEW:
            value['semanticContext'] = {**value.get('semanticContext', {}), 'replyProtocol': rules}
        else:
            value['replyProtocol'] = rules
    if quotes and slot in EXTRACTION:
        # P4: a fields entry may quote the source text instead of citing refs; the coordinator maps the quote.
        field = schema['$defs']['ReferencedField']
        field['properties']['quote'] = {'type': ['string', 'null']}
        field['required'] = list(field['properties'])
    return value, schema, attempt.model.model, data, operation, attempt


def quotes_to_refs(raw, value):
    """P4: replace each entry's quote by the refs of the offered lines that state it (word for word, else by stems)."""
    from packages.resume_core.template_completion import stating, stating_stems
    from packages.resume_core.template_identity import offered_evidence
    outer = json.loads(raw)
    payload = outer.get('payload') if isinstance(outer, dict) else None
    if not isinstance(payload, dict):
        return raw
    table = offered_evidence(value)
    for entry in payload.get('fields') or []:
        quote = entry.pop('quote', None) if isinstance(entry, dict) else None
        if quote and not entry.get('evidence'):
            entry['evidence'] = stating(quote.strip(), table) or stating_stems(quote.strip(), table)
    return json.dumps(outer, ensure_ascii=False)


def validate(data, operation, attempt, block, raw):
    """What the import would make of the fresh reply: the class of an extraction (accepted, refused, reply-format) with its
    dropped values and derived evidence, or the receipt of a review."""
    from tools.ct06_corpus_replay import replay_extraction, replay_review
    copy = operation.model_copy(deep=True)
    reset = next(value for value in copy.attempts if value.id == attempt.id)
    reset.raw_return, reset.raw_return_hash = raw, hashlib.sha256(raw.encode()).hexdigest()
    reset.return_hash = reset.raw_return_hash
    if attempt.slot in REVIEW:
        now, detail, shape = replay_review(data, copy, reset)
        return {'kind': 'review', 'outcome': now, 'detail': detail, 'shape': shape}
    now, kind, detail, digest = replay_extraction(data, copy, reset, block)
    result = {'kind': 'extraction', 'outcome': now, 'class': kind, 'detail': detail, 'evidenceDigest': digest}
    if now == 'accepted':
        from packages.resume_core.models.template_facts import Relation
        from packages.resume_core.template_proposals import parse_proposal
        again = operation.model_copy(deep=True)
        fresh = next(value for value in again.attempts if value.id == attempt.id)
        fresh.raw_return, fresh.raw_return_hash, fresh.return_hash = raw, reset.raw_return_hash, reset.raw_return_hash
        fresh.proposal_record_id, fresh.state, fresh.outcome, fresh.error_code = None, 'returned', 'completed', None
        again.proposals = [value for value in again.proposals if value.attempt_id != attempt.id]
        captured = [Relation.model_validate(value) for value in (attempt.request_value or {}).get('capturedRelations', [])]
        _, _, proposal = parse_proposal(again, attempt.id, data.template_package, data.sources, data.facts, captured_relations=captured)
        result['dropped'] = [value.model_dump(mode='json', by_alias=True) for value in proposal.dropped_values]
        result['fields'] = len(proposal.resolved_fields)
    return result


def probe(value, schema, model, effort, out, index):
    from resume_api.cli.experimental_profile import installed_profile
    from resume_api.lifecycle import OperationFiles
    from resume_api.providers.codex_cli import CodexCliProvider
    from resume_api.providers.content import ContentFailure, ContentInput, GenerationPolicy
    from resume_api.providers.dynamic_result import dynamic_result
    from packages.resume_core.template_prompt import model_prompt
    from packages.resume_core.templates.replies import BOOKKEEPING_KEYS
    profile = installed_profile(PROFILE)
    provider = CodexCliProvider(profile.executable, experimental_profile=profile)
    timeline, raw, started = [], [], [None]

    def observe(line):
        at = round(time.monotonic() - started[0], 2) if started[0] else None
        raw.append(line if isinstance(line, bytes) else str(line).encode())
        try:
            event = json.loads(line)
            item = event.get('item') or {}
            timeline.append([at, event.get('type'), item.get('type')])
        except (ValueError, TypeError, AttributeError):
            timeline.append([at, 'unparsed', None])

    original = CodexCliProvider._run

    def run(self, files, args, deadline, cancel, **kwargs):
        # The provider's `exec --help` feature check must see its output unchanged; the model run is observed.
        if not args or args[0] != 'exec' or '--help' in args or kwargs.get('on_line') is None:
            return original(self, files, args, deadline, cancel, **kwargs)
        on_line = kwargs['on_line']
        started[0] = time.monotonic()
        def both(line):
            observe(line)
            on_line(line)
        return original(self, files, args, deadline, cancel, **{**kwargs, 'on_line': both})

    temp = out / ('operations-%d' % index)
    temp.mkdir(mode=0o700)
    request = ContentInput(model_prompt(value), dynamic_result(schema, BOOKKEEPING_KEYS),
        GenerationPolicy(model, timeout_seconds=180, allow_repair=False, reasoning_effort=effort), request_value=value)
    began, outcome, code, usage, returned = time.monotonic(), 'completed', None, None, None
    try:
        files = OperationFiles(temp)
        with files.open():
            with PATCH_LOCK:
                CodexCliProvider._run = run
            try:
                result = provider.generate(request, files, threading.Event())
            finally:
                with PATCH_LOCK:
                    if CodexCliProvider._run is run:
                        CodexCliProvider._run = original
        usage, returned = result.usage, getattr(result, 'raw_return', None)
    except ContentFailure as error:
        outcome, code, usage = 'failed', error.code, error.usage
        returned = getattr(error, 'raw_return', None)
    (out / ('probe-%d.jsonl' % index)).write_bytes(b'\n'.join(raw))
    if returned:
        (out / ('reply-%d.json' % index)).write_text(returned)
    total = round(time.monotonic() - began, 2)
    return {'index': index, 'effort': effort, 'outcome': outcome, 'code': code, 'seconds': total,
        'inputTokens': getattr(usage, 'input_tokens', None), 'cachedTokens': getattr(usage, 'cached_input_tokens', None),
        'outputTokens': getattr(usage, 'output_tokens', None), 'events': timeline}, returned


def main(args):
    root, out = args.root.resolve(), args.out.resolve()
    if out.parent != Path('/private/tmp') or not out.name.startswith('foldcv-ct06-probe-') or out.exists():
        raise SystemExit('A new /private/tmp/foldcv-ct06-probe-* folder is required')
    rules = json.loads(Path(args.protocol_rules).read_text()) if args.protocol_rules else None
    value, schema, model, data, operation, attempt = stored_request(root, args.block, args.slot, args.schema, rules, args.quotes)
    from packages.resume_core.template_prompt import model_prompt
    planned = len(args.effort) * args.concurrent
    ledger = Ledger(LEDGER)
    with ledger.lock():
        current = ledger.read()
        budget = current.get('d101')
        if budget is None:
            raise SystemExit('the ledger has no D101 allowance')
        if budget['probesSpent'] + planned > budget['probeCap']:
            raise SystemExit('D101 probe cap reached: %d spent of %d, %d planned' % (budget['probesSpent'], budget['probeCap'], planned))
        budget['probesSpent'] += planned
        entry = {'decision': 'D101', 'source': args.label, 'fromRun': args.from_run, 'block': args.block, 'slot': args.slot,
            'model': model, 'variant': args.variant, 'schema': args.schema, 'protocolRules': args.protocol_rules,
            'concurrent': args.concurrent, 'promptChars': len(model_prompt(value)),
            'startedAt': datetime.now(timezone.utc).isoformat(), 'folder': out.name, 'calls': []}
        current.setdefault('probes', []).append({'id': 'PROBE-%02d' % (len(current.get('probes', [])) + 1), **entry})
        probe_id = current['probes'][-1]['id']
        ledger.write(current)
    out.mkdir(mode=0o700)
    print(probe_id, 'charged', planned, 'calls', flush=True)
    index = 0
    for effort in args.effort:
        jobs = []
        for _ in range(args.concurrent):
            index += 1
            jobs.append((value, schema, model, effort, out, index))
        with ThreadPoolExecutor(max_workers=args.concurrent) as pool:
            outcomes = list(pool.map(lambda job: probe(*job), jobs))
        for call, returned in outcomes:
            if args.validate and returned:
                try:
                    checked = quotes_to_refs(returned, value) if args.quotes else returned
                    call['validation'] = validate(data, operation, attempt, args.block, checked)
                except Exception as error:  # noqa: BLE001 - a validation crash is itself a finding
                    call['validation'] = {'kind': 'error', 'detail': type(error).__name__ + ': ' + str(error)[:200]}
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
    parser.add_argument('--variant', default='control', help='a short name for the ledger: control, content-only, always-cite, quotes, ...')
    parser.add_argument('--schema', choices=['content', 'full'], default='content')
    parser.add_argument('--protocol-rules', help='JSON file with {version, rules} replacing the stored reply protocol')
    parser.add_argument('--concurrent', type=int, default=1, help='simultaneous sends of the same request per effort')
    parser.add_argument('--quotes', action='store_true', help='P4: fields entries quote the source; quotes are mapped to refs before validation')
    parser.add_argument('--validate', action='store_true', help='check each fresh reply offline as the import would')
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args())
