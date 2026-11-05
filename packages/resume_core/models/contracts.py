"""The shared wire base, ids, partial dates, sources, evidence and value models, and the template manifest the V6
workspace carries."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

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


def _unique(items: list[str], label: str) -> set[str]:
    if len(items) != len(set(items)):
        raise ValueError(f"duplicate {label}")
    return set(items)


def _safe_path(path: str) -> bool:
    return bool(path) and not path.startswith("/") and "\\" not in path and all(part not in ("", ".", "..") for part in path.split("/"))
