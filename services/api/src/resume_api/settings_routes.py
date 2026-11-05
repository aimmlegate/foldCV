"""The /v1/settings routes: rules, preferences, limits and the import, fallback and rewrite model choices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi.responses import JSONResponse

from packages.resume_core.models.settings import (RulesSettings, RulesSettingsError, SaveAnalysisPreference,
    SaveImportModelPreference, SaveLimitsPreference, SaveRulesRequest)
from packages.resume_core.repository.preferences import PreferencesFailure, PreferencesStore
from packages.resume_core.project_limits import apply_preferences as apply_limits
from packages.resume_core.rules import PRESET_HEADINGS, RulesFailure, RulesStore, presets

from .host_models import SelectReasoningRequest


@dataclass
class SettingsContext:
    """What the settings routes share with the connection routes: the same gate object and the live catalog."""
    rules_store: RulesStore
    preferences_store: PreferencesStore
    gate: object
    catalog: Callable
    reasoning_of: Callable
    processing_model: Callable
    connection_response: Callable
    problem: Callable


def mount_settings_routes(app, ctx: SettingsContext):
    rules_store, preferences_store, gate = ctx.rules_store, ctx.preferences_store, ctx.gate
    catalog, reasoning_of, processing_model = ctx.catalog, ctx.reasoning_of, ctx.processing_model
    connection_response, problem = ctx.connection_response, ctx.problem

    def rules_failure(error: RulesFailure):
        status = 409 if error.code == "RULES_STALE" else 422 if error.code in {
            "RULES_PRESETS_REQUIRED", "RULES_PRESET_TOO_LONG", "RULES_TOO_LARGE", "RULES_INVALID_TEXT"} else 500
        payload = RulesSettingsError.model_validate({
            "error": {"code": error.code, "retryable": False, "stage": "rules"},
            "requiredHeadings": list(PRESET_HEADINGS.values()) if error.code == "RULES_PRESETS_REQUIRED" else [],
        })
        return JSONResponse(payload.model_dump(mode="json", by_alias=True), status_code=status,
                            headers={"Cache-Control": "no-store"})

    def rules_response(captured):
        value = {**captured.model_dump(mode="json", by_alias=True), "presets": presets(captured.markdown)}
        payload = RulesSettings.model_validate(value)
        return JSONResponse(payload.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.get("/v1/settings/rules")
    async def read_rules():
        try:
            captured = rules_store.load()
            return rules_response(captured)
        except RulesFailure as error:
            return rules_failure(error)

    @app.put("/v1/settings/rules")
    async def save_rules(request: SaveRulesRequest):
        try:
            captured = rules_store.save(request.markdown, request.base_revision)
            return rules_response(captured)
        except RulesFailure as error:
            return rules_failure(error)

    @app.get("/v1/settings/connection")
    async def current_connection():
        return connection_response()

    @app.get("/v1/settings/preferences")
    async def preferences():
        try:
            rules_store.load()
            value = preferences_store.load()
            return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
        except (PreferencesFailure, RulesFailure) as error:
            return problem(error.code, 409, "settings")

    @app.put("/v1/settings/preferences")
    async def save_analysis_preferences(payload: SaveAnalysisPreference):
        try:
            rules_store.load()
            value = preferences_store.save_analysis(payload.automatic_analysis)
            return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
        except (PreferencesFailure, RulesFailure) as error:
            return problem(error.code, 409, "settings")

    @app.put("/v1/settings/limits")
    async def save_limits(payload: SaveLimitsPreference):
        try:
            rules_store.load()
            value = preferences_store.save_limits(payload.import_minutes, payload.project_megabytes)
            apply_limits(value)
            return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
        except (PreferencesFailure, RulesFailure) as error:
            return problem(error.code, 409, "settings")

    @app.put("/v1/settings/import-model")
    async def save_import_model(payload: SaveImportModelPreference):
        async with gate:
            if payload.model is not None and payload.model not in catalog():
                return problem("MODEL_DENIED", 409, "settings")
            try:
                rules_store.load()
                value = preferences_store.select_import_model(payload.model)
                return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
            except (PreferencesFailure, RulesFailure) as error:
                return problem(error.code, 409, "settings")

    @app.put("/v1/settings/fallback-model")
    async def save_fallback_model(payload: SaveImportModelPreference):
        async with gate:
            if payload.model is not None and payload.model not in catalog():
                return problem("MODEL_DENIED", 409, "settings")
            try:
                rules_store.load()
                value = preferences_store.select_fallback_model(payload.model)
                return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
            except (PreferencesFailure, RulesFailure) as error:
                return problem(error.code, 409, "settings")

    @app.put("/v1/settings/rewrite-model")
    async def save_rewrite_model(payload: SaveImportModelPreference):
        async with gate:
            owners = catalog()
            if not owners or payload.model is not None and payload.model not in owners:
                return problem("MODEL_DENIED", 409, "settings")
            metadata = reasoning_of(payload.model or processing_model() or "")
            try:
                rules_store.load()
                value = preferences_store.select_rewrite_model(payload.model, set(metadata.supported if metadata else ()))
                return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
            except (PreferencesFailure, RulesFailure) as error:
                return problem(error.code, 409, "settings")

    @app.put("/v1/settings/rewrite-reasoning")
    async def save_rewrite_reasoning(payload: SelectReasoningRequest):
        async with gate:
            metadata = reasoning_of(payload.model)
            # The store checks the model against the rewrite model, which follows the processing model when unset.
            if (payload.model not in catalog()
                    or payload.effort is not None and (metadata is None or payload.effort not in metadata.supported)):
                return problem("MODEL_DENIED", 409, "settings")
            try:
                value = preferences_store.select_rewrite_reasoning(payload.model, payload.effort)
                return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
            except PreferencesFailure as error:
                return problem(error.code, 409, "settings")
