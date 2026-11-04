"""Reasoning choices come from the connected model catalog."""

from typing import Literal
from pydantic import Field
from .models.contracts import Wire

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
EFFORTS = set(LEVELS)


class ModelReasoning(Wire):
    supported: list[ReasoningEffort] = Field(max_length=8)
    default: ReasoningEffort | None = None


def default_effort(supported, reported):
    """The level a run takes when none is chosen (D144): high when the model offers levels above it, medium when high is
    its top, else the catalog's own default."""
    if "high" in supported and any(LEVELS.index(level) > LEVELS.index("high") for level in supported):
        return "high"
    if "medium" in supported:
        return "medium"
    return reported


def model_reasoning(item):
    values = item.get("supportedReasoningEfforts", [])
    default = item.get("defaultReasoningEffort")
    if not isinstance(values, list):
        raise ValueError("invalid reasoning metadata")
    supported = []
    for value in values:
        effort = value.get("reasoningEffort") if isinstance(value, dict) else None
        if not isinstance(effort, str) or effort not in EFFORTS or effort in supported:
            raise ValueError("invalid reasoning effort")
        supported.append(effort)
    if default is not None and default not in supported:
        raise ValueError("invalid default reasoning effort")
    return ModelReasoning(supported=supported, default=default_effort(supported, default))
