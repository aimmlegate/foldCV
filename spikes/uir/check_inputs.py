"""Verify retained fixture provenance without browser scenarios or providers."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from packages.resume_core.rich_archive import open_rich_archive
from packages.resume_core.rich_presentation import authored_text


def main():
    folder = ROOT / "docs/gui/handoffs/PROTOTYPE-ADOPTION/fixtures"
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, value in manifest["files"].items():
        data = (folder / name).read_bytes()
        assert len(data) == value["bytes"] and hashlib.sha256(data).hexdigest() == value["sha256"], name
    mapping = json.loads((folder / "block-mapping.json").read_text())
    workspace, originals, _, _ = open_rich_archive((folder / "structured.foldcv").read_bytes(), "uir-verified")
    blocks = {block.id: block for block in workspace.project.document.blocks()}
    assert len(mapping["rows"]) == 27 and len({row["prototypeKind"] for row in mapping["rows"]}) == 8
    for row in mapping["rows"]:
        block = blocks[row["canonicalId"]]
        assert block.type == row["canonicalType"] and authored_text(block) == row["visibleText"], row
        bindings = [{key: span.model_dump(by_alias=True)[key] for key in ("bindingId", "recordId", "fieldKey")}
            for span in block.content if span.type == "fact_field"]
        assert bindings == row["bindings"]
        if row["prototypeKind"] == "caption": assert all(item["fieldKey"].startswith("period:") for item in bindings)
        if row["prototypeKind"] == "focus":
            assert any(child.id == block.id for section in blocks.values() if section.type == "section" and section.props.presentation == "focus" for child in section.children)
    assert next(r for r in workspace.project.facts.records if r.kind == "education").qualification.value is None
    fresh, imported_originals, _, _ = open_rich_archive((folder / "fresh-import.foldcv").read_bytes(), "uir-fresh-verified")
    assert not fresh.project.document.regions[0].blocks and not fresh.project.document.regions[1].blocks
    assert list(imported_originals.values()) == [(folder / "import-source.txt").read_bytes()]
    units = sorted(fresh.project.sources[0].units, key=lambda unit: unit.order)
    assert [authored_text(block) for block in fresh.project.document.regions[2].blocks] == [unit.text for unit in units]
    states = json.loads((folder / "reference-states.json").read_text())
    for fixture in ("structured", "fresh-import"):
        assert {(r["viewport"]["width"], r["viewport"]["height"]) for r in states["states"] if r["fixture"] == fixture and r["variant"] == "baseline"} == {(1440,900),(1280,900),(1024,900),(390,844)}
    for state in states["states"]:
        shell, viewport = state["boxes"]["shell"], state["viewport"]
        gap = 7 if viewport["width"] <= 600 else 16
        assert shell["width"] == min(viewport["width"] - 2 * gap, 1600)
        assert shell["height"] == viewport["height"] - 2 * gap and shell["y"] == gap
        assert state["fonts"] == "loaded" and state["zoom"] == 1
        assert hashlib.sha256((ROOT / state["screenshot"]).read_bytes()).hexdigest() == state["screenshotSha256"]
    print("PASS: fixture hashes, 27 block/field mappings after reopen, literal import, eight baselines and three panel/selection references")


if __name__ == "__main__": main()
