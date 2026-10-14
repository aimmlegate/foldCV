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
from packages.resume_core.gui_drafting import GUI_DRAFT_CONTRACTS
from packages.resume_core.gui_projects import GUI_PROJECT_CONTRACTS
from packages.resume_core.gui_rewriting import GUI_REWRITE_CONTRACTS
from packages.resume_core.gui_exports import GUI_EXPORT_CONTRACTS
from packages.resume_core.gui_reconciliation import GUI_RECONCILE_CONTRACTS
from packages.resume_core.models.rich_document import RichDocumentV1
from packages.resume_core.models.rich_facts import WorkingFacts
from packages.resume_core.models.rich_mutations import RichMutation, RichSelection, DateCascadeProposal
from packages.resume_core.models.rich_workspace import ProjectV5, WorkspaceV6, ArchiveManifestV6, AssetReservation
from packages.resume_core.rich_api import RichProjectResponse, ImageSessionRequest, ImageUploadCapture
from packages.resume_core.rich_sync import RichCompletionRequest, RichRewriteRequest, RichRewriteProposal, RichReconcileProposal, RichSyncDisposition

OUT = ROOT / "contracts" / "json-schema"
RICH_CONTRACTS = {
    "rich_completion_request": RichCompletionRequest, "rich_rewrite_request": RichRewriteRequest,
    "rich_rewrite_proposal": RichRewriteProposal, "rich_reconcile_proposal": RichReconcileProposal,
    "rich_sync_disposition": RichSyncDisposition,
    "rich_document_v1": RichDocumentV1, "working_facts": WorkingFacts,
    "rich_mutation": RichMutation, "rich_selection": RichSelection,
    "date_cascade_proposal": DateCascadeProposal, "project_v5": ProjectV5,
    "workspace_v6": WorkspaceV6, "archive_manifest_v6": ArchiveManifestV6,
    "asset_reservation": AssetReservation,
    "rich_project_response": RichProjectResponse,
    "image_session_request": ImageSessionRequest, "image_upload_capture": ImageUploadCapture,
}
RECOVERY_MODELS = {**RECOVERY_CONTRACTS, **GUI_NORMALIZATION_CONTRACTS, **GUI_DRAFT_CONTRACTS, **GUI_PROJECT_CONTRACTS, **GUI_REWRITE_CONTRACTS, **GUI_EXPORT_CONTRACTS, **GUI_RECONCILE_CONTRACTS, **RICH_CONTRACTS}


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
