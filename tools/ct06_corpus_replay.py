"""CT06 corpus replay: re-parse every stored live reply with the current coordinator and compare with a baseline.

No model is called. For each live root the extraction attempts are re-parsed (transport schema check, then
parse_proposal on a copy of the operation with the attempt reset) and the protocol-3 reviews are re-decoded
(record_review on a copy). Each attempt gets its stored outcome, its current outcome, an error class and a digest
of the resolved evidence, so a coordinator change shows exactly which replies it now accepts, refuses or binds
differently. `--baseline write` stores the table; `--baseline check` fails on a regression: an attempt accepted
in the baseline that is refused now, or whose evidence digest changed.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'services/api/src')]

# The D097/D100 live roots and their ledger run ids; the project with its stored replies lives in each.
DEFAULT_ROOTS = {
    'LIVE-05': '/private/tmp/foldcv-ct06-live-luna-cvb-r3', 'LIVE-06': '/private/tmp/foldcv-ct06-live-luna-cvb-r4',
    'LIVE-07': '/private/tmp/foldcv-ct06-live-luna-cvb-r5', 'LIVE-08': '/private/tmp/foldcv-ct06-live-luna-cvb-r6',
    'LIVE-09': '/private/tmp/foldcv-ct06-live-luna-cvb-r7', 'LIVE-11': '/private/tmp/foldcv-ct06-live-luna-cvb-r8',
    'LIVE-12': '/private/tmp/foldcv-ct06-live-luna-cva-r3'}
EXTRACTION = {'initial', 'primary_repair', 'fallback_repair'}
REVIEW = {'review', 'replacement_review'}
BASELINE = ROOT / 'docs/gui/handoffs/MODEL-FIT-20261025/baseline.json'


def load(root):
    from packages.resume_core.rich_project_store import RichProjectStore
    from tools.ct06_live_import import durable
    store = RichProjectStore(root / 'data')
    [project] = [path.name for path in (root / 'data/projects').iterdir() if path.is_dir()]
    workspace = durable(SimpleNamespace(storage=store), project)
    data = workspace.project or workspace.pre_draft
    [operation] = data.template_operations
    return data, operation


def evidence_digest(proposal):
    rows = sorted(({'pointer': field.pointer, 'fieldKey': field.field_key,
        'evidence': [span.model_dump(mode='json', by_alias=True) for span in field.evidence]}
        for field in proposal.resolved_fields), key=lambda row: (row['pointer'], row['fieldKey']))
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def error_class(message):
    if message is None:
        return None
    for prefix, name in (('every bound value needs one fields entry', 'missing-entry'), ('matches no compiled binding', 'no-binding'),
            ('no unique compiled item binding', 'ambiguous-binding'), ('relation repair changes uncaptured identity', 'relation-identity'),
            ('/payload/relations', 'relations-shape'), ('matches none of the allowed shapes', 'schema-shape')):
        if prefix in message:
            return name
    return 'other'


def replay_extraction(data, operation, attempt, block):
    from packages.resume_core.models.template_facts import Relation
    from packages.resume_core.template_proposals import parse_proposal, transport_refusal
    copy = operation.model_copy(deep=True)
    reset = next(value for value in copy.attempts if value.id == attempt.id)
    reset.proposal_record_id, reset.state, reset.outcome, reset.error_code = None, 'returned', 'completed', None
    copy.proposals = [value for value in copy.proposals if value.attempt_id != attempt.id]
    reason = transport_refusal(reset, data.template_package, block)
    if reason:
        return 'refused', 'reply-format', reason, None
    captured = [Relation.model_validate(value) for value in (attempt.request_value or {}).get('capturedRelations', [])]
    try:
        _, _, proposal = parse_proposal(copy, attempt.id, data.template_package, data.sources, data.facts, captured_relations=captured)
    except Exception as error:  # noqa: BLE001 - every failure of the current code is a finding here
        return 'error', type(error).__name__, str(error)[:200], None
    if proposal.state == 'provisional':
        return 'accepted', None, None, evidence_digest(proposal)
    message = '; '.join(proposal.errors)
    return 'refused', error_class(message), message[:200], None


def replay_review(data, operation, attempt):
    from packages.resume_core.template_import import TemplateImportFailure
    from packages.resume_core.template_review import record_review
    from packages.resume_core.templates.replies import REVIEW_PROTOCOL, check_references, review_protocol
    stored = next((value for value in operation.review_inputs if value.attempt_id == attempt.id), None)
    protocol = review_protocol(stored.value) if stored is not None else None
    if attempt.raw_return is None:
        return 'no-reply', attempt.error_code or attempt.outcome, None
    listed, duplicates, unknown = None, 0, 0
    try:
        results = json.loads(attempt.raw_return)['payload']['results']
        checks = [result['check'] for result in results]
        listed, duplicates = len(checks), len(checks) - len(set(checks))
        unknown = len(set(checks) - set(check_references(stored.value))) if stored is not None else 0
    except (ValueError, KeyError, TypeError):
        pass
    shape = 'listed=%s dup=%d unknown=%d' % (listed, duplicates, unknown)
    if protocol != REVIEW_PROTOCOL['version']:
        return 'not-protocol-3', protocol or 'none', shape
    copy = operation.model_copy(deep=True)
    reset = next(value for value in copy.attempts if value.id == attempt.id)
    reset.review_receipt_id, reset.state, reset.outcome, reset.error_code = None, 'returned', 'completed', None
    copy.receipts = [value for value in copy.receipts if value.attempt_id != attempt.id]
    # The owning task lists its receipts; the integrity check refuses a dangling id.
    task = next(value for value in copy.tasks if value.id == attempt.task_id)
    task.receipt_ids = [value for value in task.receipt_ids if value != attempt.review_receipt_id]
    try:
        _, receipt = record_review(copy, attempt.id, data.sources, datetime.now(timezone.utc).isoformat())
    except TemplateImportFailure as error:
        return 'incomplete', error.code, shape
    except Exception as error:  # noqa: BLE001 - the LIVE-06/07 intermediate forms fail the current schema
        return 'not-current-schema', type(error).__name__, shape
    failing = sum(1 for result in receipt.reply.results if result.disposition != 'satisfied')
    return 'receipt', 'failing=%d/%d' % (failing, len(receipt.reply.results)), shape


def replay(run, root):
    data, operation = load(root)
    blocks = {task.id: task.block_id for task in operation.tasks}
    attempts, reviews = [], []
    for attempt in sorted(operation.attempts, key=lambda value: value.reserved_at):
        block = blocks[attempt.task_id]
        if attempt.slot in EXTRACTION and attempt.raw_return is not None:
            now, kind, detail, digest = replay_extraction(data, operation, attempt, block)
            attempts.append({'run': run, 'attemptId': attempt.id, 'block': block, 'slot': attempt.slot,
                'stored': attempt.error_code or 'accepted', 'now': now, 'class': kind, 'detail': detail, 'evidenceDigest': digest})
        elif attempt.slot in REVIEW:
            now, detail, shape = replay_review(data, operation, attempt)
            reviews.append({'run': run, 'attemptId': attempt.id, 'block': block, 'slot': attempt.slot,
                'stored': 'receipt' if attempt.review_receipt_id else (attempt.error_code or 'no receipt'), 'now': now, 'detail': detail, 'shape': shape})
    return attempts, reviews


def summary(attempts, reviews):
    classes = {}
    for row in attempts:
        if row['now'] != 'accepted':
            classes[row['class']] = classes.get(row['class'], 0) + 1
    current = [row for row in reviews if row['now'] not in {'not-protocol-3', 'not-current-schema', 'no-reply'}]
    return {'attempts': len(attempts), 'refused': sum(1 for row in attempts if row['now'] != 'accepted'), 'refusedByClass': classes,
        'reviewsCurrentProtocol': len(current), 'reviewsWithoutReceipt': sum(1 for row in current if row['now'] != 'receipt'),
        'reviewsHistoricalForm': len(reviews) - len(current)}


def compare(baseline, attempts, reviews):
    before = {(row['run'], row['attemptId']): row for row in baseline['attempts']}
    regressions, improvements = [], []
    for row in attempts:
        old = before.get((row['run'], row['attemptId']))
        if old is None:
            continue
        if old['now'] == 'accepted' and row['now'] != 'accepted':
            regressions.append((row, 'accepted before, now %s: %s' % (row['class'], row['detail'])))
        elif old['now'] == 'accepted' and old['evidenceDigest'] != row['evidenceDigest']:
            regressions.append((row, 'evidence changed %s -> %s' % (old['evidenceDigest'], row['evidenceDigest'])))
        elif old['now'] != 'accepted' and row['now'] == 'accepted':
            improvements.append(row)
    before = {(row['run'], row['attemptId']): row for row in baseline['reviews']}
    for row in reviews:
        old = before.get((row['run'], row['attemptId']))
        if old is None:
            continue
        if old['now'] == 'receipt' and (row['now'] != 'receipt' or old['detail'] != row['detail']):
            regressions.append((row, 'review %s before, now %s %s' % (old['detail'], row['now'], row['detail'])))
        elif old['now'] == 'incomplete' and row['now'] == 'receipt':
            improvements.append(row)
    return regressions, improvements


def main(args):
    roots = {Path(path).name: Path(path) for path in args.roots} if args.roots else {run: Path(path) for run, path in DEFAULT_ROOTS.items()}
    attempts, reviews = [], []
    for run, root in roots.items():
        found, decoded = replay(run, root)
        attempts += found
        reviews += decoded
        if args.verbose:
            for row in found:
                print('%-8s %-18s %-14s stored=%-24s now=%-9s %s %s' % (run, row['block'], row['slot'], row['stored'], row['now'],
                    row['class'] or row['evidenceDigest'], (row['detail'] or '')[:90]))
            for row in decoded:
                print('%-8s %-18s %-19s stored=%-10s now=%-14s %s | %s' % (run, row['block'], row['slot'], row['stored'], row['now'], row['detail'], row['shape']))
    print(json.dumps(summary(attempts, reviews), ensure_ascii=False))
    for row in attempts:
        if row['now'] != 'accepted':
            print('  refused %-8s %-18s %-14s %-18s %s' % (row['run'], row['block'], row['slot'], row['class'], (row['detail'] or '')[:100]))
    for row in reviews:
        if row['now'] not in {'receipt', 'not-protocol-3', 'not-current-schema', 'no-reply'}:
            print('  review  %-8s %-18s %-19s %-12s %s | %s' % (row['run'], row['block'], row['slot'], row['now'], row['detail'], row['shape']))
    if args.baseline == 'write':
        code = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        args.baseline_path.write_text(json.dumps({'generatedAt': datetime.now(timezone.utc).isoformat(), 'code': code,
            'summary': summary(attempts, reviews), 'attempts': attempts, 'reviews': reviews}, ensure_ascii=False, indent=1) + '\n')
        print('baseline written:', args.baseline_path)
    elif args.baseline == 'check':
        regressions, improvements = compare(json.loads(args.baseline_path.read_text()), attempts, reviews)
        for row in improvements:
            print('  improved %-8s %-18s %-14s now %s %s' % (row['run'], row['block'], row['slot'], row['now'], row.get('detail') or ''))
        for row, why in regressions:
            print('  REGRESSION %-8s %-18s %-14s %s' % (row['run'], row['block'], row['slot'], why))
        print('regressions: %d, improvements: %d' % (len(regressions), len(improvements)))
        if regressions:
            raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roots', nargs='*', help='live roots; default: the seven D097/D100 Luna roots')
    parser.add_argument('--baseline', choices=['write', 'check'])
    parser.add_argument('--baseline-path', type=Path, default=BASELINE)
    parser.add_argument('--verbose', action='store_true')
    main(parser.parse_args())
