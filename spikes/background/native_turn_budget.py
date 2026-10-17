"""Charge each authorized multiplexed model turn before its single RPC dispatch."""

from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re

from packages.resume_core.storage import atomic_write


HANDOFF = Path(__file__).resolve().parents[2] / "docs/gui/handoffs/BACKGROUND-WORK"
AUTHORITY = HANDOFF / "parallel-transport-authorization.json"
PROPOSAL = HANDOFF / "nb07a-evidence/parallel-transport-proposal.md"
PROPOSAL_SHA256 = "f623b3d35c9c28c93ea95f34fe4b07285accf794f435a70615527bf7f7949933"
GROUPS = {"NB00": [("NB-R05:v01", 2), ("NB-R05:v02", 2), ("NB-R05:v03", 3), ("NB-R05:v04", 3)],
    "NB07b": [("NB-X03:v03", 3), ("NB-X03:v04", 3)]}
CAPS = {"NB00": 10, "NB07b": 6}
ROLES = {"NB-R05:v01": ["agent-A", "agent-B"], "NB-R05:v02": ["agent-A", "structured-rewrite-B"],
    "NB-R05:v03": ["agent-A", "agent-B", "structured-rewrite-C"],
    "NB-R05:v04": ["agent-A", "structured-rewrite-B", "structured-sync-C"],
    "NB-X03:v03": ["agent-A", "agent-B", "structured-rewrite-C"],
    "NB-X03:v04": ["agent-A", "structured-rewrite-B", "structured-sync-C"]}
ACCOUNT_ERRORS = {"AUTH_REQUIRED", "AGENT_AUTH_REQUIRED", "RATE_LIMITED", "AGENT_QUOTA", "QUOTA_EXHAUSTED"}
RETRY_AUTHORITY = HANDOFF / "native-feasibility-retry-authorization.json"
RETRY_PROPOSAL = HANDOFF / "nb00b-evidence/native-retry-proposal.md"
RETRY_PROPOSAL_SHA256 = "c01b055c1bfc2612a4f8c7be4e9552b4b5246d51c166eeb31b9522bd3e54fb6a"
FAILED_PAIR_SHA256 = "aed250fd5514208fa175709cf119e629674380736b3a6d4a697f2c6440d3a72c"


class NativeTurnDenied(ValueError):
    pass


