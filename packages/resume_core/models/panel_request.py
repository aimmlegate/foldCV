"""A facts panel request: the operation, the record and the values the panel sends."""

from __future__ import annotations

from .contracts import Id, Revision, Wire
from .rich_mutations import ActionCapture
from pydantic import ConfigDict
from pydantic import Field
from typing import Literal
from pydantic import model_validator


PanelKind = Literal["candidate", "employment", "technology", "education", "language", "claim"]


class RichPanelRequest(Wire):
    model_config = ConfigDict(json_schema_extra={
        "if": {"properties": {"operation": {"const": "clear_technologies"}}, "required": ["operation"]},
        "then": {"properties": {"recordKind": {"const": "technology"}, "recordId": {"type": "null"},
            "periodId": {"type": "null"}, "values": {"maxProperties": 0}}, "required": ["recordKind"]},
        "else": {"if": {"properties": {"operation": {"enum": ["add_to_focus", "remove_from_focus"]}}, "required": ["operation"]},
            "then": {"properties": {"recordId": {"type": "string"}, "recordKind": {"enum": [None, "technology"]},
                "jobId": {"type": "null"}, "periodId": {"type": "null"}, "values": {"maxProperties": 0}}, "required": ["recordId"]},
            # A Focus row's icon: one of the template's icons, or "" for the template's own choice (D122).
            "else": {"if": {"properties": {"operation": {"const": "set_focus_icon"}}, "required": ["operation"]},
                "then": {"properties": {"recordId": {"type": "string"}, "recordKind": {"enum": [None, "technology"]},
                    "jobId": {"type": "null"}, "periodId": {"type": "null"},
                    "values": {"required": ["icon"], "maxProperties": 1}}, "required": ["recordId"]}}},
    })
    operation: Literal["add", "edit", "remove", "add_period", "remove_period", "clear_technologies", "add_to_focus", "remove_from_focus", "move_technology", "move_focus", "set_focus_icon", "add_technology_group"]
    record_id: Id | None = None
    record_kind: PanelKind | None = None
    job_id: Id | None = None
    period_id: Id | None = None
    before_record_id: Id | None = Field(default=None, exclude_if=lambda value: value is None)
    # The skill group a technology moves to or leaves, as the plan's general target names it (D136).
    group_id: Id | None = Field(default=None, exclude_if=lambda value: value is None)
    values: dict[str, str] = Field(default_factory=dict, max_length=50)
    facts_revision: Revision
    document_revision: Revision
    capture: ActionCapture

    @model_validator(mode="after")
    def operation_scope(self):
        if self.before_record_id is not None and self.operation not in {"move_technology", "move_focus"}:
            raise ValueError("TECHNOLOGY_MOVE_INVALID")
        if self.group_id is not None and self.operation not in {"move_technology", "remove"}:
            raise ValueError("TECHNOLOGY_GROUP_INVALID")
        if self.operation in {"move_technology", "move_focus"} and (self.record_id is None
                or self.record_kind not in {None, "technology"} or self.job_id is not None or self.period_id is not None or self.values):
            raise ValueError("TECHNOLOGY_MOVE_INVALID")
        if self.operation == "move_focus" and self.group_id is not None:
            raise ValueError("TECHNOLOGY_MOVE_INVALID")
        # A new skill group with its first technology: a new name, or a technology moved from its group (D136).
        if self.operation == "add_technology_group" and (self.record_kind not in {None, "technology"} or self.job_id is not None
                or self.period_id is not None or "title" not in self.values
                or set(self.values) != ({"title"} if self.record_id is not None else {"title", "display"})):
            raise ValueError("TECHNOLOGY_GROUP_INVALID")
        if self.operation in {"add_to_focus", "remove_from_focus"} and (self.record_id is None
                or self.record_kind not in {None, "technology"} or self.job_id is not None or self.period_id is not None or self.values):
            raise ValueError("FOCUS_SCOPE_INVALID")
        if self.operation == "set_focus_icon" and (self.record_id is None or self.record_kind not in {None, "technology"}
                or self.job_id is not None or self.period_id is not None or set(self.values) != {"icon"}
                or len(self.values["icon"]) > 128):
            raise ValueError("FOCUS_SCOPE_INVALID")
        if self.operation == "clear_technologies" and (self.record_kind != "technology" or self.record_id is not None
                or self.period_id is not None or self.values):
            raise ValueError("PANEL_CLEAR_INVALID")
        return self
