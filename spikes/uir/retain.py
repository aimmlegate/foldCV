"""Retain exact UIR source scopes and append deferred review roles atomically."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "docs/gui/handoffs/PROTOTYPE-ADOPTION"


def retain(task, paths, scope):
    relative = f"docs/gui/handoffs/PROTOTYPE-ADOPTION/{task.lower()}-source-manifest.json"
    target = ROOT / relative
    assert not target.exists(), "Milestone manifests are immutable"
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    files = {}
    for path in sorted(set(paths)):
        source = ROOT / path
        if source.is_file():
            files[path] = {"sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "bytes": source.stat().st_size}
        else:
            before = subprocess.check_output(["git", "show", f"{base}:{path}"], cwd=ROOT)
            marker = b"UIR deleted file\0" + path.encode() + b"\0" + before
            files[path] = {"state": "deleted", "sha256": hashlib.sha256(marker).hexdigest(), "bytes": 0,
                "hashKind": "SHA256 of UIR deleted file + NUL + UTF-8 path + NUL + base bytes",
                "baseSha256": hashlib.sha256(before).hexdigest(), "baseBytes": len(before)}
    locator = f"git log -1 --format=%H -- {relative}"
    manifest = {"task": task, "baseRevision": base, "scope": scope, "files": files,
        "retainedRevisionLocator": locator, "excludes": ["state.json", "review ledger bookkeeping", "this manifest"]}
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    ledger = ROOT / "docs/gui/handoffs/external-review-backlog.json"
    before = ledger.read_bytes(); value = json.loads(before)
    assert not any(entry.get("task") == task for entry in value["entries"])
    for provider, model, effort in [("sol", "gpt-6.1-sol", "high"), ("grok", "grok-4.7-build-fast", "medium"),
            ("gemini", "gemini-3.8-flash-medium", "medium"), ("astra", "gpt-6-astra", "high")]:
        value["entries"].append({"task": task, "scope": scope, "started_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider, "model": model, "effort": effort, "status": "pending_quota",
            "reason": "UIR scoped deferral explicitly authorized for this implementation run. Current-agent checks only; no independent reviewer/provider call, availability probe or quota response.",
            "base_revision": base, "retained_revision": None, "retained_revision_locator": locator,
            "manifest_path": relative, "manifest_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "snapshot_path": locator, "files": list(files), "scope_hashes": {p: v["sha256"] for p,v in files.items()}, "verdict": None})
    output = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    assert json.loads(output)["entries"][:-4] == json.loads(before)["entries"]
    assert ledger.read_bytes() == before, "Concurrent ledger change; reread before append"
    temporary = ledger.with_suffix(".json.uir-tmp"); temporary.write_bytes(output); temporary.replace(ledger)
    return relative, locator
