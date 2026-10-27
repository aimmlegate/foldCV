"""A cited source span with its text."""

from __future__ import annotations

from pydantic import Field

from .contracts import Evidence


class EvidenceSpan(Evidence):
    text: str = Field(min_length=1)
