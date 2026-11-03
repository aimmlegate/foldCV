"""Settings: read, check and save the YAML of each template, and choose the default template for new imports.

Existing projects keep the package they captured (R10); a saved change affects only new imports.
"""

import base64
import json
import re

from pydantic import Field
import yaml

from packages.resume_core.models.contracts import Wire
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.loading import CONFIG_BYTES
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import TemplateIdTaken, TemplateStore, bundled_folder

from .template_reasons import reason_text

REVISION_TAKEN = "эта версия уже сохранена с другим содержимым; измените template.revision"
ID_CHANGED = "template.id менять нельзя, укажите «{}»"
NO_HEADER = "нет раздела template с полями id, name и revision"
FIRST_REVISION = '1.0.0'
# Russian letters of a copy's name become ASCII in its id.
TRANSLIT = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя', ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k',
    'l', 'm', 'n', 'o', 'p', 'r', 's', 't', 'u', 'f', 'kh', 'ts', 'ch', 'sh', 'shch', '', 'y', '', 'e', 'yu', 'ya']))
HEADER_KEY = re.compile(r'^(\s+)(id|name|revision)\s*:')


class TemplateConfigRequest(Wire):
    text: str = Field(max_length=CONFIG_BYTES)


class TemplateDefaultRequest(Wire):
    template_id: str = Field(min_length=1, max_length=200)


class TemplateCopyRequest(Wire):
    copy_of: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)


class TemplateDraftRequest(Wire):
    text: str = Field(max_length=CONFIG_BYTES)
    assets_from: str | None = Field(min_length=1, max_length=200)


def slug(name):
    letters = ''.join(TRANSLIT.get(char, char) for char in name.lower())
    return re.sub(r'[^a-z0-9]+', '-', letters).strip('-')[:60].strip('-')


def new_id(name, taken):
    """`custom-<slug>`, `custom-<n>` for a name without letters or digits, with -2, -3... while taken."""
    base = slug(name)
    if not base:
        return next(f'custom-{number}' for number in range(1, len(taken) + 2) if f'custom-{number}' not in taken)
    found, number = 'custom-' + base, 2
    while found in taken:
        found, number = f'custom-{base}-{number}', number + 1
    return found


def with_header(text, template_id, name, revision):
    """The text with new id, name and revision lines in its top `template:` mapping; comments and the short form stay.
    None when the text has no such block mapping."""
    lines = text.splitlines(keepends=True)
    top = next((index for index, line in enumerate(lines) if re.match(r'template\s*:\s*(#.*)?$', line.rstrip('\r\n'))), None)
    if top is None:
        return None
    values = {'id': template_id, 'name': json.dumps(name, ensure_ascii=False), 'revision': revision}
    indent, seen = None, set()
    for index in range(top + 1, len(lines)):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if not line[0].isspace():
            break
        current = len(line) - len(line.lstrip())
        indent = current if indent is None else indent
        match = HEADER_KEY.match(line)
        if current == indent and match and match.group(2) not in seen:
            key = match.group(2)
            seen.add(key)
            ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
            lines[index] = f'{match.group(1)}{key}: {values[key]}{ending}'
    if indent is None:
        return None
    ending = '\r\n' if lines[top].endswith('\r\n') else '\n'
    missing = [f'{" " * indent}{key}: {values[key]}{ending}' for key in ('id', 'revision', 'name') if key not in seen]
    if not lines[top].endswith(('\n', '\r\n')):
        lines[top] += ending
    return ''.join([*lines[:top + 1], *missing, *lines[top + 1:]])


def stated_name(text):
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    header = loaded.get('template') if isinstance(loaded, dict) else None
    name = header.get('name') if isinstance(header, dict) else None
    return name.strip() if isinstance(name, str) and name.strip() else None


def summary(package):
    return {'id': package.id, 'name': package.definition.template.name, 'revision': package.revision,
        'packageHash': package.package_hash}


def original(package):
    return package.original_format, base64.b64decode(package.original_base64)


