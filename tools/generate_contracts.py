"""Export deterministic JSON Schemas from the Python contract authority."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.resume_core.models.contracts import ArchiveManifest, Project, Proposal, TemplateManifest, ZipManifest
from packages.resume_core.rendering.models import RenderRequest
from packages.resume_core.rendering.preparation import PrepareRequest
from packages.resume_core.extraction.models import ExtractResult
from packages.resume_core.normalization import FactRequest, FactSheet, SemanticProposal
from packages.resume_core.drafting import DraftRequest, DraftProposal, DraftResult
from packages.resume_core.rewriting import RewritePreflightFailure, RewriteRequest, RewriteProposal, RewriteResult
from packages.resume_core.technologies import CATALOG, CATALOG_VERSION
from packages.resume_core.models.recovery import RECOVERY_CONTRACTS
from packages.resume_core.gui_normalization import GUI_NORMALIZATION_CONTRACTS

OUT = ROOT / "contracts" / "json-schema"
RECOVERY_MODELS = {**RECOVERY_CONTRACTS, **GUI_NORMALIZATION_CONTRACTS}


def main() -> None:
    if sys.argv[1:] == ["--clean-types"]:
        for path in sorted((ROOT / "apps" / "web" / "src" / "contracts" / "generated").glob("*.ts")):
            text = path.read_text(encoding="utf-8")
            marker = "export "
            start = text.find(marker)
            if start < 0:
                raise ValueError(f"missing declarations in {path}")
            path.write_text(text[start:], encoding="utf-8")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for name, model in {
        "project": Project,
        "proposal": Proposal,
        "template": TemplateManifest,
        "zip_manifest": ZipManifest,
        "archive_manifest": ArchiveManifest,
        "render_request": RenderRequest,
        "prepare_request": PrepareRequest,
        "extract_result": ExtractResult,
        "fact_request": FactRequest,
        "fact_sheet": FactSheet,
        "semantic_proposal": SemanticProposal,
        "draft_request": DraftRequest,
        "draft_proposal": DraftProposal,
        "draft_result": DraftResult,
        "rewrite_request": RewriteRequest,
        "rewrite_proposal": RewriteProposal,
        "rewrite_result": RewriteResult,
        "rewrite_preflight_failure": RewritePreflightFailure,
        **RECOVERY_MODELS,
    }.items():
        schema = model.model_json_schema(mode="validation")
        (OUT / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    (ROOT / "contracts" / "technology-catalog.json").write_text(
        json.dumps({"version": CATALOG_VERSION, "entries": [
            {"canonicalId": item.canonical_id, "aliases": list(item.aliases)} for item in CATALOG
        ]}, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
