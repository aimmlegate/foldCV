"""Pyright as a ratchet: run it over `packages` and `services` (the `[tool.pyright]` settings) and fail when a file has
more errors than `tools/pyright-baseline.json` records. Fewer errors pass; `--write` records the current counts.
Most of today's errors are pydantic constructor calls by field alias, which pyright cannot see; new code adds none.

    python tools/check_pyright.py            # compare (CI)
    python tools/check_pyright.py --write    # after fixing errors, record the lower counts
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tools/pyright-baseline.json"


def counts() -> Counter:
    run = subprocess.run([str(Path(sys.executable).with_name("pyright")), "--outputjson", "--pythonpath", sys.executable],
                         cwd=ROOT, capture_output=True, text=True)
    try:
        report = json.loads(run.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"pyright gave no report (exit {run.returncode}): {run.stderr.strip()[:400]}")
    errors = Counter()
    for item in report["generalDiagnostics"]:
        if item["severity"] == "error":
            errors[Path(item["file"]).resolve().relative_to(ROOT).as_posix()] += 1
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="record the current counts as the baseline")
    args = parser.parse_args(argv)
    current = counts()
    if args.write:
        BASELINE.write_text(json.dumps(dict(sorted(current.items())), indent=1) + "\n", encoding="utf-8")
        print(f"recorded {sum(current.values())} errors in {len(current)} files")
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    worse = {name: (baseline.get(name, 0), count) for name, count in current.items() if count > baseline.get(name, 0)}
    for name, (before, now) in sorted(worse.items()):
        print(f"{name}: {before} -> {now} pyright errors")
    if worse:
        print("run .venv/bin/pyright <file> for the errors; fix the new ones")
        return 1
    print(f"pyright: {sum(current.values())} errors, none above the baseline ({sum(baseline.values())})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
