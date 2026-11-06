"""Check that every decision number named in the code (`D123` in `packages`, `services`, `apps/web/src`) has a line
in the tracked `docs/gui/decisions-index.md`. A policy check, not a test: the test policy keeps tests off the docs.
Reads only tracked files, so it runs the same in a clean clone and in CI.
"""

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/gui/decisions-index.md"
FOLDERS = ("packages", "services", "apps/web/src")
REFERENCE = re.compile(r"\bD\d{3}\b")


def main():
    indexed = set(re.findall(r"^- (D\d{3}) ", INDEX.read_text(encoding="utf-8"), re.M))
    files = subprocess.run(["git", "ls-files", "-z", *FOLDERS], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split("\0")
    missing = {}
    for name in filter(None, files):
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for number in set(REFERENCE.findall(text)) - indexed:
            missing.setdefault(number, []).append(name)
    for number in sorted(missing):
        print(f"{number} is not in {INDEX.relative_to(ROOT)}: {', '.join(sorted(missing[number]))}")
    if missing:
        return 1
    print(f"decision references indexed ({len(indexed)} decisions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
