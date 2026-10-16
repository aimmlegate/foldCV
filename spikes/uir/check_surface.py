"""Check a built UIR surface without changing retained earlier evidence."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "docs/gui/handoffs/PROTOTYPE-ADOPTION"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slice", required=True)
    args = parser.parse_args()
    dist = ROOT / "apps/web/dist-uir-proof"
    html = (dist / "uir-proof.html").read_text()
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
    assert assets and all((dist / path.lstrip("/")).is_file() for path in assets)
    graph = json.loads((dist / "uir-proof-imports.json").read_text())
    assert not graph["forbidden"]
    assert "apps/web/src/rich/Editor.tsx" in graph["modules"]
    assert not any("fixtures/" in path or "prototype.js" in path or "visual/index.js" in path for path in graph["modules"])
    sheets = [path for path in assets if path.endswith(".css")]
    css = "\n".join((dist / path.lstrip("/")).read_text() for path in sheets)
    for name, expected in {"surface": "#fafaf5", "muted": "#767c6f", "accent": "#58684c"}.items():
        assert re.findall(rf"--{name}\s*:\s*([^;}}]+)", css) == [expected]
    assert ':root[data-theme' not in css and "cv-sheet" not in css
    light_entries = ["apps/web/index.html", "apps/web/uir-proof.html"]
    for name in light_entries:
        entry = (ROOT / name).read_text()
        assert 'color-scheme: light' in entry and 'data-theme="light"' in entry
        assert "foldcv-theme" not in entry and "matchMedia" not in entry
    assert not (ROOT / "apps/web/src/rich/App.tsx").exists()
    frozen = ["design/future-editor/visual", "docs/gui/handoffs/AGENT-ASSISTANT",
        "docs/gui/handoffs/PROTOTYPE-ADOPTION/fixtures", "docs/gui/handoffs/PROTOTYPE-ADOPTION/visual-extraction.json",
        "docs/gui/handoffs/PROTOTYPE-ADOPTION/source-manifest.json",
        "docs/gui/handoffs/PROTOTYPE-ADOPTION/uir00-source-manifest.json",
        "docs/gui/handoffs/PROTOTYPE-ADOPTION/uir01-source-manifest.json"]
    subprocess.run(["git", "diff", "--exit-code", "a551598", "--", *frozen], cwd=ROOT, check=True, capture_output=True)
    files = {str(path.relative_to(dist)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(dist.rglob("*")) if path.is_file()}
    result = {"status": "passed", "slice": args.slice,
        "buildSha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
        "transitiveModuleCount": len(graph["modules"]), "forbiddenImports": graph["forbidden"],
        "assets": assets, "lightEntries": light_entries, "frozenScopes": frozen}
    (HANDOFF / f"evidence/{args.slice.lower()}-build-checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: built assets, import boundary, exact palette, light entries and frozen scopes")


if __name__ == "__main__":
    main()
