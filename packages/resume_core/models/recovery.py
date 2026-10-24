"""Frozen recovery contracts alongside the unchanged version 3 decoders."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import ConfigDict, Field, RootModel, model_validator

from ..project_limits import IMPORT_MINUTES, PROJECT_MEGABYTES
from ..reasoning import ReasoningEffort

from .contracts import (
    ArchiveEntry, AssetRef, Block, Evidence, Fact, Id, Job, Subproject, Operation, PartialDate,
    OperationEvent, Proposal, RenderSnapshot, Review, Revision, Sha256, Source, TemplateManifest,
    TextFact, TechnologyFact, MetricFact, LeadershipFact, DateFact, Wire, _unique,
)


Status = Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
ContentKind = Literal["normalize_semantics", "draft_prose", "rewrite_prose", "reconcile_edits"]


class EvidenceSpan(Evidence):
    text: str = Field(min_length=1)


class NameAssessment(Wire):
    missing_surname: bool | None
    evidence: list[EvidenceSpan]
    revision: Revision


class ObservationAssessment(Wire):
    source_observed_at: PartialDate | None
    evidence: EvidenceSpan | None
    revision: Revision

    @model_validator(mode="after")
    def paired_evidence(self) -> ObservationAssessment:
        if (self.source_observed_at is None) != (self.evidence is None):
            raise ValueError("observation date requires evidence")
        return self


class CandidateDetail(Wire):
    field: Literal["name", "title", "location", "education", "certification", "language", "private_metadata"]
    text: str
    field_id: Id | None = None


class CandidateFact(TextFact):
    kind: Literal["candidate_detail"]
    value: CandidateDetail


class NameAssessmentFact(TextFact):
    kind: Literal["name_assessment"]
    value: NameAssessment


class ObservationFact(TextFact):
    kind: Literal["source_observation"]
    value: ObservationAssessment


class GuiTextFact(TextFact):
    literal_evidence: list[EvidenceSpan]


class GuiTechnologyFact(TechnologyFact):
    literal_evidence: list[EvidenceSpan]


class GuiMetricFact(MetricFact):
    literal_evidence: list[EvidenceSpan]


class GuiLeadershipFact(LeadershipFact):
    literal_evidence: list[EvidenceSpan]


class GuiDateFact(DateFact):
    literal_evidence: list[EvidenceSpan]


class EmploymentPeriodValue(Wire):
    id: Id
    start: PartialDate | None
    end: PartialDate | None
    start_text: str
    end_text: str
    present: bool
    evidence: list[EvidenceSpan]


class EmploymentValue(Wire):
    job_id: Id
    employer: str
    role: str
    periods: list[EmploymentPeriodValue]
    subprojects: list[Subproject]


class EmploymentFact(TextFact):
    kind: Literal["employment"]
    value: EmploymentValue
    literal_evidence: list[EvidenceSpan]


GuiFact = Annotated[Union[GuiTextFact, GuiTechnologyFact, GuiMetricFact, GuiLeadershipFact, GuiDateFact], Field(discriminator="kind")]
RecoveryFact = Union[GuiFact, Fact, CandidateFact, NameAssessmentFact, ObservationFact, EmploymentFact]


class Rules(Wire):
    model_config = ConfigDict(frozen=True)
    markdown: str
    revision: Revision
    sha256: Sha256


class JobDisposition(Wire):
    job_id: Id
    disposition: Literal["detailed", "early-career"]
    fact_ids: list[Id]


class PlanFocus(Wire):
    catalog_id: Id
    display: str
    fact_ids: list[Id]


class TechnologyGroup(Wire):
    title: str
    fact_ids: list[Id]


class EditorialPlan(Wire):
    origin: Literal["model", "migration"]
    revision: Revision
    rules_revision: Revision | None
    formatting_as_of: PartialDate
    source_language: Literal["ru", "en", "mixed"]
    profile_language: Literal["ru", "en"] | None
    jobs: list[JobDisposition]
    focus: list[PlanFocus]
    technology_groups: list[TechnologyGroup]
    fact_ids: list[Id]

    @model_validator(mode="after")
    def model_context(self) -> EditorialPlan:
        _unique([job.job_id for job in self.jobs], "plan job")
        if self.origin == "model" and (self.rules_revision is None or self.profile_language is None):
            raise ValueError("model plan needs captured rules and profile language")
        return self


class AuthoredField(Wire):
    field_id: Id
    text: str
    fact_ids: list[Id]
    evidence: list[Evidence]
    origin: Literal["source", "generated", "user", "migration"]


class Record(Wire):
    id: Id
    revision: Revision
    visible: bool


class CandidateRecord(Record):
    kind: Literal["candidate"]
    id: Literal["candidate"]
    visible: Literal[True]
    name: AuthoredField
    title: AuthoredField
    location: AuthoredField
    details: list[AuthoredField] = Field(default_factory=list, max_length=100)


class ProfileRecord(Record):
    kind: Literal["profile"]
    id: Literal["profile"]
    text: AuthoredField


class DocumentPeriod(Wire):
    id: Id
    start_text: AuthoredField
    end_text: AuthoredField
    present: bool


class JobRecord(Record):
    kind: Literal["job"]
    employer: AuthoredField
    role: AuthoredField
    periods_field_id: Id
    periods: list[DocumentPeriod]
    context: AuthoredField
    tasks: AuthoredField
    results: AuthoredField
    stack: AuthoredField
    subproject_ids: list[Id]


class EducationRecord(Record):
    kind: Literal["education"]
    institution: AuthoredField
    qualification: AuthoredField
    specialty: AuthoredField
    date_text: AuthoredField
    legacy_text: AuthoredField | None


class CertificationRecord(Record):
    kind: Literal["certification"]
    name: AuthoredField
    issuer: AuthoredField
    date_text: AuthoredField
    legacy_text: AuthoredField | None


class LanguageRecord(Record):
    kind: Literal["language"]
    name: AuthoredField
    proficiency: AuthoredField
    legacy_text: AuthoredField | None


class FocusEntry(Wire):
    id: Id
    catalog_id: Id
    display: AuthoredField
    fact_ids: list[Id]


class SkillsFocusRecord(Record):
    kind: Literal["skills-focus"]
    id: Literal["skills-focus"]
    skills_text: AuthoredField
    focus_field_id: Id
    focus: list[FocusEntry] = Field(max_length=8)


class EarlyCareerRecord(Record):
    kind: Literal["early-career"]
    id: Literal["early-career"]
    text: AuthoredField
    represented_job_ids: list[Id]


DocumentRecord = Annotated[Union[
    CandidateRecord, ProfileRecord, JobRecord, EducationRecord, CertificationRecord,
    LanguageRecord, SkillsFocusRecord, EarlyCareerRecord,
], Field(discriminator="kind")]


def record_slot(record: DocumentRecord) -> str:
    if record.kind in {"candidate", "profile", "skills-focus", "early-career"}:
        return record.id
    return f"{record.kind}:{record.id}"


def authored_fields(record: DocumentRecord) -> list[AuthoredField]:
    fields = [value for value in record.__dict__.values() if isinstance(value, AuthoredField)]
    if isinstance(record, CandidateRecord):
        fields.extend(record.details)
    if isinstance(record, JobRecord):
        fields = [record.employer, record.role,
                  *(field for period in record.periods for field in (period.start_text, period.end_text)),
                  record.context, record.tasks, record.results, record.stack]
    if isinstance(record, SkillsFocusRecord):
        fields.extend(entry.display for entry in record.focus)
    return fields


class Document(Wire):
    candidate: CandidateRecord
    profile: ProfileRecord
    jobs: list[JobRecord]
    education: list[EducationRecord]
    certifications: list[CertificationRecord]
    languages: list[LanguageRecord]
    skills_focus: SkillsFocusRecord
    early_career: EarlyCareerRecord

    def records(self) -> list[DocumentRecord]:
        return [self.candidate, self.profile, *self.jobs, *self.education,
                *self.certifications, *self.languages, self.skills_focus, self.early_career]

    @model_validator(mode="after")
    def stable_identity(self) -> Document:
        records = self.records()
        _unique([record_slot(record) for record in records], "document slot")
        fields = [field.field_id for record in records for field in authored_fields(record)]
        fields.extend(job.periods_field_id for job in self.jobs)
        fields.append(self.skills_focus.focus_field_id)
        _unique(fields, "field ID")
        for record in [*self.education, *self.certifications, *self.languages]:
            if record.legacy_text is not None and any(field.text for field in authored_fields(record)
                                                      if field is not record.legacy_text):
                raise ValueError("legacyText and structured content are exclusive")
        for job in self.jobs:
            _unique([period.id for period in job.periods], "period ID")
        _unique([entry.id for entry in self.skills_focus.focus], "focus ID")
        return self


class Range(Wire):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> Range:
        if self.end < self.start:
            raise ValueError("range is reversed")
        return self


class FieldAnchor(Wire):
    kind: Literal["field"]
    field_id: Id
    range: Range | None


class SectionAnchor(Wire):
    kind: Literal["section"]
    section_id: Id


class DocumentAnchor(Wire):
    kind: Literal["document"]


Anchor = Annotated[Union[FieldAnchor, SectionAnchor, DocumentAnchor], Field(discriminator="kind")]


class Dependencies(Wire):
    project_revision: Revision
    document_revision: Revision
    rules_sha256: Sha256 | None
    source_fingerprint: Sha256
    dependency_fingerprint: Sha256


class FocusRemoval(Wire):
    catalog_id: Id
    reason: Literal["duplicate", "unknown-ID", "missing-logo", "capacity"]


class Annotation(Wire):
    id: Id
    type: Literal["missing", "conflicting", "stale", "warning"]
    code: Id
    anchor: Anchor
    dependencies: Dependencies
    fact_ids: list[Id]
    reason: str
    evidence: list[EvidenceSpan]
    resolved: bool
    update_suggestion_id: Id | None
    removed_focus: list[FocusRemoval]


DocxErrorCode = Literal[
    "DOCX_NAME_LINE_LIMIT", "DOCX_TITLE_LINE_LIMIT", "DOCX_UNBREAKABLE_TEXT",
    "DOCX_BLOCK_PAGE_BUDGET", "DOCX_BLOCK_PLANNED_PAGE", "DOCX_UNKNOWN_FOCUS_ICON",
    "DOCX_TEXT_LIMIT", "DOCX_LIST_LIMIT", "DOCX_TOTAL_TEXT_LIMIT",
    "DOCX_INVALID_CHARACTER", "DOCX_INVALID_RENDER_INPUT", "DOCX_RENDER_FAILED",
]
SafeRenderPath = Annotated[str, Field(pattern=(
    r"^(candidate\.(name|title|summary)|footer|focus(\[[0-9]+\]\.(label|duration|icon))?|"
    r"sidebar(\[[0-9]+\]\.(title|items(\[[0-9]+\])?))?|"
    r"projects(\[[0-9]+\]\.(company|role|period|stack|description|tasks(\[[0-9]+\])?|"
    r"results(\[[0-9]+\])?))?|achievements(\[[0-9]+\])?|"
    r"skillGroups(\[[0-9]+\]\.(title|items))?)$"
))]


class DocxError(Wire):
    code: DocxErrorCode
    path: SafeRenderPath | None
    anchor: Anchor


class RenderSnapshotV4(Wire):
    id: Id
    project_revision: Revision
    document_revision: Revision
    render_input_fingerprint: Sha256
    template_id: Id
    template_version: str
    template_sha256: Sha256
    renderer_version: str
    renderer_sha256: Sha256
    docx: AssetRef
    pdf: Literal[None]
    artifact_available: bool


class GuiOperationEvent(OperationEvent):
    type: Literal["operation.started", "stage.changed", "result.ready", "usage.updated",
                  "operation.completed", "operation.failed", "cancelled"]


class AnalysisBatch(Wire):
    phase: Literal["pending", "dispatched"]
    completed_field_ids: list[Id]
    enabled: bool


class GuiOperation(Operation):
    kind: Literal["extract", "validate", "render", "project_save", "normalize_semantics",
                  "draft_prose", "rewrite_prose", "reconcile_edits"]
    project_id: Id
    captured_document_revision: Revision | None
    dependencies: Dependencies | None
    rules_used: Rules | None
    target_field_ids: list[Id]
    result_fingerprint: Sha256 | None
    error_code: Id | None
    events: list[GuiOperationEvent]
    docx_error: DocxError | None = None
    render_snapshot_id: Id | None = None
    analysis_batch: AnalysisBatch | None = None
    editorial_recommendations: list[str] = Field(default_factory=list)


class GenerationStage(Wire):
    kind: Literal["extract", "normalize_semantics", "draft_prose", "assemble", "render"]
    status: Status
    dependency_fingerprint: Sha256
    result_fingerprint: Sha256 | None
    operation_id: Id | None
    error_code: Id | None
    docx_error: DocxError | None


class Generation(Wire):
    id: Id
    project_id: Id
    status: Status
    dependencies: Dependencies
    rules_used: Rules
    source_ids: list[Id]
    formatting_as_of: PartialDate
    stages: list[GenerationStage]


class CollectionState(Wire):
    sources: list[Source]
    facts: list[RecoveryFact]
    operations: list[GuiOperation]
    renders: list[RenderSnapshotV4]


class PreDraft(CollectionState):
    selected_input: Literal["text", "file"]
    selected_source_id: Id | None
    extracted_text: str
    warnings: list[str]
    extraction_fingerprint: Sha256 | None


class ProjectV4(CollectionState):
    schema_version: Literal[4]
    project_id: Id
    revision: Revision
    as_of: PartialDate | None
    created_at: str
    document: Document
    employment: list[Job]
    views: list[Block]
    template: TemplateManifest | None
    review: Review
    proposals: list[Proposal]

    @model_validator(mode="after")
    def collection_identity(self) -> ProjectV4:
        for name in ("facts", "operations", "renders", "employment"):
            _unique([item.id for item in getattr(self, name)], name)
        _unique([f"{item.id}:{item.revision}" for item in self.sources], "source revision")
        return self


class DerivedValue(Wire):
    field_id: Id
    parsed_date: PartialDate | None
    canonical_aliases: list[Id]
    months_min: int | None = Field(ge=0)
    months_max: int | None = Field(ge=0)
    display: str | None
    valid: bool
    complete_exposure: bool
    dependency_fingerprint: Sha256


class DerivedState(Wire):
    document_revision: Revision
    values: list[DerivedValue]


class SourceExclusion(Wire):
    id: Id
    record_id: Id
    source_ids: list[Id]
    fact_ids: list[Id]
    reason: Literal["hidden", "deleted"]
    revision: Revision


class FactStamp(Wire):
    fact_id: Id
    revision: Revision
    owner_slot_id: Id
    origin: Literal["source", "user", "model", "migration"]
    authoritative_revision: Revision


class BlockCheckpoint(Wire):
    record: DocumentRecord
    facts: list[RecoveryFact]
    annotations: list[Annotation]
    fact_stamps: list[FactStamp]
    project_revision: Revision
    document_revision: Revision


class BufferedField(Wire):
    field_id: Id
    text: str


class EditSession(Wire):
    session_id: Id
    baseline: BlockCheckpoint
    buffered_fields: list[BufferedField]
    started_document_revision: Revision


class FieldReplacement(Wire):
    field_id: Id
    range: Range | None
    text: str


class RelatedUpdateSuggestion(Wire):
    id: Id
    dependencies: Dependencies
    fact_ids: list[Id]
    replacements: list[FieldReplacement]
    reason: str


class MutationReplay(Wire):
    client_mutation_id: Id
    payload_sha256: Sha256
    status: Literal["applied", "stale", "rejected"]
    project_revision: Revision
    document_revision: Revision
    rejection_reason: Id | None


class LegacyText(Wire):
    id: Id
    original_kind: str
    label: str
    text: str
    visible: bool
    fact_ids: list[Id]
    evidence: list[Evidence]


class LegacyRender(Wire):
    record: RenderSnapshot
    artifact_available: bool


class LegacyData(Wire):
    blocks: list[Block]
    proposals: list[Proposal]
    review: Review | None
    renders: list[LegacyRender]
    unmapped_text: list[LegacyText]


class WorkspaceV5(Wire):
    schema_version: Literal[5]
    project_id: Id
    project_revision: Revision
    document_revision: Revision
    title: str
    title_manually_set: bool
    created_at: str
    updated_at: str
    project: ProjectV4 | None
    pre_draft: PreDraft | None
    formatting_as_of: PartialDate
    source_observed_at: PartialDate | None
    rules_used: Rules | None
    editorial_plan: EditorialPlan | None
    annotations: list[Annotation]
    related_update_suggestions: list[RelatedUpdateSuggestion]
    derived_state: DerivedState | None
    undo_slots: dict[str, BlockCheckpoint | None]
    edit_sessions: dict[str, EditSession]
    mutation_replay: list[MutationReplay]
    generations: list[Generation]
    source_exclusions: list[SourceExclusion]
    migration_notices: list[str]
    legacy_data: LegacyData | None

    @model_validator(mode="after")
    def exclusive_collections(self) -> WorkspaceV5:
        if (self.project is None) == (self.pre_draft is None):
            raise ValueError("exactly one collection owner is required")
        if self.project is not None:
            if self.project.project_id != self.project_id or self.project.revision != self.project_revision:
                raise ValueError("project identity/revision mismatch")
            slots = {record_slot(record) for record in self.project.document.records()}
            if set(self.undo_slots) != slots or not set(self.edit_sessions) <= slots:
                raise ValueError("undo/session slot mismatch")
            for slot, checkpoint in self.undo_slots.items():
                if checkpoint is not None and record_slot(checkpoint.record) != slot:
                    raise ValueError("checkpoint belongs to another slot")
        elif self.undo_slots or self.edit_sessions:
            raise ValueError("preDraft cannot have document sessions")
        _unique([item.client_mutation_id for item in self.mutation_replay], "mutation replay ID")
        return self


class SelectionSpan(Wire):
    field_id: Id
    range: Range
    captured_text: str


class Selection(Wire):
    project_id: Id
    document_revision: Revision
    dependency_fingerprint: Sha256
    spans: list[SelectionSpan] = Field(min_length=1)


class SourceContextRequest(Wire):
    project_id: Id
    document_revision: Revision
    selection: Selection | None
    field_ids: list[Id]


class SourceExcerpt(Wire):
    evidence: EvidenceSpan
    relation: Literal["exact", "field", "block"]
    page: int | None = Field(ge=0)


class SourceContext(Wire):
    project_id: Id
    document_revision: Revision
    status: Literal["evidence", "user-origin", "no-evidence", "stale"]
    excerpts: list[SourceExcerpt]
    annotations: list[Annotation]
    legacy_text: list[LegacyText]


class EditFieldPayload(Wire):
    field_id: Id
    text: str | None
    periods: list[DocumentPeriod] | None
    focus: list[FocusEntry] | None
    session_id: Id
    completion: Literal["none", "paragraph", "field", "slot"]

    @model_validator(mode="after")
    def one_value(self) -> EditFieldPayload:
        if sum(value is not None for value in (self.text, self.periods, self.focus)) != 1:
            raise ValueError("edit needs exactly one value")
        return self


class RestorePayload(Wire):
    slot_id: Id
    session_id: Id | None


class AddPayload(Wire):
    section_id: Literal["jobs", "education", "languages"]
    record: Annotated[Union[JobRecord, EducationRecord, LanguageRecord], Field(discriminator="kind")]
    after_record_id: Id | None


class DeletePayload(Wire):
    section_id: Literal["jobs", "education", "languages"]
    record_id: Id


class ReorderPayload(Wire):
    section_id: Literal["jobs", "education", "languages"]
    ordered_ids: list[Id]


class HidePayload(Wire):
    slot_id: Id
    visible: bool


class ApplyRelatedPayload(Wire):
    suggestion_id: Id
    dependencies: Dependencies


class MutationBase(Wire):
    project_id: Id
    base_revision: Revision
    client_mutation_id: Id


class EditMutation(MutationBase):
    kind: Literal["edit-field"]
    payload: EditFieldPayload


class RestoreMutation(MutationBase):
    kind: Literal["restore-previous-block"]
    payload: RestorePayload


class AddMutation(MutationBase):
    kind: Literal["add"]
    payload: AddPayload


class DeleteMutation(MutationBase):
    kind: Literal["delete"]
    payload: DeletePayload


class ReorderMutation(MutationBase):
    kind: Literal["reorder"]
    payload: ReorderPayload


class HideMutation(MutationBase):
    kind: Literal["hide"]
    payload: HidePayload


class RelatedMutation(MutationBase):
    kind: Literal["apply-related-update"]
    payload: ApplyRelatedPayload


class Mutation(RootModel[Annotated[Union[EditMutation, RestoreMutation, AddMutation, DeleteMutation,
                                        ReorderMutation, HideMutation, RelatedMutation], Field(discriminator="kind")]]):
    pass


class MutationResult(Wire):
    status: Literal["applied", "replayed", "stale", "rejected"]
    project_revision: Revision
    document_revision: Revision
    changed_slot_ids: list[Id]
    rejection_reason: Id | None
    persistence: Literal["memory", "durable", "pending", "failed"]


class RegistryEntry(Wire):
    project_id: Id
    title: str
    updated_at: str
    tombstoned: bool
    cleanup_status: Literal["none", "pending", "complete", "failed"]


class Registry(Wire):
    schema_version: Literal[1]
    entries: list[RegistryEntry]


class Preferences(Wire):
    schema_version: Literal[1]
    automatic_analysis: bool
    theme: Literal["light", "dark", "system"]
    selected_model: str | None
    selected_import_model: str | None = None
    rewrite_reasoning_effort: ReasoningEffort | None = None
    import_minutes: int = Field(default=IMPORT_MINUTES[0], ge=IMPORT_MINUTES[1], le=IMPORT_MINUTES[2])
    project_megabytes: int = Field(default=PROJECT_MEGABYTES[0], ge=PROJECT_MEGABYTES[1], le=PROJECT_MEGABYTES[2])


class SaveImportModelPreference(Wire):
    model: str | None = Field(max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")


class SaveLimitsPreference(Wire):
    import_minutes: int = Field(ge=IMPORT_MINUTES[1], le=IMPORT_MINUTES[2])
    project_megabytes: int = Field(ge=PROJECT_MEGABYTES[1], le=PROJECT_MEGABYTES[2])


class ArchiveManifestV5(Wire):
    schema_version: Literal[5]
    app_version: str
    project_id: Id
    entries: list[ArchiveEntry] = Field(min_length=1, max_length=47)

    @model_validator(mode="after")
    def archive_shape(self) -> ArchiveManifestV5:
        paths = [entry.path for entry in self.entries]
        _unique(paths, "archive path")
        _unique([path.casefold() for path in paths], "archive path alias")
        if [entry.path for entry in self.entries if entry.role == "workspace"] != ["workspace.json"]:
            raise ValueError("workspace entry required")
        if any(entry.role not in {"workspace", "source_original", "render"} for entry in self.entries):
            raise ValueError("v5 contains workspace, originals and current DOCX only")
        renders = [entry for entry in self.entries if entry.role == "render"]
        if len(renders) > 1 or any(not entry.path.startswith("renders/") or not entry.path.endswith(".docx")
                                   for entry in renders):
            raise ValueError("at most current DOCX is packaged")
        if any(entry.role == "source_original" and not entry.path.startswith("sources/") for entry in self.entries):
            raise ValueError("source entry path mismatch")
        return self


class SaveRulesRequest(Wire):
    markdown: str = Field(min_length=1, max_length=32_768)
    base_revision: Revision


class RulePresets(Wire):
    shorten: str = Field(min_length=1)
    clarify: str = Field(min_length=1)


class RulesSettings(Rules):
    presets: RulePresets


class RulesErrorPayload(Wire):
    code: Literal["RULES_PRESETS_REQUIRED", "RULES_STALE", "RULES_TOO_LARGE",
                  "RULES_INVALID_TEXT", "RULES_LOAD_FAILED", "RULES_SAVE_FAILED", "RULES_UNSAFE_STORAGE"]
    retryable: Literal[False]
    stage: Literal["rules"]


class RulesSettingsError(Wire):
    error: RulesErrorPayload
    required_headings: list[Literal["## Preset: shorten", "## Preset: clarify"]]


RECOVERY_CONTRACTS = {
    "project_v4": ProjectV4, "workspace_v5": WorkspaceV5, "archive_manifest_v5": ArchiveManifestV5,
    "document": Document, "docx_error": DocxError, "editorial_plan": EditorialPlan,
    "mutation": Mutation, "mutation_result": MutationResult, "preferences": Preferences,
    "save_import_model_preference": SaveImportModelPreference, "save_limits_preference": SaveLimitsPreference,
    "registry": Registry, "render_snapshot_v4": RenderSnapshotV4, "rules": Rules,
    "selection": Selection, "source_context": SourceContext, "source_context_request": SourceContextRequest,
    "save_rules_request": SaveRulesRequest, "rules_settings_error": RulesSettingsError,
    "rules_settings": RulesSettings,
}
