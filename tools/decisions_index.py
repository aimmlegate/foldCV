"""Write `docs/gui/decisions-index.md`: the number and title of every `## D…` heading of the decisions log.

The log itself is local only (`docs/gui/automation/decisions.md` in the main checkout); the index is tracked, so a
`D123` named in a code comment can be looked up in a clean clone. Names of the private-data guard's local indicators
become "local", as the published repository carries none of them. Run it after a new decision:

    python tools/decisions_index.py --log /path/to/main/docs/gui/automation/decisions.md \
        --indicators /path/to/main/.private/resume-qa/indicators.json
"""

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/gui/decisions-index.md"
HEADING = re.compile(r"^## (D\d{3})\s*(?::|—|-)\s*(.+?)\s*$", re.M)


def redact(title: str, names: list[str]) -> str:
    # The guard's own word match: a name inside a longer word is not that name.
    for name in names:
        title = re.sub(r"(?<![^\W\d_])" + re.escape(name) + r"(?![^\W\d_])", "local", title, flags=re.I)
    return title


def index_text(log: str, names: list[str]) -> str:
    headings = [(number, redact(title, names)) for number, title in HEADING.findall(log)]
    if not headings:
        raise SystemExit("no `## Dnnn` headings in the log")
    lines = ["# Decisions index", "",
             "Number and title of each decision in the local log `docs/gui/automation/decisions.md`. Written by",
             "`tools/decisions_index.py`; checked by `tools/check_decisions_index.py`.", ""]
    lines += [f"- {number} {title}" for number, title in headings]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, default=ROOT / "docs/gui/automation/decisions.md",
                        help="the decisions log (default: the one of this checkout)")
    parser.add_argument("--indicators", type=Path, default=ROOT / ".private/resume-qa/indicators.json",
                        help="the guard's local indicators (default: the ones of this checkout)")
    args = parser.parse_args(argv)
    # Without the indicators a title could publish a name the guard would only catch at commit time.
    if not args.indicators.is_file():
        raise SystemExit(f"the indicators file is missing: {args.indicators}")
    names = json.loads(args.indicators.read_text(encoding="utf-8")).get("names", [])
    INDEX.write_text(index_text(args.log.read_text(encoding="utf-8"), names), encoding="utf-8")
    print(f"wrote {INDEX.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
