"""Audit a private PDF corpus without inference or candidate text in the summary: every PDF text line reaches the
extracted source units once, and the first page starts with its heading."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

import pymupdf

from packages.resume_core.extraction.parser import extract
from packages.resume_core.sources import canonical_source


def check(args):
    report = []
    args.views.mkdir(parents=True, exist_ok=True)
    for case in json.loads(args.inputs.read_text()):
        raw = (ROOT / case["copy"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == case["sha256"]
        with pymupdf.open(stream=raw, filetype="pdf") as document:
            blocks = [[block for block in page.get_text("blocks", sort=False) if block[6] == 0]
                      for page in document]
        expected_lines = Counter((page, line) for page, items in enumerate(blocks, 1)
                                 for block in items for line in block[4].splitlines(keepends=True))
        result = extract(raw, case["name"])
        actual_lines = Counter((unit.location.page, line) for unit in result.units
                               for line in unit.text.splitlines(keepends=True))
        assert actual_lines == expected_lines, case["id"]
        first = min(blocks[0], key=lambda block: (block[1], block[0]))[4].splitlines()[0]
        assert result.units[0].text.splitlines()[0] == first, case["id"]
        source = canonical_source(result)
        assert "".join(unit.text for unit in source.units) == "".join(unit.text for unit in result.units), case["id"]
        (args.views / f'{case["id"]}.json').write_text(result.model_dump_json(by_alias=True, indent=2))
        report.append({"fixture": case["id"], "sha256": case["sha256"], "pages": result.page_count,
            "textLines": sum(expected_lines.values()), "missingLines": 0, "extraLines": 0,
            "firstPageHeadingFirst": True, "sourceUnits": len(source.units),
            "uncertainLayoutFragments": sum(bool(u.structure and u.structure.layout_uncertain) for u in result.units),
            "modelCalls": 0})
    args.summary.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"files": len(report), "lostLines": 0, "modelCalls": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    check(parser.parse_args())
