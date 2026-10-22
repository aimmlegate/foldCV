"""Validate or explicitly activate a local configurable template."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.resume_core.storage import StorageFailure
from packages.resume_core.templates.compiler import compile_template
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import TemplateStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("validate", "activate"):
        command = actions.add_parser(name)
        command.add_argument("path", type=Path)
        if name == "activate": command.add_argument("--store-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        package = compile_template(args.path)
        if args.action == "activate": TemplateStore(args.store_root).activate(package)
    except (OSError, ValueError, SchemaFailure, StorageFailure) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"{args.action}: {package.id}@{package.revision} {package.package_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
