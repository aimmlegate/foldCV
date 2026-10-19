"""Reasoning choices come from the connected model catalog."""

from typing import Literal
from pydantic import Field
from .models.contracts import Wire

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}


class ModelReasoning(Wire):
    supported: list[ReasoningEffort] = Field(max_length=8)
    default: ReasoningEffort | None = None


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
    return ModelReasoning(supported=supported, default=default)
