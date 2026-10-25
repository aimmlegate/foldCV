"""Compare a live CAP draft with its frozen baseline: only wording may change; everything else must hold."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]


def flat(document):
    out = []
    def walk(blocks):
        for block in blocks:
            out.append(block)
            walk(block.get("children") or [])
    for region in document["regions"]:
        walk(region["blocks"])
    return out


def text(value):
    if isinstance(value, dict):
        return "".join(text(item) for key, item in value.items() if key in {"text", "content", "rows", "cells", "caption"})
    if isinstance(value, list):
        return "".join(text(item) for item in value)
    return value if isinstance(value, str) else ""


def links(value):
    found = []
    def walk(item):
        if isinstance(item, dict):
            if item.get("type") == "link":
                found.append((item.get("href"), text(item.get("content"))))
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return sorted(found)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def verify(baseline, candidate, allowed):
    base, cand = flat(baseline["project"]["document"]), flat(candidate["project"]["document"])
    report = {"blockOrderSame": [b["id"] for b in base] == [b["id"] for b in cand]}
    pairs = dict(zip([b["id"] for b in base], zip(base, cand)))
    own = lambda block: {key: value for key, value in block.items() if key != "children"}
    # A parent section changes only through its children, which are compared on their own.
    changed = sorted(key for key, (old, new) in pairs.items() if digest(own(old)) != digest(own(new)))
    report["changedBlocks"] = changed
    report["onlyAllowedChanged"] = set(changed) <= set(allowed)
    report["edits"] = {key: {"before": text(pairs[key][0].get("content")), "after": text(pairs[key][1].get("content"))} for key in changed}
    report["shorter"] = all(len(edit["after"]) < len(edit["before"]) for edit in report["edits"].values())
    report["cyrillicKept"] = all(re.search("[А-Яа-яЁё]", edit["after"]) for edit in report["edits"].values())
    whole_before, whole_after = text(baseline["project"]["document"]), text(candidate["project"]["document"])
    report["linksSame"] = links(baseline["project"]["document"]) == links(candidate["project"]["document"])
    report["numbersSame"] = sorted(re.findall(r"\d+", whole_before)) == sorted(re.findall(r"\d+", whole_after))
    report["emojiSame"] = whole_before.count("😀") == whole_after.count("😀")
    report["contactsSame"] = all(item in whole_after for item in re.findall(r"[\w.+-]+@[\w.-]+", whole_before))
    report["factsSame"] = digest(baseline["project"]["facts"]) == digest(candidate["project"]["facts"])
    report["sourcesSame"] = digest(baseline["project"]["sources"]) == digest(candidate["project"]["sources"])
    report["assetsSame"] = digest(baseline["project"]["assets"]) == digest(candidate["project"]["assets"])
    report["templateSame"] = digest(baseline["project"]["template"]) == digest(candidate["project"]["template"])
    report["passed"] = all(report[key] for key in ("blockOrderSame", "onlyAllowedChanged", "shorter", "cyrillicKept", "linksSame",
        "numbersSame", "emojiSame", "contactsSame", "factsSame", "sourcesSame", "assetsSame", "templateSame")) and bool(changed)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--out", type=Path, required=True)
    options = parser.parse_args()
    spec = json.loads((options.root / "task-spec.json").read_text())
    path = Path(spec["dataRoot"]) / "assistant/proposals" / spec["projectId"] / (options.proposal + "-1.json")
    payload = json.loads(path.read_text())["payload"]
    report = verify(payload["baseline"], payload["candidate"], list(spec.get("wordyBlocks") or {}))
    report.update({"proposal": options.proposal, "state": payload["proposal"]["state"],
        "coverage": {state: sum(unit["state"] == state for unit in payload["proposal"]["coverage"]) for state in ("changed", "unchanged", "unresolved")},
        "contentSha256": payload["proposal"]["contentSha256"]})
    options.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
