"""Where the facts panel places a record and adds a technology; the panel edits and the editor plan share them."""

from __future__ import annotations

from pydantic import Field
from .contracts import Id, Wire


class EditorPlacement(Wire):
    """A block's parent block or region and the sibling before it, as a panel placement context names them."""
    parent_id: Id
    after_id: Id | None


class EditorTechnologyTarget(Wire):
    """Where the facts panel adds a technology: a line of one scope, a job section that has none yet, or a group view
    the document no longer shows (block id view:<view id>)."""
    block_id: Id
    job_id: Id | None
    # The view title the panel names when one scope has several lines.
    label: str
    # The block's place, or where the view's line goes; the panel sends it back and Python refuses an older one.
    placement: EditorPlacement
    # A skill group's technologies in the order its line shows them (D136); a job's target lists none.
    records: list[Id] = Field(default_factory=list, exclude_if=lambda value: not value)
