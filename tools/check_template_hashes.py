"""Print the hashes of the five public bundled templates, or compare them with a recorded file.

Each line: `id revision packageHash configHash originalHash`. `--expect FILE` exits non-zero on any changed value or
on another id set. Only the public templates count: a private `templates/local` folder is left out.
"""

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ("generic-two-column", "generic-one-column", "generic-skills-table", "generic-questionnaire",
          "generic-project-cards")


def lines():
    # Read before the store module computes its template table at import time.
    os.environ["FOLDCV_PUBLIC_TEMPLATES"] = "1"
    sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]
    from packages.resume_core.templates import store

    ids = list(store.shipped_templates())
    if sorted(ids) != sorted(PUBLIC):
        raise SystemExit(f"shipped template ids differ: {sorted(ids)}")
    result = []
    for template_id in ids:
        package = store.bundled_package(template_id)
        result.append(f"{template_id} {package.revision} {package.package_hash} {package.config_hash} "
                      f"{package.original_hash}")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", type=Path, help="recorded output to compare with (absolute path)")
    args = parser.parse_args(argv)
    current = lines()
    if args.expect is None:
        print("\n".join(current))
        return 0
    expected = [line for line in args.expect.read_text(encoding="utf-8").splitlines() if line.strip()]
    if sorted(current) == sorted(expected):
        print(f"template hashes unchanged ({len(current)})")
        return 0
    for line in sorted(set(expected) - set(current)):
        print(f"- {line}")
    for line in sorted(set(current) - set(expected)):
        print(f"+ {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
