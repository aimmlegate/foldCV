"""Write THIRD-PARTY-NOTICES.md: the third-party components inside the FoldCV apps, their licences and licence texts.

Usage: `.venv/bin/python tools/third_party_notices.py` with Node 22 on the PATH; `--check` only compares the committed
file with a fresh generation. Sources: the packages of `requirements-service.txt` and their dependencies as installed in
this venv (both helpers), the production dependency tree of `apps/web` (the web bundle), the crates of the Tauri shell
(`cargo metadata --offline`), and the hand-kept runtimes and assets below. Licence texts come from the packages
themselves; identical texts appear once in the appendix.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "THIRD-PARTY-NOTICES.md"
LICENCE_FILE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|COPYRIGHT)([.\-_].*)?$", re.I)
REQUIREMENTS = ("requirements.txt", "requirements-service.txt")
NOTES = {
    "pymupdf": "Used under the GNU AGPL v3 (the same licence as FoldCV, see LICENSE). Contains the MuPDF library, "
               "Copyright © Artifex Software, Inc. Source: the `pymupdf` sdist of this version on PyPI and "
               "https://mupdf.com/source.",
}


@dataclass
class Component:
    name: str
    version: str
    licence: str
    texts: list[str] = field(default_factory=list)
    note: str = ""


def licence_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.is_file() and LICENCE_FILE.match(path.name))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def python_packages() -> list[Component]:
    names = [line.split("==")[0].strip() for file in REQUIREMENTS for line in (ROOT / file).read_text().splitlines()
             if "==" in line]
    seen: dict[str, Component] = {}
    todo = list(names)
    while todo:
        name = todo.pop()
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            raise SystemExit(f"{name} is not installed in this venv; install requirements-dev.txt first")
        meta = dist.metadata
        licence = (meta.get("License-Expression") or (meta.get("License") or "").splitlines()[0:1] or [""])
        licence = licence if isinstance(licence, str) else licence[0]
        if not licence:
            licence = "; ".join(c.split("::")[-1].strip() for c in (meta.get_all("Classifier") or []) if c.startswith("License"))
        texts = [read(Path(dist.locate_file(f))) for f in (dist.files or [])
                 if ".dist-info" in str(f) and (LICENCE_FILE.match(Path(str(f)).name) or "/licenses/" in str(f))]
        seen[key] = Component(meta["Name"], dist.version, licence or "?", texts, NOTES.get(key, ""))
        for spec in dist.requires or []:
            requirement = Requirement(spec)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            todo.append(requirement.name)
    return sorted(seen.values(), key=lambda c: c.name.lower())


def web_packages() -> list[Component]:
    result = subprocess.run(["npm", "ls", "--omit=dev", "--all", "--parseable"], cwd=ROOT / "apps/web",
                            capture_output=True, text=True, check=False)
    found: dict[tuple[str, str], Component] = {}
    for line in result.stdout.split():
        directory = Path(line)
        manifest = directory / "package.json"
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("name") == "foldcv-web":
            continue
        licence = data.get("license") or ", ".join(item.get("type", "?") for item in data.get("licenses", []) if isinstance(item, dict)) or "?"
        key = (data["name"], data.get("version", "?"))
        if key not in found:
            found[key] = Component(key[0], key[1], licence, [read(p) for p in licence_files(directory)])
    if not found:
        raise SystemExit("npm ls returned nothing; run npm ci in apps/web with Node 22 on the PATH")
    return sorted(found.values(), key=lambda c: (c.name.lower(), c.version))


def crates() -> list[Component]:
    result = subprocess.run(["cargo", "metadata", "--offline", "--format-version", "1", "--locked",
                             "--manifest-path", str(ROOT / "apps/desktop-tauri/Cargo.toml")], capture_output=True,
                            text=True, check=True)
    data = json.loads(result.stdout)
    packages = {p["id"]: p for p in data["packages"]}
    nodes = {n["id"]: n for n in data["resolve"]["nodes"]}
    seen: set[str] = set()
    todo = [data["resolve"]["root"]]
    while todo:
        item = todo.pop()
        if item in seen:
            continue
        seen.add(item)
        for dep in nodes[item]["deps"]:
            if any(kind.get("kind") in (None, "normal") for kind in dep["dep_kinds"]):
                todo.append(dep["pkg"])
    components = []
    for item in seen:
        package = packages[item]
        if package["source"] is None:
            continue  # the shell itself
        directory = Path(package["manifest_path"]).parent
        components.append(Component(package["name"], package["version"], package.get("license") or "?",
                                    [read(p) for p in licence_files(directory)]))
    return sorted(components, key=lambda c: (c.name.lower(), c.version))


def hand_kept() -> list[Component]:
    base = Path(sys.base_prefix)
    python_text = [read(base / "LICENSE.txt")] if (base / "LICENSE.txt").is_file() else []
    fonts = ROOT / "skills/format-resume/assets/fonts/LICENSE.txt"
    devicon = ROOT / "skills/format-resume/assets/devicon/LICENSE"
    library = ROOT / "assets/technology-library/LICENSE"
    return [
        Component("CPython", "3.13", "PSF-2.0", python_text,
                  "The Python runtime frozen into the macOS helper and the python.org embeddable package of the Windows helper."),
        Component("PyInstaller bootloader", "6.22.3", "GPL-2.0-or-later WITH Bootloader-exception", [],
                  "The macOS helper is frozen with PyInstaller; its bootloader licence allows bundling programs under any licence."),
        Component("pywin32", "311", "PSF-style", [],
                  "Windows helper only; its licence text is `win32/License.txt` inside the helper's site-packages."),
        Component("Microsoft Visual C++ Redistributable (msvcp140.dll)", "14.44.35211.0", "Microsoft Software License Terms", [],
                  "Windows helper only; an app-local copy, which the redistributable's terms allow."),
        Component("Source Sans Pro", "", "OFL-1.1", [read(fonts)] if fonts.is_file() else [], "Fonts of the rendered resume."),
        Component("Devicon", "", "MIT", [read(devicon)] if devicon.is_file() else [], "Technology icons."),
        Component("Technology icon library", "", "MIT", [read(library)] if library.is_file() else [], "Technology icons (Devicon set)."),
        Component("WebKit (macOS), WebView2 (Windows)", "", "system component", [],
                  "The apps show their page in the system web view; nothing of it is distributed."),
    ]


def render(sections: list[tuple[str, str, list[Component]]]) -> str:
    texts: dict[str, tuple[int, str, list[str]]] = {}

    def text_id(text: str, owner: str) -> int:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest not in texts:
            texts[digest] = (len(texts) + 1, text, [])
        texts[digest][2].append(owner)
        return texts[digest][0]

    out = ["# Third-party notices", "",
           "FoldCV is free software under the GNU Affero General Public License, version 3 or any later version (see",
           "`LICENSE`). The macOS and Windows apps also contain the third-party components below, each under its own",
           "licence. Names, versions and licences are the pinned ones of this checkout; licence texts are the ones the",
           "components ship, and identical texts appear once in the appendix. Generated by `tools/third_party_notices.py`.", ""]
    for number, (title, lead, components) in enumerate(sections, 1):
        out += [f"## {number}. {title}", "", lead, "", "| Component | Version | Licence | Text | Note |", "|---|---|---|---|---|"]
        for c in components:
            ids = ", ".join(f"T{text_id(t, f'{c.name} {c.version}'.strip())}" for t in c.texts) or "—"
            out.append(f"| {c.name} | {c.version} | {c.licence.replace('|', '/')} | {ids} | {c.note} |")
        out.append("")
    out += ["## Appendix: licence texts", ""]
    for _, (number, text, owners) in sorted(texts.items(), key=lambda item: item[1][0]):
        shown = ", ".join(owners[:8]) + (f" and {len(owners) - 8} more" if len(owners) > 8 else "")
        out += [f"### T{number}", "", f"Used by: {shown}.", "", "```text", text, "```", ""]
    return "\n".join(out)


def main() -> int:
    content = render([
        ("Python packages", "The local service inside both apps: the packages of `requirements-service.txt` and their dependencies.", python_packages()),
        ("Web application", "The production dependency tree of `apps/web`, from which the page is bundled.", web_packages()),
        ("Desktop window", "The crates of the Tauri shell in `apps/desktop-tauri`.", crates()),
        ("Runtimes and assets", "Hand-kept entries for what the builds add outside the package managers.", hand_kept()),
    ])
    if "--check" in sys.argv[1:]:
        if OUTPUT.read_text(encoding="utf-8") != content:
            print("THIRD-PARTY-NOTICES.md is stale; run tools/third_party_notices.py", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_text(content, encoding="utf-8")
    print(OUTPUT, f"{OUTPUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
