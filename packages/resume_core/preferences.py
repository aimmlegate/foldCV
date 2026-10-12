"""Private nonsecret application preferences beside shared Rules."""

import json
import re
from pathlib import Path

from pydantic import ValidationError

from .models.recovery import Preferences
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
            value = Preferences(schemaVersion=1, automaticAnalysis=True, theme='system', selectedModel=None)
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
            if value.selected_model is not None and not MODEL.fullmatch(value.selected_model):raise ValueError()
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

    def save_analysis(self, enabled):
        try:
            with locked_root(self.root, '.preferences.lock'):
                value = self._read()
                value.automatic_analysis = enabled
                self._write(value)
                return value
        except StorageFailure:
            raise PreferencesFailure('PREFERENCES_SAVE_FAILED') from None
