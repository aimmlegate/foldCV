"""Bundled Claude model catalog; the CLI has no list command (decision 8: pinned, no remote fetch)."""

from __future__ import annotations

from dataclasses import dataclass

from packages.resume_core.reasoning import ModelReasoning
from resume_api.cli.qualification import Version


EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class CatalogModel:
    id: str
    name: str
    min_version: str | None
    default_effort: str | None

    def reasoning(self) -> ModelReasoning:
        if self.default_effort is None:
            return ModelReasoning(supported=[], default=None)
        return ModelReasoning(supported=list(EFFORTS), default=self.default_effort)


# Taken from T3's model manifest of 2026-10-21; `ultracode` and `ultrathink` are excluded.
# Catalog membership is not entitlement; only a real call proves access.
MODELS = (
    CatalogModel("claude-opus-5-5", "Claude Opus 5.5", "2.1.280", "medium"),
    CatalogModel("claude-sonnet-5-5", "Claude Sonnet 5.5", "2.1.284", "high"),
    CatalogModel("claude-fable-5-1", "Claude Fable 5.1", "2.1.257", "medium"),
    CatalogModel("claude-haiku-5-5", "Claude Haiku 5.5", "2.1.293", "medium"),
)


def models_for(version: Version) -> tuple[CatalogModel, ...]:
    return tuple(model for model in MODELS
                 if model.min_version is None or Version.parse(model.min_version) <= version)


def reasoning_for(version: Version) -> dict[str, ModelReasoning]:
    return {model.id: model.reasoning() for model in models_for(version)}
