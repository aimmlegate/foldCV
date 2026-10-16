"""Verify exact UI artifacts against their isolated canonical projects."""

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from packages.resume_core.rich_archive import open_rich_archive
from packages.resume_core.rich_project_store import RichProjectStore


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--slice", required=True); args = parser.parse_args()
    root = args.root.resolve()
    assert root.parent == Path("/private/tmp") and root.name.startswith("foldcv-uir-")
    handoff = ROOT / "docs/gui/handoffs/PROTOTYPE-ADOPTION/evidence"
    packet = json.loads((handoff / f"{args.slice.lower()}-t3.json").read_text())
    projects, errors, _ = RichProjectStore(root / "data").load_all(); assert not errors
    results = []
    for expected in packet["artifactsExpected"]:
        name = expected["download"]; assert Path(name).name == name
        data = (root / "downloads" / name).read_bytes()
        assert len(data) == expected["bytes"] and hashlib.sha256(data).hexdigest() == expected["sha256"]
        identifier = expected["projectId"]
        workspace, originals, artifacts, images = projects[identifier]; assert workspace.project
        if name.endswith(".foldcv"):
            reopened, source_bytes, _, image_bytes = open_rich_archive(data, "uir-artifact-check")
            assert reopened.project.document == workspace.project.document
            assert reopened.project.facts == workspace.project.facts
            assert reopened.project.sources == workspace.project.sources
            assert source_bytes == {key[1]: value for key, value in originals.items()}
            assert image_bytes == {key[1]: value for key, value in images.items()}
        else:
            assert name.endswith(".docx")
            assert data == artifacts[(identifier, workspace.project.renders[-1].id)]
            with ZipFile(BytesIO(data)) as archive:
                xml = archive.read("word/document.xml").decode()
                assert "UIR04 table" in xml and "Clearer:" in xml and "UIR04 synthetic image" in xml
                assert "https://example.com/uir04" in archive.read("word/_rels/document.xml.rels").decode()
                media = [archive.read(path) for path in archive.namelist() if path.startswith("word/media/")]
                assert all(blob in media for blob in images.values())
        target = handoff / f"{args.slice.lower()}-{name}"; target.write_bytes(data)
        results.append({**expected, "path": str(target.relative_to(ROOT)), "verifiedExact": True})
    (handoff / f"{args.slice.lower()}-artifacts.json").write_text(json.dumps(results, indent=2) + "\n")
    print("PASS: exact UI hashes, portable document/facts/source/image identity and latest editable DOCX content")


if __name__ == "__main__":
    main()
