"""New rich persistence contracts, with no serialized session history."""

from __future__ import annotations

from math import isclose
from typing import Literal

from pydantic import Field, model_validator

from ..project_limits import ARCHIVE_EXPANDED_BYTES, PROJECT_CEILING_BYTES
from .contracts import Evidence, Id, PartialDate, Revision, Sha256, Source, TemplateManifest, Wire, _safe_path, _unique
from .evidence import EvidenceSpan
from .settings import Rules
from .rich_document import ImageBlock, RichDocumentV1, SectionBlock
from .rich_facts import WorkingFacts
from .rich_mutations import DependencyStamp, RichStep, RichSelection
from .importing import ImportDraft


class LocalImageAsset(Wire):
    id: Id
    sha256: Sha256
    path: str
    mime_type: Literal["image/png", "image/jpeg"]
    size: int = Field(gt=0, le=20 * 1024 * 1024)
    width: int = Field(ge=1)
    height: int = Field(ge=1)

    @model_validator(mode="after")
    def owned_image(self) -> LocalImageAsset:
        extension = "png" if self.mime_type == "image/png" else "jpg"
        if self.path != f"images/{self.sha256}.{extension}":
            raise ValueError("image path must match its hash and format")
        if self.width * self.height > 25_000_000:
            raise ValueError("decoded image exceeds 25 megapixels")
        return self


class AssetReservation(Wire):
    id: Id
    project_id: Id
    session_id: Id
    action_id: Id
    dependency_revision: Revision
    retained_bytes: int = Field(ge=0, le=20 * 1024 * 1024)
    live_blocks: int = Field(ge=0, le=20)
    status: Literal["reserved", "decoding", "published", "cancelled", "stale", "failed"]


class ImmutableFactEvidence(Wire):
    id: Id
    evidence: list[EvidenceSpan]
    raw_text: str


class RichOperation(Wire):
    id: Id
    kind: Literal["extract", "assess_resume", "normalize_semantics", "draft_prose", "render", "project_save", "rewrite_prose", "reconcile_edits"]
    status: Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
    action_id: Id | None
    dependencies: list[DependencyStamp]
    error_code: Id | None


class RichRenderSnapshot(Wire):
    id: Id
    document_revision: Revision
    facts_revision: Revision
    template_sha256: Sha256
    renderer_version: Id
    renderer_sha256: Sha256
    docx_sha256: Sha256
    docx_size: int = Field(gt=0, le=32 * 1024 * 1024)
    docx_path: str

    @model_validator(mode="after")
    def safe_artifact(self) -> RichRenderSnapshot:
        if not _safe_path(self.docx_path) or not self.docx_path.startswith("renders/") or not self.docx_path.endswith(".docx"):
            raise ValueError("unsafe rich render reference")
        return self


class ImportCoverage(Wire):
    source_id: Id
    unit_id: Id
    disposition: Literal["placed", "excluded"]
    block_ids: list[Id]
    reason: str | None


class ProjectV5(Wire):
    schema_version: Literal[5]
    project_id: Id
    revision: Revision
    created_at: str
    sources: list[Source]
    evidence_records: list[ImmutableFactEvidence]
    facts: WorkingFacts
    document: RichDocumentV1
    assets: list[LocalImageAsset]
    operations: list[RichOperation]
    renders: list[RichRenderSnapshot]
    template: TemplateManifest
    import_coverage: list[ImportCoverage] = Field(default_factory=list)

    @model_validator(mode="after")
    def identity(self) -> ProjectV5:
        for field in ("evidence_records", "assets", "operations", "renders"):
            _unique([item.id for item in getattr(self, field)], field)
        _unique([f"{item.id}:{item.revision}" for item in self.sources], "source revision")
        records = {record.id for record in self.facts.records}
        assets = {asset.id: asset for asset in self.assets}
        retained: dict[str, int] = {}
        for block in self.document.blocks():
            if isinstance(block, ImageBlock) and block.props.asset_id not in assets:
                raise ValueError("missing local image metadata")
            if isinstance(block, ImageBlock):
                asset = assets[block.props.asset_id]
                if not isclose(block.props.width / block.props.height, asset.width / asset.height, rel_tol=1e-6):
                    raise ValueError("image dimensions must preserve asset aspect ratio")
                if asset.sha256 in retained and retained[asset.sha256] != asset.size:
                    raise ValueError("inconsistent image hash metadata")
                retained[asset.sha256] = asset.size
            if isinstance(block, SectionBlock) and block.props.record_id is not None and block.props.record_id not in records:
                raise ValueError("missing owned working record")
        if sum(retained.values()) > 20 * 1024 * 1024:
            raise ValueError("live retained image bytes exceed 20 MiB")
        if self.template.id != "foldcv-reference" or self.template.version != "1.0.0":
            raise ValueError("rich path requires its own template identity")
        return self


class RichPreDraft(Wire):
    selected_input: Literal["text", "file"]
    selected_source_id: Id | None
    sources: list[Source]
    facts: WorkingFacts
    operations: list[RichOperation]
    warnings: list[Id]
    import_draft: ImportDraft | None = Field(default=None, exclude_if=lambda value: value is None)


