"""Own Focus icons (D187): a library beside the projects, in the app's data root, that every résumé on this computer sees.
A résumé that uses one keeps its own copy (`ProjectV6.own_icons`), so a deleted or damaged library never stops a résumé
from opening, showing or exporting it."""

import base64
import hashlib
import json
import re

from ..image_check import check_image
from ..models.template_mutations import OwnIcon
from ..storage import StorageFailure, atomic_write, locked_root, private_directory, private_file

MAX_ICONS = 500
INDEX_BYTES = 512 * 1024
ID = re.compile(r'own-[0-9a-f]{24}\Z')


class OwnIconStore:
    def __init__(self, root):
        self.root, self.folder = root, root / 'own-icons'
        self.index = self.folder / 'index.json'

    def _read(self):
        """The library's entries {id, name, sha256}; a missing or damaged index lists none."""
        try:
            if not self.index.exists():
                return []
            private_file(self.index)
            raw = self.index.read_bytes()
            value = json.loads(raw) if len(raw) <= INDEX_BYTES else None
        except (OSError, ValueError, StorageFailure, RecursionError):
            return []
        icons = value.get('icons') if isinstance(value, dict) and value.get('schemaVersion') == 1 else None
        if not isinstance(icons, list):
            return []
        return [icon for icon in icons if isinstance(icon, dict) and isinstance(icon.get('id'), str) and ID.fullmatch(icon['id'])
                and isinstance(icon.get('name'), str) and 0 < len(icon['name']) <= 200
                and isinstance(icon.get('sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', icon['sha256'])]

    def _write(self, icons):
        private_directory(self.folder)
        atomic_write(self.index, json.dumps({'schemaVersion': 1, 'icons': icons}, ensure_ascii=False).encode())

    def list(self):
        try:
            with locked_root(self.root, '.own-icons.lock'):
                return self._read()
        except (OSError, StorageFailure):
            return []

    def get(self, identifier):
        """The icon with its PNG, as a résumé keeps its copy; None when the library lacks it or its file is damaged."""
        entry = next((icon for icon in self.list() if icon['id'] == identifier), None)
        if entry is None:
            return None
        try:
            data = (self.folder / (entry['sha256'] + '.png')).read_bytes()
        except OSError:
            return None
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            return None
        return OwnIcon.model_validate({'id': entry['id'], 'name': entry['name'], 'sha256': entry['sha256'],
                                       'bytesBase64': base64.b64encode(data).decode()})

    def add(self, name, data):
        """A new library icon: a checked 256 px PNG and a name; two icons may share a name. ValueError with a public code."""
        name = ' '.join(name.split())
        if not name or len(name) > 200:
            raise ValueError('ICON_NAME_INVALID')
        checked = check_image(data, 'icon')
        digest = hashlib.sha256(checked.data).hexdigest()
        with locked_root(self.root, '.own-icons.lock'):
            icons = self._read()
            if len(icons) >= MAX_ICONS:
                raise ValueError('ICON_LIBRARY_FULL')
            identifier = 'own-' + hashlib.sha256((digest + name).encode()).hexdigest()[:24]
            if not any(icon['id'] == identifier for icon in icons):
                private_directory(self.folder)
                atomic_write(self.folder / (digest + '.png'), checked.data)
                icons.append({'id': identifier, 'name': name, 'sha256': digest})
                self._write(icons)
        return {'id': identifier, 'name': name, 'sha256': digest}

    def delete(self, identifier):
        with locked_root(self.root, '.own-icons.lock'):
            icons = self._read()
            kept = [icon for icon in icons if icon['id'] != identifier]
            if len(kept) == len(icons):
                return False
            self._write(kept)
            removed = next(icon for icon in icons if icon['id'] == identifier)
            if not any(icon['sha256'] == removed['sha256'] for icon in kept):
                (self.folder / (removed['sha256'] + '.png')).unlink(missing_ok=True)
        return True
