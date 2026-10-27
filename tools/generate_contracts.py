"""Export deterministic JSON Schemas from the Python contract authority."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.resume_core.extraction.models import ExtractResult
from packages.resume_core.models.agent import AGENT_CONTRACTS
from packages.resume_core.models.assistant import ASSISTANT_CONTRACTS
from packages.resume_core.models.connection import CliInstallationPayload
from packages.resume_core.models.contracts import Project
from packages.resume_core.models.projects import PROJECT_CONTRACTS, TemplateRewritePreviewV1
from packages.resume_core.models.registry import Registry
from packages.resume_core.models.rich_document import RichDocumentV1
from packages.resume_core.models.rich_facts import WorkingFacts
from packages.resume_core.models.settings import SETTINGS_CONTRACTS, SaveAnalysisPreference
from packages.resume_core.models.template_authoring import TemplateClipboardCaptureV1, TemplateEditPreparationV1
from packages.resume_core.models.template_document import RichDocumentV2
from packages.resume_core.models.template_import import ImportOperation
from packages.resume_core.models.template_render import TemplateRenderRequestV1, TemplateSnapshotIdentity
from packages.resume_core.models.template_workspace import ArchiveManifestV7, WorkspaceV7
from packages.resume_core.rendering.models import RenderRequest
from packages.resume_core.rendering.preparation import PrepareRequest
from packages.resume_core.rich_panel import RichPanelRequest
from packages.resume_core.template_api import TemplateProjectResponseV1
from packages.resume_core.templates.models import TemplateDefinition, TemplatePackage
from packages.resume_core.templates.shorthand import source_schema

OUT = ROOT / "contracts" / "json-schema"
TYPES = ROOT / "apps" / "web" / "src" / "contracts" / "generated"
# Route bodies and replies, the files a project writes, the worker inputs and outputs, and the models the client
# types or kept tests read through contracts/examples.
CONTRACTS = {
    **PROJECT_CONTRACTS,
    "template_project_response_v1": TemplateProjectResponseV1,
    "template_edit_preparation_v1": TemplateEditPreparationV1,
    "template_clipboard_capture_v1": TemplateClipboardCaptureV1,
    "template_rewrite_preview_v1": TemplateRewritePreviewV1,
    "template_snapshot_identity": TemplateSnapshotIdentity,
    "rich_document_v2": RichDocumentV2,
    "workspace_v7": WorkspaceV7,
    "archive_manifest_v7": ArchiveManifestV7,
    "template_import_v1": ImportOperation,
    "template_render_request_v1": TemplateRenderRequestV1,
    "template_definition": TemplateDefinition,
    "template_package": TemplatePackage,
    # V6 parts the V7 models are built from and the client still types.
    "working_facts": WorkingFacts,
    "rich_document_v1": RichDocumentV1,
    "rich_panel_request": RichPanelRequest,
    **ASSISTANT_CONTRACTS,
    **AGENT_CONTRACTS,
    **SETTINGS_CONTRACTS,
    "save_analysis_preference": SaveAnalysisPreference,
    "registry": Registry,
    "cli_installation_payload": CliInstallationPayload,
    "extract_result": ExtractResult,
    "render_request": RenderRequest,
    "prepare_request": PrepareRequest,
    "project": Project,
}


def main() -> None:
    if sys.argv[1:] == ["--clean-types"]:
        for path in sorted(TYPES.glob("*.ts")):
            text = path.read_text(encoding="utf-8")
            marker = "export "
            start = text.find(marker)
            if start < 0:
                raise ValueError(f"missing declarations in {path}")
            path.write_text(text[start:], encoding="utf-8")
        return
    # Start from empty folders so a contract that left the list leaves no schema or type behind.
    for path in [*OUT.glob("*.schema.json"), *TYPES.glob("*.ts")]:
        path.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    TYPES.mkdir(parents=True, exist_ok=True)
    for name, model in CONTRACTS.items():
        schema = model.model_json_schema(mode="validation")
        (OUT / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    # Editor hints for template YAML in both forms; no TypeScript type is generated from it.
    (ROOT / "contracts" / "template-source.schema.json").write_text(json.dumps(
        source_schema(TemplateDefinition.model_json_schema(mode="validation")), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
