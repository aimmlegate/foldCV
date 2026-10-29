"""Private nonsecret application preferences beside shared Rules."""

import json
import re
from pathlib import Path

from pydantic import ValidationError

from .models.settings import Preferences, ProviderSelection
from .storage import StorageFailure, atomic_write, locked_root, private_file

MODEL = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z')


class PreferencesFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class PreferencesStore:
    def __init__(self, root: Path):
        self.root, self.path = root, root/'preferences.json'

    def _read(self):
        if not self.path.exists() and not self.path.is_symlink():
            # No edit check runs automatically on V7; the flag stays only so older stores remain readable.
            value = Preferences(schemaVersion=1, automaticAnalysis=False, theme='system', selectedModel=None)
            self._write(value)
            return value
        private_file(self.path)
        try:
            raw = self.path.read_bytes()
            if len(raw) > 4096:raise ValueError()
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:raise ValueError()
                    result[key] = value
                return result
            value = Preferences.model_validate(json.loads(raw, object_pairs_hook=unique))
            kept = [model for selection in value.provider_selections.values() for model in (
                selection.selected_model, selection.selected_import_model, selection.selected_fallback_model,
                selection.selected_rewrite_model, selection.selected_agent_model)]
            for model in (value.selected_model, value.selected_import_model, value.selected_fallback_model,
                          value.selected_rewrite_model, *kept):
                if model is not None and not MODEL.fullmatch(model):raise ValueError()
            if value.selected_provider in value.provider_selections:raise ValueError()
            return value
        except (OSError, ValueError, ValidationError):
            raise PreferencesFailure('PREFERENCES_CORRUPT') from None

    def _write(self, value):
        atomic_write(self.path, (value.model_dump_json(by_alias=True, indent=2)+'\n').encode())

    def load(self):
        try:
            with locked_root(self.root, '.preferences.lock'):return self._read()
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_UNAVAILABLE') from None

    def select_model(self, model):
        if not MODEL.fullmatch(model):raise PreferencesFailure('MODEL_DENIED')
        try:
            with locked_root(self.root, '.preferences.lock'):
                value = self._read();value.selected_model = model;self._write(value);return value
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_SAVE_FAILED') from None

    def select_rewrite_reasoning(self, model, effort):
        try:
            with locked_root(self.root, '.preferences.lock'):
                value = self._read()
                if (value.selected_rewrite_model or value.selected_model) != model:
                    raise PreferencesFailure('MODEL_DENIED')
                value.rewrite_reasoning_effort = effort
                self._write(value)
                return value
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_SAVE_FAILED') from None

    def select_rewrite_model(self, model, supported):
        """`supported`: the levels the resulting rewrite model reports; a saved level outside them goes back to its default."""
        if model is not None and not MODEL.fullmatch(model):
            raise PreferencesFailure('MODEL_DENIED')
        try:
            with locked_root(self.root, '.preferences.lock'):
                value = self._read()
                value.selected_rewrite_model = model
                if value.rewrite_reasoning_effort not in supported:
                    value.rewrite_reasoning_effort = None
                self._write(value)
                return value
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_SAVE_FAILED') from None

    def save_analysis(self, enabled):
        try:
            with locked_root(self.root, '.preferences.lock'):
                value = self._read()
                value.automatic_analysis = enabled
                self._write(value)
                return value
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_SAVE_FAILED') from None

    def save_limits(self, import_minutes, project_megabytes):
        try:
            with locked_root(self.root, '.preferences.lock'):
                value = self._read()
                value.import_minutes, value.project_megabytes = import_minutes, project_megabytes
                value = Preferences.model_validate(value.model_dump(by_alias=True))
                self._write(value)
                return value
        except ValidationError:
            raise PreferencesFailure('INVALID_REQUEST') from None
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_SAVE_FAILED') from None

    def select_import_model(self, model):
        if model is not None and not MODEL.fullmatch(model):
            raise PreferencesFailure('MODEL_DENIED')
        try:
            with locked_root(self.root, '.preferences.lock'):
                value = self._read()
                value.selected_import_model = model
                self._write(value)
                return value
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_SAVE_FAILED') from None

    def select_fallback_model(self, model):
        if model is not None and not MODEL.fullmatch(model):
            raise PreferencesFailure('MODEL_DENIED')
        try:
            with locked_root(self.root, '.preferences.lock'):
                value = self._read()
                value.selected_fallback_model = model
                self._write(value)
                return value
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_SAVE_FAILED') from None

    def select_provider(self, kind, agent_model, agent_effort=None):
        """Keeps the outgoing provider's choices, including the assistant model and effort held in their own
        file, and restores the incoming provider's; returns the preferences and the assistant pair to restore."""
        try:
            with locked_root(self.root, '.preferences.lock'):
                value = self._read()
                if value.selected_provider == kind:
                    return value, (agent_model, agent_effort)
                selections = dict(value.provider_selections)
                selections[value.selected_provider] = ProviderSelection(
                    selectedModel=value.selected_model, selectedImportModel=value.selected_import_model,
                    selectedFallbackModel=value.selected_fallback_model, selectedRewriteModel=value.selected_rewrite_model,
                    rewriteReasoningEffort=value.rewrite_reasoning_effort, selectedAgentModel=agent_model,
                    agentReasoningEffort=agent_effort)
                restored = selections.pop(kind, ProviderSelection())
                value.selected_provider = kind
                value.selected_model, value.selected_import_model = restored.selected_model, restored.selected_import_model
                value.selected_fallback_model = restored.selected_fallback_model
                value.selected_rewrite_model = restored.selected_rewrite_model
                value.rewrite_reasoning_effort = restored.rewrite_reasoning_effort
                value.provider_selections = selections
                self._write(value)
                return value, (restored.selected_agent_model, restored.agent_reasoning_effort)
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_SAVE_FAILED') from None
