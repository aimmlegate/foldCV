"""Private nonsecret application preferences beside shared Rules."""

import json
import re
from pathlib import Path

from pydantic import ValidationError

from .models.settings import DEFAULT_PROVIDER, Preferences
from .storage import StorageFailure, atomic_write, locked_root, private_file

MODEL = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z')


def migrated(raw):
    """Files of the one-active-provider design (MP01 to MP07): the active provider's choices stay, the kept choices of
    the other one are dropped, and a Claude choice turns Claude on next to Codex (D119)."""
    if not isinstance(raw, dict) or 'enabledProviders' in raw or not {'selectedProvider', 'providerSelections'} & raw.keys():
        return raw
    raw = dict(raw)
    active, kept = raw.pop('selectedProvider', DEFAULT_PROVIDER), raw.pop('providerSelections', {})
    if active not in ('codex_cli', 'claude_cli') or not isinstance(kept, dict) or active in kept:
        raise ValueError()
    raw['enabledProviders'] = [DEFAULT_PROVIDER] + (['claude_cli'] if active == 'claude_cli' else [])
    return raw


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
            value = Preferences.model_validate(migrated(json.loads(raw, object_pairs_hook=unique)))
            for model in (value.selected_model, value.selected_import_model, value.selected_fallback_model,
                          value.selected_rewrite_model):
                if model is not None and not MODEL.fullmatch(model):raise ValueError()
            if len(set(value.enabled_providers)) != len(value.enabled_providers):raise ValueError()
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

    def enable_provider(self, kind, enabled):
        try:
            with locked_root(self.root, '.preferences.lock'):
                value = self._read()
                kinds = [item for item in value.enabled_providers if item != kind]
                value.enabled_providers = [*kinds, kind] if enabled else kinds
                self._write(value)
                return value
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_SAVE_FAILED') from None
