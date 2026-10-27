"""Version 3 wire contracts. All persisted candidate state is explicit."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer
from pydantic.alias_generators import to_camel


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, alias_generator=to_camel)


Id = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Revision = Annotated[int, Field(ge=1)]


class PartialDate(Wire):
    precision: Literal["year", "month", "day"]
    year: int = Field(ge=1, le=9999)
    month: int | None
    day: int | None

    @model_validator(mode="after")
    def valid_precision(self) -> PartialDate:
        if self.precision == "year" and (self.month is not None or self.day is not None):
            raise ValueError("year precision cannot include month or day")
        if self.precision == "month" and (self.month is None or self.day is not None):
            raise ValueError("month precision requires only month")
        if self.precision == "day" and (self.month is None or self.day is None):
            raise ValueError("day precision requires month and day")
        if self.month is not None:
            if not 1 <= self.month <= 12:
                raise ValueError("invalid month")
            if self.day is not None:
                date(self.year, self.month, self.day)
        return self

    def lower(self) -> tuple[int, int, int]:
        return (self.year, self.month or 1, self.day or 1)

    def upper(self) -> tuple[int, int, int]:
        if self.precision == "year":
            return (self.year, 12, 31)
        if self.precision == "month":
            month = self.month or 1
            last = (date(self.year + 1, 1, 1) if month == 12 and self.year < 9999
                    else date(self.year, month + 1, 1) if month < 12
                    else date(9999, 12, 31))
            if self.year == 9999 and month == 12:
                return (9999, 12, 31)
            from datetime import timedelta
            last -= timedelta(days=1)
            return (last.year, last.month, last.day)
        return (self.year, self.month or 1, self.day or 1)


class Period(Wire):
    start: PartialDate
    end: PartialDate | None

    @model_validator(mode="after")
    def valid_order(self) -> Period:
        if self.end and self.start.lower() > self.end.upper():
            raise ValueError("period ends before it starts")
        return self


class SourceLocation(Wire):
    kind: Literal["page", "paragraph", "table_cell", "pasted"]
    index: int = Field(ge=0)
    row: int | None
    column: int | None

    @model_validator(mode="after")
    def valid_cell(self) -> SourceLocation:
        if (self.row is not None or self.column is not None) != (self.kind == "table_cell"):
            raise ValueError("row and column belong only to table cells")
        if self.kind == "table_cell" and (self.row is None or self.column is None or self.row < 0 or self.column < 0):
            raise ValueError("table cell needs nonnegative row and column")
        return self


class SourceStructure(Wire):
    """Observed layout cues, never semantic resume fields."""

    model_config = ConfigDict(populate_by_name=True)
    bounds: list[float] | None = Field(default=None, min_length=4, max_length=4)
    column: int | None = Field(default=None, ge=1)
    group: int | None = Field(default=None, ge=1)
    gap_before: float | None = None
    font_size: float | None = Field(default=None, gt=0)
    bold: bool | None = None
    layout_uncertain: bool = False
    part: str | None = Field(default=None, max_length=120)
    style: str | None = Field(default=None, max_length=120)
    heading_level: int | None = Field(default=None, ge=1, le=9)
    list_level: int | None = Field(default=None, ge=0, le=8)
    column_span: int | None = Field(default=None, ge=1, le=1000)
    row_merge: Literal["start", "continue"] | None = None
    indent: int | None = Field(default=None, ge=0)
    blank_before: int | None = Field(default=None, ge=0)

    @model_serializer(mode="wrap")
    def omit_unknown(self, serialize):
        return {key: value for key, value in serialize(self).items() if value is not None}


class SourceUnit(Wire):
    id: Id
    revision: Revision
    order: int = Field(ge=0)
    text: str
    location: SourceLocation
    disposition: Literal["shown", "condensed", "archived", "duplicate", "unresolved", "administrative"]
    represented_fact_ids: list[Id]
    # Absent cues must not change old workspace hashes or saved job identities.
    structure: SourceStructure | None = Field(default=None, exclude_if=lambda value: value is None)


class SourceOverlay(Wire):
    id: Id
    revision: Revision
    unit_id: Id
    text: str
    origin: Literal["user"]


class SourceWarning(Wire):
    code: str
    page: int | None = Field(default=None, ge=1)


class Source(Wire):
    id: Id
    revision: Revision
    original_name: str
    mime_type: str
    byte_sha256: Sha256
    byte_ref: str
    parser: str
    parser_version: str
    units: list[SourceUnit]
    overlays: list[SourceOverlay]
    warnings: list[str]
    warning_details: list[SourceWarning] = Field(default_factory=list)


class Evidence(Wire):
    source_id: Id
    source_revision: Revision
    unit_id: Id
    unit_revision: Revision


class TextValue(Wire):
    text: str


class TechnologyValue(Wire):
    canonical_id: Id
    display: str
    scope: Literal["global", "job", "subproject"]


class MetricValue(Wire):
    number: float
    upper_number: float | None
    comparator: Literal["exact", "at_least", "at_most", "approximately", "range"]
    unit: str
    period: str | None
    baseline: str | None
    result: str | None
    scope: str | None
    attribution: Literal["personal", "team", "organization", "unknown"]
    qualifiers: list[str]

    @model_validator(mode="after")
    def valid_range(self) -> MetricValue:
        if (self.comparator == "range") != (self.upper_number is not None):
            raise ValueError("range requires upper number only for range comparator")
        if self.upper_number is not None and self.upper_number < self.number:
            raise ValueError("range upper number is below lower number")
        return self


class LeadershipValue(Wire):
    action: str
    team_size: MetricValue | None
    attribution: Literal["personal", "team", "organization", "unknown"]


class TextFact(Wire):
    id: Id
    revision: Revision
    kind: Literal["text"]
    value: TextValue
    evidence: list[Evidence]
    origin: Literal["source", "user"]
    importance: Literal["essential", "normal", "minor"]
    job_id: Id | None
    subproject_id: Id | None


class TechnologyFact(TextFact):
    kind: Literal["technology"]
    value: TechnologyValue


class MetricFact(TextFact):
    kind: Literal["metric"]
    value: MetricValue


class LeadershipFact(TextFact):
    kind: Literal["leadership"]
    value: LeadershipValue


class DateFact(TextFact):
    kind: Literal["date"]
    value: PartialDate


Fact = Annotated[Union[TextFact, TechnologyFact, MetricFact, LeadershipFact, DateFact], Field(discriminator="kind")]


class Subproject(Wire):
    id: Id
    name: str
    period: Period | None
    fact_ids: list[Id]


class Job(Wire):
    id: Id
    employer: str
    role: str
    periods: list[Period]
    subprojects: list[Subproject]
    fact_ids: list[Id]


class BlockState(Wire):
    text: str
    origin: Literal["source", "generated", "manual"]
    locked: bool
    fact_ids: list[Id]
    fact_revisions: dict[str, Revision]


class Block(Wire):
    id: Id
    kind: Literal["profile", "job_prose", "contact", "focus", "education", "skills", "early_career"]
    revision: Revision
    state: BlockState
    previous: BlockState | None
    visible: bool
    status: Literal["empty", "running", "proposed", "ready", "stale", "error"]
    dependency_hash: Sha256
    content_policy_version: str


class ReviewDecision(Wire):
    target_kind: Literal["source_unit", "fact", "block"]
    target_id: Id
    disposition: Literal["shown", "condensed", "archived", "duplicate", "unresolved", "excluded"]
    reason: str | None
    target_revision: Revision


class Acknowledgment(Wire):
    issue_id: Id
    target_kind: Literal["fact", "block"]
    target_id: Id
    target_revision: Revision


class Review(Wire):
    decisions: list[ReviewDecision]
    acknowledgments: list[Acknowledgment]


class Proposal(Wire):
    id: Id
    operation_id: Id
    kind: Literal["draft_prose", "rewrite_prose"]
    block_id: Id
    base_block_revision: Revision
    dependency_hash: Sha256
    replacement_text: str
    evidence_fact_ids: list[Id]
    findings: list[str]


class Usage(Wire):
    logical_attempts: int = Field(ge=0)
    internal_inference_requests: int | None = Field(ge=0)
    reported_input_tokens: int | None = Field(ge=0)
    reported_output_tokens: int | None = Field(ge=0)


class OperationEvent(Wire):
    request_id: Id
    sequence: int = Field(ge=0)
    type: Literal["operation.started", "stage.changed", "result.ready", "usage.updated", "operation.completed", "operation.failed", "cancelled"]
    stage: str | None
    usage: Usage | None


class OperationDependencies(Wire):
    project_revision: Revision
    document_revision: Revision
    rules_sha256: Sha256 | None
    source_fingerprint: Sha256
    dependency_fingerprint: Sha256


class OperationRules(Wire):
    markdown: str
    revision: Revision
    sha256: Sha256


class Operation(Wire):
    id: Id
    kind: Literal["extract", "validate", "render", "project_save", "normalize_semantics", "draft_prose", "rewrite_prose", "reconcile_edits"]
    status: Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
    base_revision: Revision
    usage: Usage | None
    events: list[OperationEvent]
    project_id: Id | None = None
    captured_document_revision: Revision | None = None
    dependencies: OperationDependencies | None = None
    rules_used: OperationRules | None = None
    target_field_ids: list[Id] = Field(default_factory=list)
    result_fingerprint: Sha256 | None = None
    error_code: Id | None = None


class AssetRef(Wire):
    path: str
    sha256: Sha256
    size: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_path(self) -> AssetRef:
        if not _safe_path(self.path):
            raise ValueError("unsafe asset reference")
        return self


class TemplateManifest(Wire):
    id: Id
    version: str
    package_sha256: Sha256
    content_policy_version: str
    assets: list[AssetRef]


class RenderBlock(Wire):
    block_id: Id
    block_revision: Revision
    text: str


class RenderSnapshot(Wire):
    id: Id
    project_revision: Revision
    snapshot_sha256: Sha256
    template_id: Id
    template_version: str
    renderer_version: str
    blocks: list[RenderBlock]
    docx: AssetRef | None
    pdf: AssetRef | None


class ZipEntry(Wire):
    path: str
    role: Literal["project", "source_original", "source_extracted", "template_asset", "render", "checks"]
    sha256: Sha256
    uncompressed_size: int = Field(ge=0)


class ZipManifest(Wire):
    schema_version: Literal[3]
    app_version: str
    renderer_version: str
    project_id: Id
    entries: list[ZipEntry]

    @model_validator(mode="after")
    def valid_entries(self) -> ZipManifest:
        return validate_manifest(self)


class ArchiveEntry(Wire):
    path: str
    role: Literal["project", "workspace", "source_original", "template_asset", "render"]
    sha256: Sha256
    uncompressed_size: int = Field(ge=0, le=32 * 1024 * 1024)

    @model_validator(mode="after")
    def valid_path(self) -> ArchiveEntry:
        if not _safe_path(self.path):
            raise ValueError("unsafe archive path")
        return self


class ArchiveManifest(Wire):
    schema_version: Literal[4]
    app_version: str
    renderer_version: str | None
    template_package_sha256: Sha256 | None
    template_assets_included: bool
    project_id: Id | None
    entries: list[ArchiveEntry] = Field(min_length=1, max_length=47)

    @model_validator(mode="after")
    def valid_entries(self) -> ArchiveManifest:
        paths = [entry.path for entry in self.entries]
        _unique(paths, "archive entry")
        if len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("case alias archive entry")
        if [entry.path for entry in self.entries if entry.role == "workspace"] != ["workspace.json"]:
            raise ValueError("workspace entry is required")
        project_paths = [entry.path for entry in self.entries if entry.role == "project"]
        if project_paths != (["project.json"] if self.project_id is not None else []):
            raise ValueError("project entry mismatch")
        if self.project_id is None and (self.renderer_version is not None or self.template_package_sha256 is not None):
            raise ValueError("partial project cannot claim renderer identity")
        if (self.renderer_version is None) != (self.template_package_sha256 is None):
            raise ValueError("renderer and template identity must be paired")
        if self.template_assets_included != any(entry.role == "template_asset" for entry in self.entries):
            raise ValueError("template asset status mismatch")
        for entry in self.entries:
            if entry.role == "render" and not entry.path.startswith("renders/"):
                raise ValueError("render entry path mismatch")
            if entry.role == "template_asset" and not entry.path.startswith("template/"):
                raise ValueError("template entry path mismatch")
        return self


class Project(Wire):
    schema_version: Literal[3]
    project_id: Id
    revision: Revision
    as_of: PartialDate | None
    created_at: str
    sources: list[Source]
    facts: list[Fact]
    employment: list[Job]
    views: list[Block]
    template: TemplateManifest | None
    review: Review
    operations: list[Operation]
    proposals: list[Proposal]
    renders: list[RenderSnapshot]

    @model_validator(mode="after")
    def valid_references(self) -> Project:
        return validate_project(self)


def _unique(items: list[str], label: str) -> set[str]:
    if len(items) != len(set(items)):
        raise ValueError(f"duplicate {label}")
    return set(items)


def _refs(items: list[str], valid: set[str], label: str) -> None:
    if not set(items) <= valid:
        raise ValueError(f"broken {label} reference")


def _safe_path(path: str) -> bool:
    return bool(path) and not path.startswith("/") and "\\" not in path and all(part not in ("", ".", "..") for part in path.split("/"))


def validate_project(project: Project) -> Project:
    if len({(s.id, s.revision) for s in project.sources}) != len(project.sources):
        raise ValueError("duplicate source revision")
    sources = {s.id for s in project.sources}
    facts = _unique([f.id for f in project.facts], "fact ID")
    jobs = _unique([j.id for j in project.employment], "job ID")
    blocks = _unique([b.id for b in project.views], "block ID")
    operations = _unique([o.id for o in project.operations], "operation ID")
    subprojects = _unique([p.id for j in project.employment for p in j.subprojects], "subproject ID")
    fact_by_id = {fact.id: fact for fact in project.facts}
    job_by_id = {job.id: job for job in project.employment}
    unit_owners: dict[str, str] = {}
    for source in project.sources:
        if not _safe_path(source.byte_ref):
            raise ValueError("unsafe source byte reference")
        units = _unique([u.id for u in source.units], "unit ID")
        _unique([str(u.order) for u in source.units], "unit order")
        _unique([o.id for o in source.overlays], "overlay ID")
        _refs([o.unit_id for o in source.overlays], units, "overlay unit")
        for unit in source.units:
            if unit.id in unit_owners and unit_owners[unit.id] != source.id:
                raise ValueError("unit ID belongs to multiple sources")
            unit_owners[unit.id] = source.id
            _refs(unit.represented_fact_ids, facts, "represented fact")
            for fact_id in unit.represented_fact_ids:
                fact = fact_by_id[fact_id]
                if fact.origin != "source" or not any(
                    evidence.source_id == source.id
                    and evidence.source_revision == source.revision
                    and evidence.unit_id == unit.id
                    and evidence.unit_revision == unit.revision
                    for evidence in fact.evidence
                ):
                    raise ValueError("represented fact lacks matching evidence")
    if project.template and any(not _safe_path(asset.path) for asset in project.template.assets):
        raise ValueError("unsafe template asset reference")
    for fact in project.facts:
        if fact.origin == "source" and not fact.evidence:
            raise ValueError("source fact needs evidence")
        if fact.origin == "user" and fact.evidence:
            raise ValueError("user fact cannot invent source evidence")
        for evidence in fact.evidence:
            if evidence.source_id not in sources:
                raise ValueError("broken evidence source reference")
            source = next((s for s in project.sources if s.id == evidence.source_id and s.revision == evidence.source_revision), None)
            if source is None:
                raise ValueError("broken evidence source revision")
            unit = next((u for u in source.units if u.id == evidence.unit_id), None)
            if unit is None or unit.revision != evidence.unit_revision:
                raise ValueError("broken evidence unit reference")
            if fact.id not in unit.represented_fact_ids:
                raise ValueError("source evidence lacks unit representation")
        _refs([fact.job_id] if fact.job_id else [], jobs, "fact job")
        _refs([fact.subproject_id] if fact.subproject_id else [], subprojects, "fact subproject")
        if fact.job_id and fact.id not in job_by_id[fact.job_id].fact_ids:
            raise ValueError("fact missing from owning job")
        if fact.subproject_id and not any(j.id == fact.job_id and any(p.id == fact.subproject_id for p in j.subprojects) for j in project.employment):
            raise ValueError("subproject is outside fact job")
        if fact.subproject_id and not any(
            fact.id in sub.fact_ids
            for job in project.employment if job.id == fact.job_id
            for sub in job.subprojects if sub.id == fact.subproject_id
        ):
            raise ValueError("fact missing from owning subproject")
        if fact.kind == "technology" and fact.value.scope == "global" and (fact.job_id or fact.subproject_id):
            raise ValueError("global technology cannot have dated association")
    for job in project.employment:
        _refs(job.fact_ids, facts, "job fact")
        if any(fact_by_id[fact_id].job_id != job.id for fact_id in job.fact_ids):
            raise ValueError("job lists a fact owned elsewhere")
        for sub in job.subprojects:
            _refs(sub.fact_ids, facts, "subproject fact")
            if any(
                fact_by_id[fact_id].job_id != job.id or fact_by_id[fact_id].subproject_id != sub.id
                for fact_id in sub.fact_ids
            ):
                raise ValueError("subproject lists a fact owned elsewhere")
            if sub.period and job.periods:
                if not any(p.start.lower() <= sub.period.start.lower() and (p.end is None or (sub.period.end is not None and sub.period.end.upper() <= p.end.upper())) for p in job.periods):
                    raise ValueError("subproject period outside job")
    for block in project.views:
        for state in [block.state, block.previous] if block.previous else [block.state]:
            _unique(state.fact_ids, "block fact ID")
            _refs(state.fact_ids, facts, "block fact")
            if set(state.fact_revisions) != set(state.fact_ids):
                raise ValueError("block fact revisions differ from fact IDs")
            if any(revision > fact_by_id[fact_id].revision for fact_id, revision in state.fact_revisions.items()):
                raise ValueError("block refers to future fact revision")
        if block.previous and block.revision < 2:
            raise ValueError("undo state requires later revision")
    for proposal in project.proposals:
        _refs([proposal.block_id], blocks, "proposal block")
        _refs([proposal.operation_id], operations, "proposal operation")
        _refs(proposal.evidence_fact_ids, facts, "proposal fact")
        block = next(b for b in project.views if b.id == proposal.block_id)
        if block.kind not in ("profile", "job_prose"):
            raise ValueError("proposal targets non-prose block")
        if proposal.base_block_revision > block.revision:
            raise ValueError("proposal base revision is in the future")
        operation = next(o for o in project.operations if o.id == proposal.operation_id)
        if operation.kind != proposal.kind:
            raise ValueError("proposal operation kind mismatch")
    for decision in project.review.decisions:
        valid = {u.id for s in project.sources for u in s.units if u.revision == decision.target_revision} if decision.target_kind == "source_unit" else facts if decision.target_kind == "fact" else blocks
        _refs([decision.target_id], valid, "review target")
        if decision.target_kind == "fact" and decision.target_revision > fact_by_id[decision.target_id].revision:
            raise ValueError("review refers to future fact revision")
        if decision.target_kind == "block" and decision.target_revision > next(b.revision for b in project.views if b.id == decision.target_id):
            raise ValueError("review refers to future block revision")
    for ack in project.review.acknowledgments:
        _refs([ack.target_id], facts if ack.target_kind == "fact" else blocks, "acknowledgment target")
        target = next(x for x in (project.facts if ack.target_kind == "fact" else project.views) if x.id == ack.target_id)
        if ack.target_revision != target.revision:
            raise ValueError("expired acknowledgment")
    for render in project.renders:
        _refs([b.block_id for b in render.blocks], blocks, "render block")
        if render.project_revision > project.revision:
            raise ValueError("render refers to future project revision")
        if project.template is None or render.template_id != project.template.id or render.template_version != project.template.version:
            raise ValueError("render template mismatch")
        if any(b.block_revision > next(view.revision for view in project.views if view.id == b.block_id) for b in render.blocks):
            raise ValueError("render block revision is in the future")
        if any(asset is not None and not _safe_path(asset.path) for asset in (render.docx, render.pdf)):
            raise ValueError("unsafe render asset reference")
    model_kinds = {"normalize_semantics", "draft_prose", "rewrite_prose", "reconcile_edits"}
    for operation in project.operations:
        if operation.base_revision > project.revision:
            raise ValueError("operation refers to future project revision")
        if operation.kind not in model_kinds and operation.usage is not None and operation.usage.logical_attempts != 0:
            raise ValueError("deterministic operation cannot have logical model attempts")
        _unique([str(event.sequence) for event in operation.events], "event sequence")
        if any(event.request_id != operation.id for event in operation.events):
            raise ValueError("event request ID mismatch")
    return project


def validate_manifest(manifest: ZipManifest) -> ZipManifest:
    paths = _unique([e.path for e in manifest.entries], "ZIP entry")
    if "project.json" not in paths:
        raise ValueError("ZIP manifest lacks project.json")
    project_entries = [entry for entry in manifest.entries if entry.role == "project"]
    if len(project_entries) != 1 or project_entries[0].path != "project.json":
        raise ValueError("project.json must be the sole project-role entry")
    for path in paths:
        if not _safe_path(path):
            raise ValueError("unsafe ZIP path")
    return manifest


def validate_contract(kind: str, data: object) -> Wire:
    models = {"project": Project, "proposal": Proposal, "template": TemplateManifest,
              "zip_manifest": ZipManifest, "archive_manifest": ArchiveManifest}
    from ..rendering.models import DocxError
    from .agent import AGENT_CONTRACTS
    from .registry import Registry
    from .settings import SETTINGS_CONTRACTS
    from ..rich_panel import RichPanelRequest
    models.update(SETTINGS_CONTRACTS)
    models.update(AGENT_CONTRACTS)
    models.update(registry=Registry, docx_error=DocxError)
    models["rich_panel_request"] = RichPanelRequest
    if kind not in models:
        raise ValueError("unknown contract")
    result = models[kind].model_validate(data)
    return result
