"""Assemble the Windows helper of the desktop zip on any build host: the python.org embeddable CPython, the service's
win_amd64 wheels and the checkout files the service reads, in the layout `apps/desktop` starts.

Usage: `<build python 3.13> tools/desktop/build_windows_helper.py <empty work directory>`; prints the helper path.
Build the frontend first. Downloads are kept in .tools/windows and checked against the pins below. PyInstaller cannot
build for Windows on another system, so nothing here runs Windows code; the zip is checked on Windows (CI).

Layout: python/ (interpreter, its ._pth and the C++ runtime), site-packages/, app/ (checkout paths, so `Path(__file__)`
lookups and source hashes work as in the checkout, with unchecked-hash .pyc files next to the sources).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import certifi

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".tools/windows"
PYTHON = ("https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip", 11441267,
          "9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38")
# PyMuPDF needs msvcp140.dll, which neither its wheel nor the embeddable Python carries and Windows may lack; it is
# taken from Microsoft's redistributable (14.44.35211.0), which allows app-local copies.
VC_REDIST = ("https://download.visualstudio.microsoft.com/download/pr/990c720a-46ce-4dc7-87b9-c2eb615d34b9/"
             "CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe", 25635768,
             "cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b")
MSVCP140 = "0f885b509a685d2bbfa652fed26b5fb31d88fbdab0a978c641d1c7b8aa460aa9"
# mcp imports pywin32 on Windows; pip on another host leaves out dependencies marked for win32.
WINDOWS_ONLY = ("pywin32==311",)
# Read at run time; kept at their checkout paths (as in build_helper.py), next to the two source trees.
DATA = ("apps/web/dist", "templates", "skills/format-resume/SKILL.md", "skills/format-resume/references",
        "skills/format-resume/assets", "assets/technology-library", "packages/resume_core/default_rules.md",
        "requirements.txt", "packaging/helper_entry.py")
SOURCES = ("packages", "services/api/src/resume_api")
# sys.path of the helper; the interpreter ignores PYTHONPATH and the registry when this file exists.
PATHS = ("python313.zip", ".", r"..\app", r"..\app\services\api\src", r"..\site-packages",
         r"..\site-packages\win32", r"..\site-packages\win32\lib", r"..\site-packages\Pythonwin")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(url: str, size: int, digest: str) -> Path:
    target = CACHE / url.rsplit("/", 1)[1]
    if not target.is_file() or target.stat().st_size != size or sha256(target) != digest:
        CACHE.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(url, context=context, timeout=60) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
        if partial.stat().st_size != size or sha256(partial) != digest:
            partial.unlink()
            raise SystemExit("Checksum mismatch: " + url)
        partial.replace(target)
    return target


def tar() -> str:
    # bsdtar reads cabinets; Git Bash puts GNU tar first on PATH on Windows.
    return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/tar.exe") if os.name == "nt" else "tar"


def cabinets(data: bytes):
    start = 0
    while (offset := data.find(b"MSCF\0\0\0\0", start)) >= 0:
        size = int.from_bytes(data[offset + 8:offset + 12], "little")
        start = offset + 4
        if 36 <= size <= len(data) - offset:
            yield data[offset:offset + size]


def runtime_dll(installer: Path, work: Path) -> bytes:
    """msvcp140.dll from the redistributable: its burn bundle carries cabinets inside cabinets."""
    pending, seen = [installer.read_bytes()], 0
    while pending and seen < 64:
        data = pending.pop()
        for cabinet in cabinets(data):
            seen += 1
            folder = Path(tempfile.mkdtemp(dir=work))
            (folder / "archive.cab").write_bytes(cabinet)
            if subprocess.run([tar(), "-xf", "archive.cab"], cwd=folder, capture_output=True).returncode:
                continue
            for item in folder.iterdir():
                if item.name == "msvcp140.dll_amd64":
                    raw = item.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != MSVCP140:
                        raise SystemExit("msvcp140.dll checksum mismatch")
                    return raw
                if item.name != "archive.cab" and item.read_bytes()[:4] == b"MSCF":
                    pending.append(item.read_bytes())
    raise SystemExit("msvcp140.dll not found in the redistributable")


def copy_sources(app: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", ".DS_Store")
    for name in SOURCES:
        shutil.copytree(ROOT / name, app / name, ignore=ignore)
    for name in DATA:
        source, target = ROOT / name, app / name
        if source.is_dir():
            shutil.copytree(source, target, ignore=ignore, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def build(work: Path) -> Path:
    if work.exists() and any(work.iterdir()):
        raise SystemExit("Use an empty work directory")
    if sys.version_info[:2] != (3, 13):
        raise SystemExit("Build with Python 3.13: the .pyc files must match the embedded interpreter")
    if not (ROOT / "apps/web/dist/index.html").is_file():
        raise SystemExit("Build the frontend first: npm run build in apps/web")
    helper, scratch = work / "helper", work / "scratch"
    python, site, app = helper / "python", helper / "site-packages", helper / "app"
    scratch.mkdir(parents=True)
    with zipfile.ZipFile(fetch(*PYTHON)) as archive:
        archive.extractall(python)
    (python / "python313._pth").write_text("\n".join(PATHS) + "\n", encoding="ascii")
    (python / "msvcp140.dll").write_bytes(runtime_dll(fetch(*VC_REDIST), scratch))
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--no-compile",
                    "--target", str(site), "--platform", "win_amd64", "--python-version", "3.13",
                    "--implementation", "cp", "--abi", "cp313", "--only-binary=:all:",
                    "-r", str(ROOT / "requirements-service.txt"), *WINDOWS_ONLY], check=True)
    # Launchers pip wrote for the build host.
    shutil.rmtree(site / "bin", ignore_errors=True)
    # pywin32's own setup would copy these next to the interpreter; without `site` nothing else loads them.
    for dll in (site / "pywin32_system32").glob("*.dll"):
        shutil.copy2(dll, python / dll.name)
    copy_sources(app)
    for tree in (app, site):
        # Sources stay next to the .pyc files: the service hashes some of them.
        result = subprocess.run([sys.executable, "-m", "compileall", "-q", "-j", "0", "--invalidation-mode",
                                 "unchecked-hash", str(tree)], capture_output=True, text=True)
        if result.returncode and tree == app:
            raise SystemExit(result.stdout + result.stderr)
    shutil.rmtree(scratch)
    for required in (python / "python.exe", site / "fastapi", site / "pymupdf", site / "win32" / "win32api.pyd",
                     app / "packaging/helper_entry.py", app / "apps/web/dist/index.html"):
        if not required.exists():
            raise SystemExit("Missing from the helper: " + str(required.relative_to(helper)))
    return helper


if __name__ == "__main__":
    print(build(Path(sys.argv[1]).resolve()))
