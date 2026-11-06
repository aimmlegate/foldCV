"""Pack the Windows app of the Tauri shell into a portable zip: one folder named after the app with the shell's exe
and, next to it, the helper it starts. No installer, no signature.

Usage: `python tools/desktop/package_windows_tauri.py <foldcv-beta.exe> <helper directory> <new output directory>`;
prints the zip path. The exe comes from cargo on Windows (the CI workflow Windows), the helper from
build_windows_helper.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package(shell: Path, helper: Path, output: Path) -> Path:
    for part in ("python/python.exe", "app/packaging/helper_entry.py"):
        if not (helper / part).is_file():
            raise SystemExit(f"The helper directory has no {part}")
    if output.exists():
        raise SystemExit("The output directory must not exist yet")
    config = json.loads((ROOT / "apps/desktop-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    name, version = config["productName"], config["version"]
    lock = (ROOT / "apps/desktop-tauri/Cargo.lock").read_text(encoding="utf-8")
    tauri = re.search(r'^name = "tauri"\nversion = "([^"]+)"$', lock, re.MULTILINE)[1]
    output.mkdir(parents=True)
    archive = output / f"{name.replace(' ', '-')}-{version}-win-x64.zip"
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(shell, f"{name}/{name}.exe")
        bundle.write(ROOT / "LICENSE", f"{name}/LICENSE.txt")
        bundle.write(ROOT / "THIRD-PARTY-NOTICES.md", f"{name}/THIRD-PARTY-NOTICES.md")
        for path in sorted(helper.rglob("*")):
            bundle.write(path, f"{name}/helper/{path.relative_to(helper).as_posix()}")
    info = {"application": name, "version": version, "commit": git("rev-parse", "HEAD"),
            "dirty": git("status", "--porcelain") != "", "shell": "tauri", "tauri": tauri, "platform": "win32-x64",
            "zip": archive.name, "zipBytes": archive.stat().st_size, "zipSha256": sha256(archive), "signature": "none",
            "builtAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")}
    (output / "build-info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    return archive


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: package_windows_tauri.py <shell exe> <helper directory> <new output directory>")
    print(package(*(Path(argument).resolve() for argument in sys.argv[1:])))
