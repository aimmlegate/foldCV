"""Bounded composite mutations and dependency captures for rich sessions."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from .contracts import Id, PartialDate, Revision, Sha256, Wire, _unique
from .rich_document import RichBlock, RichInline
from .rich_facts import RichFact, WorkingPeriod


class DependencyStamp(Wire):
    kind: Literal["block", "record", "field", "period", "ownership", "source", "rules", "asset", "timeline_order"]
    id: Id
    revision: Revision
    fingerprint: Sha256 | None


class ActionCapture(Wire):
    session_id: Id
    action_id: Id
    action_token: int = Field(ge=0)
    dependencies: list[DependencyStamp]

    @model_validator(mode="after")
    def dependency_keys(self) -> ActionCapture:
        _unique([f"{item.kind}:{item.id}" for item in self.dependencies], "dependency")
        return self


class RichPosition(Wire):
    block_id: Id
    cell_id: Id | None
    offset: int = Field(ge=0, description="UTF-16 code units within the block or cell.")


class RichSelection(Wire):
    kind: Literal["text", "blocks", "table_cells"]
    anchor: RichPosition
    head: RichPosition
    block_ids: list[Id] = Field(min_length=1)
    capture: ActionCapture
    text_sha256: Sha256


class PutBlock(Wire):
    kind: Literal["put_block"]
    parent_id: Id
    after_id: Id | None
    before_revision: Revision | None
    block: RichBlock


class RemoveBlock(Wire):
    kind: Literal["remove_block"]
    block_id: Id
    before_revision: Revision


class MoveBlock(Wire):
    kind: Literal["move_block"]
    block_id: Id
    before_revision: Revision
    parent_id: Id
    after_id: Id | None


class ReplaceInlineRange(Wire):
    kind: Literal["replace_inline_range"]
    block_id: Id
    cell_id: Id | None
    field: Literal["content", "caption"]
    start: int = Field(ge=0, description="UTF-16 code units within the selected inline field.")
    end: int = Field(ge=0, description="UTF-16 code units within the selected inline field.")
    before_revision: Revision
    content: list[RichInline]

    @model_validator(mode="after")
    def ordered_range(self) -> ReplaceInlineRange:
        if self.end < self.start:
            raise ValueError("inline range ends before its start")
        return self


class PutRecord(Wire):
    kind: Literal["put_record"]
    before_revision: Revision | None
    record: RichFact


class RemoveRecord(Wire):
    kind: Literal["remove_record"]
    record_id: Id
    before_revision: Revision


RichStep = Annotated[Union[PutBlock, RemoveBlock, MoveBlock, ReplaceInlineRange, PutRecord, RemoveRecord], Field(discriminator="kind")]


class RichMutation(Wire):
    schema_version: Literal[1]
    project_id: Id
    client_mutation_id: Id
    action_id: Id
    kind: Literal["typing", "composition", "structure", "panel", "rewrite", "reconciliation", "cascade", "undo", "redo"]
    capture: ActionCapture
    steps: list[RichStep] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def bounded_patch(self) -> RichMutation:
        if len(self.model_dump_json(by_alias=True).encode("utf-8")) > 1024 * 1024:
            raise ValueError("rich mutation exceeds 1 MiB")
        return self


class DateShift(Wire):
    job_id: Id
    period_id: Id
    before: WorkingPeriod
    after: WorkingPeriod
    unit: Literal["month", "day"]
    inclusive_span: int = Field(ge=1)

    @model_validator(mode="after")
    def same_period(self) -> DateShift:
        if self.before.id != self.period_id or self.after.id != self.period_id:
            raise ValueError("shift must retain period identity")
        for period in (self.before, self.after):
            if period.present.value is not False or any(
                part.status != "known" or part.value is None or part.value.precision != self.unit
                for part in (period.start, period.end)
            ):
                raise ValueError("shift requires closed periods at one exact precision")
        return self


class DateCascadeProposal(Wire):
    id: Id
    anchor_job_id: Id
    anchor_period_id: Id
    formatting_as_of: PartialDate
    capture: ActionCapture
    period_order: list[Id]
    shifts: list[DateShift]
    status: Literal["available", "unavailable", "stale", "applied", "dismissed"]
    reason: Id | None
    warnings: list[Id]

    @model_validator(mode="after")
    def preview_identity(self) -> DateCascadeProposal:
        _unique(self.period_order, "cascade period order")
        _unique([shift.period_id for shift in self.shifts], "cascade shift")
        if self.anchor_period_id not in self.period_order:
            raise ValueError("anchor missing from frozen order")
        if any(shift.period_id == self.anchor_period_id or shift.period_id not in self.period_order for shift in self.shifts):
            raise ValueError("cascade cannot move anchor or an uncaptured period")
        if self.status == "unavailable" and self.shifts:
            raise ValueError("unavailable cascade cannot expose a computable prefix")
        if self.status == "available" and (not self.shifts or self.reason is not None):
            raise ValueError("available cascade requires shifts without a failure")
        if self.status == "available":
            if len({shift.unit for shift in self.shifts}) != 1:
                raise ValueError("cascade chain cannot mix month and day units")
            stamps = {item.id for item in self.capture.dependencies if item.kind == "period"}
            if not {self.anchor_period_id, *(shift.period_id for shift in self.shifts)} <= stamps:
                raise ValueError("cascade needs all affected period dependencies")
            if not any(item.kind == "timeline_order" and item.fingerprint is not None for item in self.capture.dependencies):
                raise ValueError("cascade needs the frozen timeline order dependency")
        if self.status == "unavailable" and self.reason is None:
            raise ValueError("unavailable cascade needs a reason")
        return self
