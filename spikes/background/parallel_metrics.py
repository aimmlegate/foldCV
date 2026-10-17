"""Measure scoped publication outcomes without changing any dependency guard."""

import argparse
from collections import Counter
import json
from pathlib import Path

from packages.resume_core.models.agent import AgentQuery
from tests.recovery.test_background_inverse import put
from tests.support.background_publication import PublicationFixture
from tools.background_evidence import source_hashes
from .native_parallel import now, write

SCOPES = ("narrow-independent", "broad-read", "same-write-scope")
ORDERS = ((0, 1), (1, 0))


def measure(root, scope, order):
    if scope not in SCOPES or order not in ORDERS:
        raise ValueError("Use a frozen publication measurement case")
    fixture = PublicationFixture(root)
    targets = ("narrative", "narrative" if scope == "same-write-scope" else "quote")
    participants = []
    for index, target in enumerate(targets):
        reads = ["narrative", "quote"] if scope == "broad-read" else [target]
        participants.append(fixture.accepted(str(index), queries=[AgentQuery(kind="document", ids=reads)],
            steps=[put(fixture.current(), target, text="Measured change " + str(index))]))
    outcomes = []
    for index in order:
        job, proposal, _batch = participants[index]
        result = fixture.publish(job, proposal)
        outcomes.append(dict(participant=index, job=job.id, outcome=result.publication,
            reason=result.publication_error.code if result.publication_error is not None else None,
            durable=result.receipt is not None and result.receipt.durable))
    expected = ["saved", "saved" if scope == "narrow-independent" else "needs_review"]
    if [row["outcome"] for row in outcomes] != expected or not outcomes[0]["durable"]:
        raise AssertionError("Unexpected scoped publication outcome")
    if scope != "narrow-independent" and (not outcomes[1]["reason"] or outcomes[1]["durable"]):
        raise AssertionError("A rejected publication needs its actual reason and no receipt")
    return dict(scope=scope, order=list(order), outcomes=outcomes)


def run(root, sources):
    if root.exists():
        raise ValueError("Use a new owned measurement directory")
    root.mkdir(parents=True, mode=0o700)
    cases = [measure(root / (scope + "-" + str(order[0])), scope, order) for scope in SCOPES for order in ORDERS]
    summary = {}
    for scope in SCOPES:
        outcomes = [row for case in cases if case["scope"] == scope for row in case["outcomes"]]
        rejected = [row for row in outcomes if row["outcome"] == "needs_review"]
        summary[scope] = dict(publications=len(outcomes), conflicts=len(rejected),
            reasons=dict(Counter(row["reason"] for row in rejected)), conflictFraction=len(rejected) / len(outcomes))
    return dict(status="passed", at=now(), sourceHashes=source_hashes(sources), nativeStarts=0,
        scope="Frozen synthetic publication schedules; not an estimated user conflict rate.", cases=cases, summary=summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(Path("tests/requirements.json").read_bytes())["backgroundExecution"]
    write(args.output, run(args.root, spec["sources"]))
