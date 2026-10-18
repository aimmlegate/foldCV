"""Audit a private PDF corpus without inference or candidate text in the summary."""

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

import pymupdf

from packages.resume_core.extraction.parser import extract
from packages.resume_core.gui_normalization import canonical_source
from packages.resume_core.import_agent import source_parts, assemble_agent_import
from packages.resume_core.import_content import source_paragraphs, update_content
from packages.resume_core.models.importing import ImportContent, ImportDraft, ImportRead
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.rich_presentation import authored_text
from resume_api.importer.session import ImportDispatcher


async def check(args):
    report = []
    args.views.mkdir(parents=True, exist_ok=True)
    for case in json.loads(args.inputs.read_text()):
        raw = (ROOT / case["copy"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == case["sha256"]
        with pymupdf.open(stream=raw, filetype="pdf") as document:
            blocks = [[block for block in page.get_text("blocks", sort=False) if block[6] == 0]
                      for page in document]
        expected_lines = Counter((page, line) for page, items in enumerate(blocks, 1)
                                 for block in items for line in block[4].splitlines(keepends=True))
        result = extract(raw, case["name"])
        actual_lines = Counter((unit.location.page, line) for unit in result.units
                               for line in unit.text.splitlines(keepends=True))
        assert actual_lines == expected_lines, case["id"]
        first = min(blocks[0], key=lambda block: (block[1], block[0]))[4].splitlines()[0]
        assert result.units[0].text.splitlines()[0] == first, case["id"]
        source = canonical_source(result)
        parts = source_parts([source])
        paragraphs = source_paragraphs([source], parts)
        draft = ImportDraft(sourceSha256="1" * 64, skillSha256="2" * 64, runId="offline")
        draft = update_content(draft, ImportContent(sections=[{"category": "other",
            "refs": [f"p1-p{len(paragraphs)}"]}]), paragraphs, parts)
        coordinator = SimpleNamespace(paragraphs=paragraphs, guard=lambda: None, load=lambda: draft)
        dispatcher = ImportDispatcher(coordinator)
        reads, offset = [], 0
        while offset is not None:
            reply = await dispatcher.call("read_import", ImportRead(offset=offset))
            assert "error" not in reply
            assert len(json.dumps(reply, ensure_ascii=False).encode()) < 64 * 1024
            reads.append(reply)
            offset = reply["nextOffset"]
        assert dispatcher.read_keys == {paragraph.ref for paragraph in paragraphs}
        view = "".join(reply["text"] for reply in reads)
        (args.views / f'{case["id"]}.txt').write_text(view)
        (args.views / f'{case["id"]}.json').write_text(result.model_dump_json(by_alias=True, indent=2))
        selected = args.selected / case["id"] / "selected.json"
        workspace = WorkspaceV6.model_validate(json.loads(selected.read_text())["workspace"])
        workspace.pre_draft.sources = [source]
        workspace.pre_draft.selected_source_id = source.id
        draft.finished = True
        project = assemble_agent_import(workspace, draft)
        expected = Counter((part.evidence["unitId"], part.text) for part in parts if part.text.strip())
        actual = Counter((span.unit_id, span.text) for block in project.document.blocks()
                         for link in block.provenance if link.kind == "source"
                         for span in link.evidence if span.text.strip())
        assert actual == expected
        assert "".join(authored_text(block) for block in project.document.blocks()) == "".join(
            paragraph.text for paragraph in paragraphs if paragraph.text.strip())
        report.append({"fixture": case["id"], "sha256": case["sha256"], "pages": result.page_count,
            "textLines": sum(expected_lines.values()), "missingLines": 0, "extraLines": 0,
            "firstPageHeadingFirst": True, "paragraphs": len(paragraphs),
            "paragraphsWithHints": sum(bool(p.hints) for p in paragraphs),
            "uncertainLayoutFragments": sum(bool(u.structure and u.structure.layout_uncertain) for u in result.units),
            "sourceReadCalls": len(reads), "sourceReadBytes": len(view.encode()),
            "missingEvidenceSpans": 0, "repeatedEvidenceSpans": 0,
            "editableBlocks": len(list(project.document.blocks())), "modelCalls": 0})
    args.summary.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"files": len(report), "lostLines": 0, "lostEvidenceSpans": 0, "modelCalls": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--selected", type=Path, required=True, help="Directory of saved input workspaces by fixture ID")
    parser.add_argument("--summary", type=Path, required=True)
    asyncio.run(check(parser.parse_args()))