def matrix_budget(ledger, pool, *, retry_authority=RETRY_AUTHORITY, retry_proposal=RETRY_PROPOSAL):
    try:
        selected = ledger["pools"][pool]
        rows = [row for row in ledger["attempts"] if row["pool"] == pool]
        if (selected["authorized"] is not True or type(selected["cap"]) is not int
                or type(selected["spent"]) is not int or selected["spent"] != len(rows)
                or not 0 <= selected["spent"] <= selected["cap"]):
            raise NativeTurnDenied("Invalid native cap")
        if selected["cap"] == CAPS[pool]:
            return selected["cap"], rows, 0, None
        if pool != "NB00" or selected["cap"] != 12:
            raise NativeTurnDenied("Unapproved native cap")
        raw = retry_authority.read_bytes()
        grant = json.loads(raw)
        historical = rows[:2]
        fingerprint = hashlib.sha256(json.dumps(historical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if (grant["schemaVersion"] != 1 or grant["status"] != "approved_by_user"
                or grant["authorized"] is not True or grant["pool"] != "NB00" or grant["priorCap"] != 10
                or grant["cap"] != 12 or grant["historicalStarts"] != 2 or grant["freshMatrixTurns"] != 10
                or grant["everyModelTurnCounts"] is not True or grant["noOtherPoolsChanged"] is not True
                or not isinstance(grant["userInstruction"], str) or not grant["userInstruction"].strip()
                or not isinstance(grant["approvedAt"], str) or not grant["approvedAt"].strip()
                or grant["proposalSha256"] != RETRY_PROPOSAL_SHA256
                or hashlib.sha256(retry_proposal.read_bytes()).hexdigest() != RETRY_PROPOSAL_SHA256
                or grant["failedAttemptIds"] != ["NB00-1", "NB00-2"]
                or grant["failedAttemptsSha256"] != fingerprint or fingerprint != FAILED_PAIR_SHA256
                or len(historical) != 2 or any(row["status"] != "failed" for row in historical)):
            raise NativeTurnDenied("Exact approved retry and unchanged failed records are required")
        return 12, rows[2:], 2, hashlib.sha256(raw).hexdigest()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise NativeTurnDenied("Exact approved retry and unchanged failed records are required") from error


def spend_turn(path, *, pool, variant, job, source_hashes, authority=AUTHORITY, proposal=PROPOSAL,
               retry_authority=RETRY_AUTHORITY, retry_proposal=RETRY_PROPOSAL):
    if pool not in GROUPS or not isinstance(job, str) or not job:
        raise NativeTurnDenied("Unknown pool or turn identity")
    if (not source_hashes or not isinstance(source_hashes, dict)
            or any(not isinstance(name, str) or not name or not isinstance(checksum, str)
                or re.fullmatch(r"[a-f0-9]{64}", checksum) is None for name, checksum in source_hashes.items())):
        raise NativeTurnDenied("A frozen source identity is required")
    try:
        raw_authority = authority.read_bytes()
        grant = json.loads(raw_authority)
        if (grant["authorized"] is not True or grant["everyModelTurnCounts"] is not True
                or grant["transport"] != "one pinned multiplexed App Server"
                or grant["NB00Cap"] != 10 or grant["NB07bCap"] != 6
                or grant["proposalSha256"] != PROPOSAL_SHA256
                or hashlib.sha256(proposal.read_bytes()).hexdigest() != PROPOSAL_SHA256):
            raise NativeTurnDenied("Exact transport authority is required")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise NativeTurnDenied("Exact transport authority is required") from error
    with (path.parent / ".native-attempts.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = json.loads(path.read_bytes())
        selected = ledger["pools"][pool]
        all_rows = [row for row in ledger["attempts"] if row["pool"] == pool]
        cap, rows, historical, retry_sha = matrix_budget(ledger, pool,
            retry_authority=retry_authority, retry_proposal=retry_proposal)
        order = [name for name, count in GROUPS[pool] for _ in range(count)]
        if (selected["authorized"] is not True or type(selected["cap"]) is not int
                or selected["cap"] != cap or type(selected["spent"]) is not int
                or selected["spent"] != len(all_rows) or len(all_rows) >= selected["cap"]
                or len(rows) >= len(order)
                or [row["variant"] for row in rows] != order[:len(rows)]
                or variant != order[len(rows)] or any(row["status"] == "failed" for row in rows)
                or any(row["status"] not in {"started", "native_completed_unvalidated", "passed"} for row in rows)
                or any(row["sourceHashes"] != source_hashes for row in rows)
                or any(row.get("jobId") == job for row in ledger["attempts"])
                or any(row.get("error") in ACCOUNT_ERRORS for row in ledger["attempts"])):
            raise NativeTurnDenied("Native matrix, source, account or counter guard denied this turn")
        previous_group = next(index for index, name in enumerate(order) if name == variant)
        if any(row["status"] != "passed" for row in rows[:previous_group]):
            raise NativeTurnDenied("The previous group has no accepted proof")
        selected["spent"] += 1
        row = dict(id=pool + "-" + str(selected["spent"]), pool=pool, number=selected["spent"],
            variant=variant, role=ROLES[variant][len(rows) - previous_group], jobId=job, sourceHashes=source_hashes, status="started", error=None,
            model="gpt-6-luna", effort="medium", startedAt=datetime.now(timezone.utc).isoformat(),
            transport="one pinned multiplexed App Server", failedStartsCount=True,
            authority=str(authority), authoritySha256=hashlib.sha256(raw_authority).hexdigest())
        if historical:
            row.update(retryAuthority=str(retry_authority), retryAuthoritySha256=retry_sha, historicalStarts=historical)
        ledger["attempts"].append(row)
        atomic_write(path, json.dumps(ledger, indent=2, ensure_ascii=False).encode() + b"\n")
        return row