class TemplateConfig:
    def __init__(self, root):
        self.store = TemplateStore(root)

    def catalog(self):
        default_id, templates = self.store.templates()
        return {'defaultId': default_id, 'templates': [{**summary(package), **self.flags(package, bundled)[1]}
            for package, bundled in templates]}

    def flags(self, package, bundled):
        """(format and bytes of the text saved last, flags). `bundled`: the app ships this id; `edited`: the current
        version is not the shipped one, in its definition or its text."""
        shipped = bundled is not None and package.package_hash == bundled.package_hash
        # The same package may have been captured from an older, longer text; show the bundled file's current form.
        source = self.store.saved_original(package) or original(bundled if shipped else package)
        return source, {'bundled': bundled is not None, 'edited': not shipped or source != original(bundled)}

    def read(self, template_id):
        package, bundled = self.store.versions(template_id)
        (text_format, text), state = self.flags(package, bundled)
        return {'schemaVersion': 1, 'package': summary(package), 'format': text_format, 'text': text.decode('utf-8'), **state}

    def compile(self, template_id, text):
        """Return (package, None) or (None, error). Assets keep the current package's bytes; new paths read the bundled
        folder."""
        current, bundled = self.store.versions(template_id)
        captured = {asset.path: base64.b64decode(asset.bytes_base64) for asset in current.assets}
        try:
            package = compile_bytes(text.encode('utf-8'), bundled_folder(template_id), original_format='yaml', assets=captured)
        except SchemaFailure as error:
            return None, {'path': error.path, 'message': reason_text(error.reason)}
        except (ValueError, UnicodeError) as error:
            first = str(error).splitlines()[0] if str(error) else ''
            return None, {'path': '/', 'message': reason_text(first)}
        if package.id != template_id:
            return None, {'path': '/template/id', 'message': ID_CHANGED.format(template_id)}
        # The bundled revision names the bundled bytes even before the store records them.
        bundled_taken = bundled is not None and package.revision == bundled.revision and package.package_hash != bundled.package_hash
        if bundled_taken or self.store.revision_taken(package):
            return None, {'path': '/template/revision', 'message': REVISION_TAKEN}
        return package, None

    def compile_new(self, text, assets):
        """Compile the text of a template the store does not have yet: (package, None) or (None, error). `assets` maps a
        path to captured bytes; other paths read the first shipped folder. No id or revision check."""
        try:
            return compile_bytes(text.encode('utf-8'), bundled_folder(''), original_format='yaml', assets=assets), None
        except SchemaFailure as error:
            return None, {'path': error.path, 'message': reason_text(error.reason)}
        except (ValueError, UnicodeError) as error:
            first = str(error).splitlines()[0] if str(error) else ''
            return None, {'path': '/', 'message': reason_text(first)}

    def captured(self, template_id):
        """Asset bytes of the current package of `template_id`; no template, no assets."""
        if template_id is None:
            return {}
        return {asset.path: base64.b64decode(asset.bytes_base64) for asset in self.store.current(template_id).assets}

    def _create(self, text, name, assets):
        """Store `text` under a fresh id derived from `name`: (config state, None) or (None, check reply)."""
        for _attempt in range(3):
            template_id = new_id(name, self.store.taken_ids())
            headed = with_header(text, template_id, name, FIRST_REVISION)
            if headed is None:
                return None, {'schemaVersion': 1, 'valid': False, 'package': None,
                    'error': {'path': '/template', 'message': NO_HEADER}}
            package, error = self.compile_new(headed, assets)
            if error is not None:
                return None, {'schemaVersion': 1, 'valid': False, 'package': None, 'error': error}
            try:
                self.store.create(package, keep_text=True)
            except TemplateIdTaken:
                continue
            return self.read(template_id), None
        raise TemplateIdTaken(name)

    def copy(self, copy_of, name):
        """A new template from the current text and assets of `copy_of`, named `name`, at revision 1.0.0."""
        source = self.read(copy_of)['text']
        return self._create(source, name.strip() or name, self.captured(copy_of))

    def create(self, text, assets_from):
        """Save an unsaved new template text; its id comes from its own name."""
        assets = self.captured(assets_from)
        name = stated_name(text)
        if name is None:
            _package, error = self.compile_new(text, assets)
            return None, {'schemaVersion': 1, 'valid': False, 'package': None,
                'error': error or {'path': '/template/name', 'message': NO_HEADER}}
        return self._create(text, name, assets)

    def delete(self, template_id):
        self.store.delete(template_id)
        return {'schemaVersion': 1, **self.catalog()}

    def check(self, template_id, text):
        package, error = self.compile(template_id, text)
        if error is not None:
            return {'schemaVersion': 1, 'valid': False, 'package': None, 'error': error}
        return {'schemaVersion': 1, 'valid': True, 'package': summary(package), 'error': None}

    def save(self, template_id, text):
        """Save a new current version of the template; the default template stays as it is."""
        package, error = self.compile(template_id, text)
        if error is not None:
            return None, {'schemaVersion': 1, 'valid': False, 'package': None, 'error': error}
        self.store.save(package, keep_text=True)
        return self.read(template_id), None

    def reset(self, template_id):
        self.store.reset(template_id)
        return self.read(template_id)

    def set_default(self, template_id):
        self.store.set_default(template_id)
        return {'schemaVersion': 1, **self.catalog()}
