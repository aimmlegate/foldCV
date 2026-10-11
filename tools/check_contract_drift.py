"""Fail when checked-in schemas or TypeScript types differ from Python models."""

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"


def main() -> None:
    files = sorted((ROOT / "contracts" / "json-schema").glob("*.json"))
    files += sorted((WEB / "src" / "contracts" / "generated").glob("*.ts"))
    files.append(ROOT / "contracts" / "technology-catalog.json")
    if len(files) != 35:
        raise SystemExit("expected seventeen schema/type pairs and one catalog")
    before = {path: path.read_bytes() for path in files}
    subprocess.run(["npm", "run", "contracts:generate"], cwd=WEB, env=os.environ.copy(), check=True)
    changed = [str(path.relative_to(ROOT)) for path in files if path.read_bytes() != before[path]]
    if changed:
        raise SystemExit("contract generation drift: " + ", ".join(changed))
    print("35 generated contract and catalog files match Python models")


if __name__ == "__main__":
    main()