class RichSyncRecord(Wire):
    id: Id
    status: Literal["pending", "failed", "conflict", "applied", "stale"]
    action_id: Id
    block_ids: list[Id]
    field_keys: list[Id]
    fact_ids: list[Id]
    dependencies: list[DependencyStamp]
    error_code: Id | None
    kind: Literal["completion", "rewrite", "reconciliation", "conflict", "panel"] = "completion"
    ready: bool = False
    proposed_steps: list[RichStep] = Field(default_factory=list, max_length=1000)
    selection: RichSelection | None = None
    instruction: str | None = None
    rewrite_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    rewrite_result: str | None = Field(default=None, max_length=65536, exclude_if=lambda value: value is None)


class RichMutationReplay(Wire):
    client_mutation_id: Id
    request_sha256: Sha256
    resulting_revision: Revision
    # What the edit's reply named, so a retry after a restart gets the same reply; older rows have none.
    created_ids: dict[str, dict[str, Id]] = Field(default_factory=dict, exclude_if=lambda value: not value)
    created_blocks: dict[str, list[Id]] = Field(default_factory=dict, exclude_if=lambda value: not value)
    changed_block_ids: list[Id] = Field(default_factory=list, exclude_if=lambda value: not value)


class WarningLocation(Wire):
    source_id: Id
    page: int | None = Field(default=None, ge=1)


class RichWarning(Wire):
    id: Id
    code: Id
    block_ids: list[Id]
    record_ids: list[Id]
    evidence: list[Evidence]
    count: int = Field(default=1, ge=1)
    locations: list[WarningLocation] = Field(default_factory=list)


class WorkspaceV6(Wire):
    schema_version: Literal[6]
    project_id: Id
    project_revision: Revision
    document_revision: Revision
    title: str
    title_manually_set: bool
    created_at: str
    updated_at: str
    project: ProjectV5 | None
    pre_draft: RichPreDraft | None
    formatting_as_of: PartialDate
    source_observed_at: PartialDate | None
    rules_used: Rules | None
    sync_records: list[RichSyncRecord]
    mutation_replay: list[RichMutationReplay]
    warnings: list[RichWarning]

    @model_validator(mode="after")
    def owner(self) -> WorkspaceV6:
        if (self.project is None) == (self.pre_draft is None):
            raise ValueError("exactly one rich collection owner required")
        if self.project is not None and (self.project.project_id != self.project_id
                                        or self.project.revision != self.project_revision
                                        or self.project.document.revision != self.document_revision):
            raise ValueError("rich workspace identity/revision mismatch")
        _unique([item.client_mutation_id for item in self.mutation_replay], "mutation replay")
        _unique([item.id for item in self.sync_records], "sync record")
        # Settings bound new saves; validation keeps the ceiling so saved projects stay readable.
        if len(self.model_dump_json(by_alias=True).encode("utf-8")) > PROJECT_CEILING_BYTES:
            raise ValueError("rich workspace exceeds the project size ceiling")
        return self


class RichArchiveEntry(Wire):
    path: str
    role: Literal["workspace", "source_original", "render", "user_image"]
    sha256: Sha256
    size: int = Field(ge=0, le=PROJECT_CEILING_BYTES)

    @model_validator(mode="after")
    def owned_path(self) -> RichArchiveEntry:
        if not _safe_path(self.path):
            raise ValueError("unsafe archive path")
        if self.role == "workspace" and self.path != "workspace.json":
            raise ValueError("invalid workspace entry")
        if self.role != "workspace" and self.size > 32 * 1024 * 1024:
            raise ValueError("archive entry exceeds 32 MiB")
        if self.role == "source_original" and not self.path.startswith("sources/"):
            raise ValueError("invalid source entry")
        if self.role == "render" and (not self.path.startswith("renders/") or not self.path.endswith(".docx")):
            raise ValueError("invalid render entry")
        if self.role == "user_image" and (self.path not in {f"images/{self.sha256}.png", f"images/{self.sha256}.jpg"}
                                          or self.size > 20 * 1024 * 1024):
            raise ValueError("invalid user image entry")
        return self


class ArchiveManifestV6(Wire):
    schema_version: Literal[6]
    app_version: str
    project_id: Id
    entries: list[RichArchiveEntry] = Field(min_length=1, max_length=47)

    @model_validator(mode="after")
    def payload(self) -> ArchiveManifestV6:
        _unique([entry.path.casefold() for entry in self.entries], "archive path")
        if [entry.path for entry in self.entries if entry.role == "workspace"] != ["workspace.json"]:
            raise ValueError("one workspace required")
        if sum(entry.role == "render" for entry in self.entries) > 1:
            raise ValueError("only current optional render allowed")
        if sum(entry.size for entry in self.entries) + len(self.model_dump_json(by_alias=True).encode("utf-8")) > ARCHIVE_EXPANDED_BYTES:
            raise ValueError("expanded archive exceeds its ceiling")
        return self
