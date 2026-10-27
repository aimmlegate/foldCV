"""Fail when checked-in schemas or TypeScript types differ from Python models."""

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.generate_contracts import CONTRACTS

WEB = ROOT / "apps" / "web"
PAIR_COUNT = len(CONTRACTS)


def generated_files() -> set[Path]:
    files = {path for directory in (ROOT / "contracts/json-schema", WEB / "src/contracts/generated")
             for path in directory.rglob("*") if path.is_file()}
    source = ROOT / "contracts/template-source.schema.json"
    if source.is_file():
        files.add(source)
    return files


def generated_directories() -> set[Path]:
    return {path for directory in (ROOT / "contracts/json-schema", WEB / "src/contracts/generated")
            for path in directory.rglob("*") if path.is_dir()}


def main() -> None:
    before = {path: path.read_bytes() for path in generated_files()}
    directories = generated_directories()
    if len(before) != PAIR_COUNT * 2 + 1:
        raise SystemExit(f"expected {PAIR_COUNT} schema/type pairs and the template source schema")
    try:
        subprocess.run(["npm", "run", "contracts:generate"], cwd=WEB, env=os.environ.copy(), check=True)
        after = {path: path.read_bytes() for path in generated_files()}
        changed = [str(path.relative_to(ROOT)) for path in sorted(before.keys() | after.keys())
                   if before.get(path) != after.get(path)]
        if changed:
            raise SystemExit("contract generation drift: " + ", ".join(changed))
    except BaseException:
        for path in generated_files() - before.keys():
            path.unlink()
        for path, data in before.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for directory in sorted(generated_directories() - directories, key=lambda path: len(path.parts), reverse=True):
            directory.rmdir()
        raise
    print(f"{PAIR_COUNT * 2 + 1} generated contract and template source files match Python models")


if __name__ == "__main__":
    main()
