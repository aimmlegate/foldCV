"""Settings contracts: content rules and service preferences."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from ..project_limits import IMPORT_MINUTES, PROJECT_MEGABYTES
from ..reasoning import ReasoningEffort
from .contracts import Revision, Sha256, Wire


class Rules(Wire):
    model_config = ConfigDict(frozen=True)
    markdown: str
    revision: Revision
    sha256: Sha256


class SaveRulesRequest(Wire):
    markdown: str = Field(min_length=1, max_length=32_768)
    base_revision: Revision


class RulePresets(Wire):
    shorten: str = Field(min_length=1)
    clarify: str = Field(min_length=1)


class RulesSettings(Rules):
    presets: RulePresets


class RulesErrorPayload(Wire):
    code: Literal["RULES_PRESETS_REQUIRED", "RULES_STALE", "RULES_TOO_LARGE",
                  "RULES_INVALID_TEXT", "RULES_LOAD_FAILED", "RULES_SAVE_FAILED", "RULES_UNSAFE_STORAGE"]
    retryable: Literal[False]
    stage: Literal["rules"]


class RulesSettingsError(Wire):
    error: RulesErrorPayload
    required_headings: list[Literal["## Preset: shorten", "## Preset: clarify"]]


class Preferences(Wire):
    schema_version: Literal[1]
    automatic_analysis: bool
    theme: Literal["light", "dark", "system"]
    selected_model: str | None
    selected_import_model: str | None = None
    # E07: one more repair by this model after the import model's own repair; None disables it.
    selected_fallback_model: str | None = None
    rewrite_reasoning_effort: ReasoningEffort | None = None
    import_minutes: int = Field(default=IMPORT_MINUTES[0], ge=IMPORT_MINUTES[1], le=IMPORT_MINUTES[2])
    project_megabytes: int = Field(default=PROJECT_MEGABYTES[0], ge=PROJECT_MEGABYTES[1], le=PROJECT_MEGABYTES[2])


class SaveImportModelPreference(Wire):
    model: str | None = Field(max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")


class SaveLimitsPreference(Wire):
    import_minutes: int = Field(ge=IMPORT_MINUTES[1], le=IMPORT_MINUTES[2])
    project_megabytes: int = Field(ge=PROJECT_MEGABYTES[1], le=PROJECT_MEGABYTES[2])


class SaveAnalysisPreference(Wire):
    automatic_analysis: bool


SETTINGS_CONTRACTS = {
    "rules": Rules, "rules_settings": RulesSettings, "rules_settings_error": RulesSettingsError,
    "save_rules_request": SaveRulesRequest, "preferences": Preferences,
    "save_import_model_preference": SaveImportModelPreference, "save_limits_preference": SaveLimitsPreference,
}
