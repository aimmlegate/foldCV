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
from packages.resume_core.text_rewrite import RichRewriteEditRequest
from packages.resume_core.rich_panel import RichPanelRequest, RichPanelSyncRequest, RichPanelProposal
from packages.resume_core.rich_timeline import TimelineReport, CascadeRequest, CascadeApplyRequest
from packages.resume_core.models.agent import AGENT_CONTRACTS
from packages.resume_core.models.assistant_capabilities import ASSISTANT_CAPABILITY_CONTRACTS
from packages.resume_core.models.background import BACKGROUND_CONTRACTS
from packages.resume_core.models.connection import CliInstallationPayload
from packages.resume_core.templates.models import TemplateDefinition, TemplatePackage
from packages.resume_core.models.template_document import RichDocumentV2
from packages.resume_core.models.template_facts import WorkingFactsV2
from packages.resume_core.models.template_import import ImportOperation, StartTemplateImportV1, ResumeTemplateImportV1
from packages.resume_core.models.template_render import TemplateRenderRequestV1, TemplateExportRequestV1, TemplateSnapshotIdentity
from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.models.template_workspace import ProjectV6, WorkspaceV7, ArchiveManifestV7
from packages.resume_core.template_api import TemplateProjectResponseV1, TemplatePresentationV1
from packages.resume_core.models.template_writer import TEMPLATE_WRITER_CONTRACTS
from packages.resume_core.models.template_authoring import TEMPLATE_AUTHORING_CONTRACTS
from packages.resume_core.models.canonical_patch import CanonicalPatchV1
from packages.resume_core.models.template_delta import TemplatePreparedEditDeltaV1

OUT = ROOT / "contracts" / "json-schema"
RICH_CONTRACTS = {
    "timeline_report": TimelineReport, "cascade_request": CascadeRequest, "cascade_apply_request": CascadeApplyRequest,
    "rich_panel_request": RichPanelRequest, "rich_panel_sync_request": RichPanelSyncRequest, "rich_panel_proposal": RichPanelProposal,
    "rich_completion_request": RichCompletionRequest, "rich_rewrite_request": RichRewriteRequest,
    "rich_rewrite_proposal": RichRewriteProposal, "rich_reconcile_proposal": RichReconcileProposal,
    "rich_sync_disposition": RichSyncDisposition,
    "rich_rewrite_edit_request": RichRewriteEditRequest,
    "rich_document_v1": RichDocumentV1, "working_facts": WorkingFacts,
    "rich_mutation": RichMutation, "rich_selection": RichSelection,
    "date_cascade_proposal": DateCascadeProposal, "project_v5": ProjectV5,
    "workspace_v6": WorkspaceV6, "archive_manifest_v6": ArchiveManifestV6,
    "asset_reservation": AssetReservation,
    "rich_project_response": RichProjectResponse,
    "image_session_request": ImageSessionRequest, "image_upload_capture": ImageUploadCapture,
}
TEMPLATE_CONTRACTS = {
    "canonical_patch_v1": CanonicalPatchV1,
    "template_prepared_edit_delta_v1": TemplatePreparedEditDeltaV1,
    **TEMPLATE_AUTHORING_CONTRACTS,
    **TEMPLATE_WRITER_CONTRACTS,
    'template_project_response_v1': TemplateProjectResponseV1, 'template_presentation_v1': TemplatePresentationV1,
    "template_definition": TemplateDefinition, "template_package": TemplatePackage,
    "working_facts_v2": WorkingFactsV2, "rich_document_v2": RichDocumentV2,
    "template_import_v1": ImportOperation,
    "template_start_import_v1": StartTemplateImportV1, "template_resume_import_v1": ResumeTemplateImportV1,
    "template_render_request_v1": TemplateRenderRequestV1, "template_export_request_v1": TemplateExportRequestV1,
    "template_snapshot_identity": TemplateSnapshotIdentity,
    "template_mutation_v1": TemplateMutationV1,
    "project_v6": ProjectV6, "workspace_v7": WorkspaceV7, "archive_manifest_v7": ArchiveManifestV7,
}
RECOVERY_MODELS = {**RECOVERY_CONTRACTS, **GUI_NORMALIZATION_CONTRACTS, **GUI_DRAFT_CONTRACTS, **GUI_PROJECT_CONTRACTS, **GUI_REWRITE_CONTRACTS, **GUI_EXPORT_CONTRACTS, **GUI_RECONCILE_CONTRACTS, **RICH_CONTRACTS, **AGENT_CONTRACTS, **ASSISTANT_CAPABILITY_CONTRACTS, **BACKGROUND_CONTRACTS, "cli_installation_payload": CliInstallationPayload, **TEMPLATE_CONTRACTS}


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
