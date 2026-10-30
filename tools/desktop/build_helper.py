"""Freeze the macOS helper, the local service with its worker modes, into `FoldCV Helper.app` with PyInstaller.

Usage: `<build python> tools/desktop/build_helper.py <empty work directory>`; prints the built app path. Build
the frontend first. Data files keep their checkout paths inside the bundle, and every module also keeps its source
file next to it, so `Path(__file__)` lookups and source hashes work as in the checkout.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
# Read at run time; kept at their checkout paths.
DATA = ("apps/web/dist", "templates", "skills/format-resume/SKILL.md", "skills/format-resume/references",
        "skills/format-resume/assets", "assets/technology-library", "packages/resume_core/default_rules.md",
        "requirements.txt")
# The captured DOCX renderer identity reads these installed versions.
METADATA = ("fonttools", "python-docx", "lxml", "pydantic", "jsonschema", "PyYAML", "PyMuPDF", "Pillow")
# uvicorn picks its protocol modules by name.
HIDDEN = ("uvicorn.logging", "uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.on")


def spec(work: Path, version: str) -> str:
    skills = ROOT / "services/api/src/resume_api/assistant/skills"
    datas = [(str(ROOT / name), str(Path(name).parent) if (ROOT / name).is_file() else name) for name in DATA]
    datas += [(str(path), "resume_api/assistant/skills") for path in sorted(skills.glob("*.md"))]
    # python-docx opens docx/parts/../templates, so the parts directory must exist on disk.
    keep = work / "docx-parts.txt"
    keep.write_text("Keeps the python-docx parts directory in the bundle.\n", encoding="utf-8")
    datas.append((str(keep), "docx/parts"))
    return f"""from PyInstaller.utils.hooks import collect_submodules, copy_metadata
datas = {datas!r} + [item for name in {METADATA!r} for item in copy_metadata(name)]
hidden = collect_submodules("packages") + collect_submodules("resume_api") + {list(HIDDEN)!r}
a = Analysis([{str(ROOT / "packaging/helper_entry.py")!r}], pathex=[{str(ROOT)!r}, {str(ROOT / "services/api/src")!r}],
    datas=datas, hiddenimports=hidden, excludes=["tkinter", "pytest", "tests", "tools"],
    module_collection_mode={{"packages": "pyz+py", "resume_api": "pyz+py"}}, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="foldcv-helper", console=True, strip=False, upx=False,
    target_arch="arm64", codesign_identity=None)
payload = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="foldcv-helper")
app = BUNDLE(payload, name="FoldCV Helper.app", bundle_identifier="invalid.foldcv.local.helper",
    version={version!r}, info_plist={{"LSBackgroundOnly": True}})
"""


def build(work: Path) -> Path:
    if work.exists() and any(work.iterdir()):
        raise SystemExit("Use an empty work directory")
    if not (ROOT / "apps/web/dist/index.html").is_file():
        raise SystemExit("Build the frontend first: npm run build in apps/web")
    work.mkdir(parents=True, exist_ok=True)
    version = json.loads((ROOT / "apps/desktop/package.json").read_text(encoding="utf-8"))["version"]
    (work / "helper.spec").write_text(spec(work, version), encoding="utf-8")
    environment = {**os.environ, "PYTHONPATH": f"{ROOT}:{ROOT / 'services/api/src'}", "PYTHONDONTWRITEBYTECODE": "1",
                   "PYINSTALLER_CONFIG_DIR": str(work / "cache")}
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
                    "--workpath", str(work / "build"), "--distpath", str(work / "dist"), str(work / "helper.spec")],
                   cwd=ROOT, env=environment, check=True)
    return work / "dist/FoldCV Helper.app"


if __name__ == "__main__":
    print(build(Path(sys.argv[1]).resolve()))
