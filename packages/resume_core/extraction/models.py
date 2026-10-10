"""Extraction transport; project v3 is unchanged."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from packages.resume_core.models.contracts import Wire, Sha256


class ExtractLocation(Wire):
    model_config = ConfigDict(populate_by_name=True)
    kind: Literal["page", "paragraph", "table_cell", "header", "footer", "image", "pasted"]
    page: int | None = Field(default=None, ge=1)
    paragraph: int | None = Field(default=None, ge=0)
    table: int | None = Field(default=None, ge=0)
    row: int | None = Field(default=None, ge=0)
    column: int | None = Field(default=None, ge=0)
    part: str | None = Field(default=None, max_length=120)


class ExtractUnit(Wire):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(min_length=1, max_length=80)
    order: int = Field(ge=0)
    text: str = Field(max_length=750_000)
    location: ExtractLocation


class ExtractGap(Wire):
    model_config = ConfigDict(populate_by_name=True)
    code: Literal["NO_TEXT", "IMAGE", "SHAPE", "TEXT_BOX", "UNSUPPORTED_CONTENT"]
    location: ExtractLocation


class ExtractLink(Wire):
    model_config = ConfigDict(populate_by_name=True)
    part: str = Field(min_length=1, max_length=120)
    relationship_id: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=2048)


class ExtractResult(Wire):
    model_config = ConfigDict(populate_by_name=True)
    source_id: str = Field(min_length=1, max_length=80)
    source_kind: Literal["pdf", "docx", "txt", "markdown", "paste"]
    original_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    byte_sha256: Sha256
    byte_length: int = Field(ge=0, le=6_291_456)
    byte_ref: str = Field(min_length=1, max_length=120)
    parser: str = Field(min_length=1, max_length=60)
    parser_version: str = Field(min_length=1, max_length=60)
    page_count: int | None = Field(default=None, ge=1, le=40)
    units: list[ExtractUnit] = Field(max_length=5_000)
    gaps: list[ExtractGap] = Field(max_length=5_000)
    links: list[ExtractLink] = Field(max_length=100)

    @model_validator(mode="after")
    def valid_order(self) -> ExtractResult:
        if [unit.order for unit in self.units] != list(range(len(self.units))):
            raise ValueError("units are not ordered")
        if [unit.id for unit in self.units] != [f"unit_{index + 1}" for index in range(len(self.units))]:
            raise ValueError("unit IDs are not ordered")
        if self.source_id != "source_" + self.byte_sha256[:24] or self.byte_ref != "memory:sha256:" + self.byte_sha256:
            raise ValueError("source bytes identity mismatch")
        if sum(len(unit.text.encode("utf-8")) for unit in self.units) > 2 * 1024 * 1024 or sum(len(unit.text) for unit in self.units) > 750_000:
            raise ValueError("extraction text limit")
        if (self.source_kind == "pdf") != (self.page_count is not None):
            raise ValueError("PDF page count mismatch")
        if self.page_count is not None and any(location.page is not None and location.page > self.page_count
                                               for location in [*(unit.location for unit in self.units),
                                                                *(gap.location for gap in self.gaps)]):
            raise ValueError("page location outside source")
        return self
