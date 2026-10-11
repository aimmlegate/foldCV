"""Reject known private fields in the document that would actually be rendered."""

from __future__ import annotations

from collections.abc import Iterator

from packages.resume_core.privacy import private_output_text
from packages.resume_core.rendering.models import RenderDocument
from packages.resume_core.rendering.template import RenderFailure


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _strings(child)


def guard_render_document(document: RenderDocument) -> None:
    candidate = document.candidate
    sections: tuple[tuple[str, object], ...] = (
        ("IDENTITY", (candidate.name, candidate.title)),
        ("PROFILE", candidate.summary),
        ("JOB", [item.model_dump(mode="python") for item in document.projects]),
        ("FOCUS", [item.model_dump(mode="python") for item in document.focus]),
        ("SIDEBAR", [item.model_dump(mode="python") for item in document.sidebar]),
        ("SKILLS", [item.model_dump(mode="python") for item in document.skill_groups]),
        ("ACHIEVEMENTS", document.achievements),
        ("FOOTER", document.footer),
    )
    for section, values in sections:
        if any(private_output_text(text) for text in _strings(values)):
            raise RenderFailure(f"PRIVATE_OUTPUT_{section}")
