"""Typed mutable facts, separate from immutable source evidence."""

from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeVar, Union

from pydantic import Field, model_validator

from .contracts import Id, LeadershipValue, MetricValue, PartialDate, Revision, Wire, _unique
from .recovery import EvidenceSpan

T = TypeVar("T")


class WorkingField(Wire, Generic[T]):
    value: T | None
    raw_text: str
    status: Literal["known", "unknown", "unresolved", "pending", "conflict"]
    revision: Revision
    pending_raw_text: str | None
    user_corrected: bool = False

    @model_validator(mode="after")
    def authority(self) -> WorkingField[T]:
        if self.status == "known" and self.value is None:
            raise ValueError("known field needs a value")
        if self.status in {"unknown", "unresolved"} and self.value is not None:
            raise ValueError("unknown field cannot claim a typed value")
        if (self.status == "pending") != (self.pending_raw_text is not None):
            raise ValueError("pending interpretation needs retained input only while pending")
        return self


TextField = WorkingField[str]
DateField = WorkingField[PartialDate]
BooleanField = WorkingField[bool]


class WorkingRecord(Wire):
    id: Id
    revision: Revision
    origin: Literal["source", "user"]
    evidence: list[EvidenceSpan]
    user_corrected: bool = False

    @model_validator(mode="after")
    def coherent_revisions(self) -> WorkingRecord:
        for key in type(self).model_fields:
            value = getattr(self, key)
            if isinstance(value, WorkingField) and value.revision > self.revision:
                raise ValueError("field revision exceeds working record")
            if key == "periods" and any(period.revision > self.revision for period in value):
                raise ValueError("period revision exceeds working record")
        return self


class CandidateRecord(WorkingRecord):
    kind: Literal["candidate"]
    name: TextField
    title: TextField
    location: TextField


class DetailRecord(WorkingRecord):
    kind: Literal["detail"]
    detail_type: Literal["phone", "email", "url", "messenger", "age", "birth_date", "metadata", "other"]
    label: str
    value: TextField


class WorkingPeriod(Wire):
    id: Id
    revision: Revision
    start: DateField
    end: DateField
    present: BooleanField
    evidence: list[EvidenceSpan]

    @model_validator(mode="after")
    def coherent_revisions(self) -> WorkingPeriod:
        if any(part.revision > self.revision for part in (self.start, self.end, self.present)):
            raise ValueError("date field revision exceeds period")
        return self


class EmploymentRecord(WorkingRecord):
    kind: Literal["employment"]
    employer: TextField
    role: TextField
    periods: list[WorkingPeriod]


class SubprojectRecord(WorkingRecord):
    kind: Literal["subproject"]
    job_id: Id
    name: TextField
    role: TextField
    periods: list[WorkingPeriod]


class TechnologyRecord(WorkingRecord):
    kind: Literal["technology"]
    job_id: Id | None
    subproject_id: Id | None
    display: TextField
    canonical_id: TextField
    technical: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    experience: TextField = Field(default_factory=lambda: TextField(value=None, rawText="", status="unknown",
        revision=1, pendingRawText=None), exclude_if=lambda value: not value.raw_text and not value.user_corrected)


class EducationRecord(WorkingRecord):
    kind: Literal["education"]
    institution: TextField
    qualification: TextField
    specialty: TextField
    completion: DateField


class LanguageRecord(WorkingRecord):
    kind: Literal["language"]
    language: TextField
    level: TextField


class CertificationRecord(WorkingRecord):
    kind: Literal["certification"]
    name: TextField
    issuer: TextField
    date: DateField


class ClaimRecord(WorkingRecord):
    kind: Literal["claim"]
    job_id: Id | None
    subproject_id: Id | None
    value: TextField


class MetricRecord(WorkingRecord):
    kind: Literal["metric"]
    job_id: Id | None
    subproject_id: Id | None
    value: WorkingField[MetricValue]


class LeadershipRecord(WorkingRecord):
    kind: Literal["leadership"]
    job_id: Id | None
    subproject_id: Id | None
    value: WorkingField[LeadershipValue]


class UnresolvedRecord(WorkingRecord):
    kind: Literal["unresolved"]
    category: Literal["education", "certification", "language", "employment", "detail", "other"]
    status: Literal["unresolved", "pending", "conflict"]


RichFact = Annotated[Union[CandidateRecord, DetailRecord, EmploymentRecord, SubprojectRecord,
                          TechnologyRecord, EducationRecord, LanguageRecord, CertificationRecord,
                          ClaimRecord, MetricRecord, LeadershipRecord, UnresolvedRecord], Field(discriminator="kind")]


class RecordTombstone(Wire):
    record_id: Id
    revision: Revision
    action_id: Id
    order_index: int = Field(ge=0)


class ExtractionIssue(Wire):
    code: Literal["FACT_SOURCE_UNRESOLVED", "FACT_SECTION_OMITTED", "FACT_ROWS_RECOVERED"]
    source_id: Id
    unit_id: Id | None
    page: int | None = Field(default=None, ge=1)
    section: str


class ExtractionReport(Wire):
    status: Literal["complete", "partial"]
    fact_count: int = Field(ge=0)
    counts: dict[str, int]
    request_bytes: int = Field(ge=0)
    recovered_rows: int = Field(ge=0)
    unresolved: list[ExtractionIssue] = Field(max_length=5000)


class WorkingFacts(Wire):
    revision: Revision
    records: list[RichFact]
    tombstones: list[RecordTombstone]
    extraction: ExtractionReport | None = None
    mode: Literal["structured", "digest", "imported"] = Field(default="structured", exclude_if=lambda value: value == "structured")

    @model_validator(mode="after")
    def identity(self) -> WorkingFacts:
        record_ids = _unique([record.id for record in self.records], "working record")
        tombstones = _unique([item.record_id for item in self.tombstones], "record tombstone")
        if record_ids & tombstones:
            raise ValueError("removed record cannot also be current")
        _unique([period.id for record in self.records if isinstance(record, (EmploymentRecord, SubprojectRecord))
                 for period in record.periods], "working period")
        return self
