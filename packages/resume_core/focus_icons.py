"""Focus icons the user chose (D122): a technology name to a template icon, kept beside the projects. Rows added later,
by an import or from the facts panel, take the remembered icon when their template has it."""

import json
import re

from .storage import StorageFailure, atomic_write, locked_root, private_file
from .technologies import normalize_name

MAX_BYTES = 256 * 1024
MAX_NAMES = 2000
MAX_NAME = 200
ICON = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')


def valid(name, icon):
    return isinstance(name, str) and isinstance(icon, str) and 0 < len(name) <= MAX_NAME \
        and normalize_name(name) == name and ICON.fullmatch(icon) is not None


class FocusIconStore:
    def __init__(self, root):
        self.root, self.path = root, root / 'focus-icons.json'

    def _read(self):
        """Normalized names to icons, the latest choice last. A missing or unreadable file remembers nothing: these are
        conveniences, never a reason to refuse an edit or an import."""
        if not self.path.exists() and not self.path.is_symlink():
            return {}
        try:
            private_file(self.path)
            raw = self.path.read_bytes()
            if len(raw) > MAX_BYTES:
                return {}
            value = json.loads(raw)
        except (OSError, StorageFailure, ValueError):
            return {}
        names = value.get('names') if isinstance(value, dict) and value.get('schemaVersion') == 1 else None
        if not isinstance(names, dict):
            return {}
        return {name: icon for name, icon in names.items() if valid(name, icon)}

    def load(self):
        try:
            with locked_root(self.root, '.focus-icons.lock'):
                return self._read()
        except StorageFailure:
            return {}

    def update(self, changes):
        """Each (name, icon) remembers the icon for the name, or forgets the name for None. Past the limit the oldest
        choices go. Raises StorageFailure when the file cannot be written."""
        with locked_root(self.root, '.focus-icons.lock'):
            names = self._read()
            before = dict(names)
            for name, icon in changes:
                key = normalize_name(name)
                if not key or len(key) > MAX_NAME:
                    continue
                names.pop(key, None)
                if icon is not None and ICON.fullmatch(icon):
                    names[key] = icon
            while len(names) > MAX_NAMES:
                names.pop(next(iter(names)))
            if list(names.items()) == list(before.items()):
                return names
            while True:
                content = (json.dumps({'schemaVersion': 1, 'names': names}, ensure_ascii=False, indent=1) + '\n').encode()
                if len(content) <= MAX_BYTES:
                    break
                names.pop(next(iter(names)))
            atomic_write(self.path, content)
            return names
