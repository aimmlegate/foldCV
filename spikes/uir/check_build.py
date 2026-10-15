"""Inspect the bundled proof boundary and unchanged production entries."""

import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "docs/gui/handoffs/PROTOTYPE-ADOPTION"


def main():
    dist = ROOT / "apps/web/dist-uir-proof"
    html = (dist / "uir-proof.html").read_text()
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
    assert assets and all((dist / path.lstrip("/")).is_file() for path in assets)
    graph = json.loads((dist / "uir-proof-imports.json").read_text())
    assert not graph["forbidden"] and "apps/web/src/rich/Editor.tsx" in graph["modules"]
    assert not any("fixtures/" in path or "prototype.js" in path or "visual/index.js" in path for path in graph["modules"])
    sheets = [path for path in assets if path.endswith(".css")]
    assert len(sheets) == 1 and "uirProof-" in sheets[0]
    css = (dist / sheets[0].lstrip("/")).read_text()
    assert re.findall(r"--surface\s*:\s*([^;}]+)", css) == ["#fafaf5"]
    assert re.findall(r"--muted\s*:\s*([^;}]+)", css) == ["#767c6f"]
    assert re.findall(r"--accent\s*:\s*([^;}]+)", css) == ["#58684c"]
    assert "cv-sheet" not in css and ':root[data-theme' not in css
    assert "preflight" not in (ROOT / "apps/web/src/workbench/styles/utilities.css").read_text()
    assert not (ROOT / "apps/web/dist/uir-proof.html").exists()
    untouched = ["apps/web/index.html", "apps/web/next.html", "apps/web/legacy.html", "apps/web/src/next/main.tsx",
        "apps/web/src/rich/App.tsx", "apps/web/tests/shell.spec.ts", "tests/requirements.json",
        "apps/web/src/assistant", "docs/gui/handoffs/AGENT-ASSISTANT", "design/future-editor/visual"]
    subprocess.run(["git", "diff", "--exit-code", "b9518c9a7b6b85ddb3d54109fe3a96d2eec14cc9", "--", *untouched], cwd=ROOT, check=True, capture_output=True)
    files = {str(path.relative_to(dist)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(dist.rglob("*")) if path.is_file()}
    result = {"status": "passed", "buildSha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
        "proofHtml": "apps/web/dist-uir-proof/uir-proof.html", "assets": assets, "stylesheets": sheets,
        "transitiveModuleCount": len(graph["modules"]), "forbiddenImports": graph["forbidden"],
        "palette": {"surface": "#fafaf5", "muted": "#767c6f", "accent": "#58684c"},
        "ordinaryBuildOmitsProof": True, "untouchedScopes": untouched,
        "graphSha256": hashlib.sha256((dist / "uir-proof-imports.json").read_bytes()).hexdigest()}
    (HANDOFF / "evidence/uir01-build-checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: bundled proof assets/import graph, single prototype palette, no old CSS/Preflight/demo runtime; normal entries and AG scopes unchanged")


if __name__ == "__main__": main()
