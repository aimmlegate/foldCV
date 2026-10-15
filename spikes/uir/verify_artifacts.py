"""Retain the exact UI download artifacts from the owned canonical store."""

import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.gui_archive_zip import read_zip
from packages.resume_core.rich_project_store import RichProjectStore


def main():
    handoff = ROOT / "docs/gui/handoffs/PROTOTYPE-ADOPTION"
    packet = json.loads((handoff / "evidence/uir01-t3.json").read_text())
    loaded, errors, _ = RichProjectStore(Path("/private/tmp/foldcv-uir-20261015/data")).load_all()
    assert not errors
    results = []
    for name in ("structured", "fresh"):
        proof = packet[name]
        identifier = proof.get("final", proof["saved"])["projectId"]
        workspace, originals, artifacts, images = loaded[identifier]
        assert workspace.project
        expected = {entry["mime"]: entry for entry in proof["downloads"]}
        snapshot = workspace.project.renders[-1]
        docx = artifacts[(identifier, snapshot.id)]
        regenerated = export_rich_archive(workspace,
            {key[1]: value for key, value in originals.items()},
            {key[1]: value for key, value in artifacts.items()},
            {key[1]: value for key, value in images.items()})
        archive = Path(f"/private/tmp/foldcv-uir-20261015/downloads/{name}.foldcv").read_bytes()
        assert read_zip(archive) == read_zip(regenerated), "Portable members changed beyond ZIP timestamps"
        assert Path(f"/private/tmp/foldcv-uir-20261015/downloads/{name}.docx").read_bytes() == docx
        retained = {}
        for extension, mime, data in [("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx),
                ("foldcv", "application/vnd.foldcv.project+zip", archive)]:
            value = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            assert value == {key: expected[mime][key] for key in ("bytes", "sha256")}, (name, extension, value, expected[mime])
            target = handoff / f"evidence/uir01-{name}-edited.{extension}"
            target.write_bytes(data); retained[extension] = {"path": str(target.relative_to(ROOT)), **value}
        reopened, copied_sources, _, copied_images = open_rich_archive(archive, "uir-artifact-verify")
        assert reopened.project.document == workspace.project.document
        assert reopened.project.facts == workspace.project.facts
        assert copied_sources == {key[1]: value for key, value in originals.items()}
        assert copied_images == {key[1]: value for key, value in images.items()}
        with ZipFile(BytesIO(docx)) as zipped:
            xml = zipped.read("word/document.xml").decode()
            assert ("Ячейка UIR01" if name == "structured" else "Импорт UIR01") in xml
            assert "Проверка UIR01." in xml if name == "structured" else "Алексей Соколов" in xml
            assert any(path.startswith("word/media/") for path in zipped.namelist())
        results.append({"fixture": name, "projectId": identifier, "uiDownloadHashesExact": True,
            "portableDocumentExact": True, "portableFactsExact": True, "originalSourcesExact": True,
            "imagesExact": True, "docxTextAndImagePresent": True, "artifacts": retained})
    (handoff / "evidence/uir01-artifacts.json").write_text(json.dumps(results, indent=2) + "\n")
    print("PASS: exact UI DOCX/portable blobs retained; both archives preserve document, facts, sources and image identities")


if __name__ == "__main__": main()
