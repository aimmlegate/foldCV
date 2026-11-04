"""Settings: read, check and save the YAML of each template, and choose the default template for new imports.

Existing projects keep the package they captured (R10); a saved change affects only new imports.
"""

import base64
import json
import re

from pydantic import Field
import yaml
from yaml.nodes import MappingNode, ScalarNode

from packages.resume_core.models.contracts import Wire
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.loading import CONFIG_BYTES, load_definition
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import TemplateStore, bundled_folder

from .template_reasons import reason_text

REVISION_TAKEN = "эта версия уже сохранена с другим содержимым; измените template.revision"
ID_CHANGED = "template.id менять нельзя, укажите «{}»"
NO_HEADER = "нет раздела template с полями id, name и revision"
FIRST_REVISION = '1.0.0'
# Russian letters of a copy's name become ASCII in its id.
TRANSLIT = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя', ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k',
    'l', 'm', 'n', 'o', 'p', 'r', 's', 't', 'u', 'f', 'kh', 'ts', 'ch', 'sh', 'shch', '', 'y', '', 'e', 'yu', 'ya']))
NUMBERED_REVISION = re.compile(r'(\d+)\.(\d+)\.(\d+)')
HEADER_KEYS = ('id', 'revision', 'name')


class TemplateConfigRequest(Wire):
    text: str = Field(max_length=CONFIG_BYTES)


class TemplateSaveRequest(Wire):
    text: str = Field(max_length=CONFIG_BYTES)
    # The free revision Save offered after the typed one was refused as taken; it replaces the text's revision line.
    revision: str | None = Field(default=None, min_length=1, max_length=200)


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


def next_revision(revisions):
    """The patch after the highest X.Y.Z of `revisions`, so it names no version yet; 1.0.0 when none has that form."""
    numbers = [tuple(int(part) for part in match.groups()) for value in revisions if (match := NUMBERED_REVISION.fullmatch(value))]
    major, minor, patch = max(numbers, default=(1, 0, -1))
    return f'{major}.{minor}.{patch + 1}'


def _scalar(key, value, flow):
    # Ids and revisions are plain ASCII; a name is quoted. Inside braces every value is quoted, so JSON stays JSON.
    return json.dumps(value, ensure_ascii=False) if flow or key == 'name' else value


def with_header(text, **values):
    """The text with the given `id`, `name` and `revision` set in its top `template:` mapping. Values are replaced
    in place, whatever their scalar style, and missing keys are added first; comments and the short form stay.
    None when the text has no `template` mapping. Invalid YAML comes back unchanged: the compiler names the error."""
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError):
        return text
    pairs = root.value if isinstance(root, MappingNode) else []
    header = next((value for key, value in pairs if isinstance(key, ScalarNode) and key.value == 'template'), None)
    if not isinstance(header, MappingNode):
        return None
    flow, present, edits = header.flow_style, set(), []
    for key, value in header.value:
        if isinstance(key, ScalarNode) and key.value in values and key.value not in present:
            present.add(key.value)
            start, end = value.start_mark.index, value.end_mark.index
            # A block scalar's span ends past its line breaks; they stay in the text.
            while end > start and text[end - 1] in '\r\n':
                end -= 1
            replacement = _scalar(key.value, values[key.value], flow)
            if start == end and text[start - 1:start] not in (' ', '\t'):
                replacement = ' ' + replacement
            edits.append((start, end, replacement))
    missing = [key for key in HEADER_KEYS if key in values and key not in present]
    if missing and flow:
        added = ', '.join(f'{json.dumps(key)}: {_scalar(key, values[key], True)}' for key in missing)
        edits.append((header.start_mark.index + 1, header.start_mark.index + 1, added + (', ' if header.value else '')))
    elif missing:
        first = header.value[0][0].start_mark.index
        line = text.rfind('\n', 0, first) + 1
        ending = '\r\n' if '\r\n' in text else '\n'
        edits.append((line, line, ''.join(f'{text[line:first]}{key}: {_scalar(key, values[key], False)}{ending}' for key in missing)))
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def stated_name(text):
    """`template.name` of a text as the compiler reads it; None when it is missing or blank, or the text does not load."""
    try:
        loaded = load_definition(text.encode('utf-8'))
    except SchemaFailure:
        return None
    header = loaded.get('template')
    name = header.get('name') if isinstance(header, dict) else None
    return name.strip() if isinstance(name, str) and name.strip() else None


def summary(package):
    return {'id': package.id, 'name': package.definition.template.name, 'revision': package.revision,
        'packageHash': package.package_hash}


def original(package):
    return package.original_format, base64.b64decode(package.original_base64)


def decoded_assets(package):
    return {asset.path: base64.b64decode(asset.bytes_base64) for asset in package.assets}


def refused(error):
    """The check reply of a text that does not compile; a refused save or create answers 422 with it."""
    return {'schemaVersion': 1, 'valid': False, 'package': None, 'error': error}


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

    def compile_new(self, text, assets, folder=None):
        """Compile a text with no id or revision check: (package, None) or (None, error). `assets` maps a path to
        captured bytes; other paths read `folder`, by default the first shipped one (a template the store lacks)."""
        try:
            package = compile_bytes(text.encode('utf-8'), folder or bundled_folder(''), original_format='yaml', assets=assets)
        except SchemaFailure as error:
            return None, {'path': error.path, 'message': reason_text(error.reason)}
        except (ValueError, UnicodeError) as error:
            first = str(error).splitlines()[0] if str(error) else ''
            return None, {'path': '/', 'message': reason_text(first)}
        return package, None

    def compile(self, template_id, text):
        """An edit of a saved template as Save checks it: (package, None) or (None, error)."""
        return self.compile_saved(text, *self.store.versions(template_id))

    def compile_saved(self, text, current, bundled, assets=None):
        """Compile an edit of `current` (`bundled`: its shipped package or None): the id must stay and the revision
        must be free. Assets keep the current package's bytes unless given; new paths read the bundled folder."""
        package, error = self.compile_new(text, decoded_assets(current) if assets is None else assets, bundled_folder(current.id))
        if error is not None:
            return None, error
        if package.id != current.id:
            return None, {'path': '/template/id', 'message': ID_CHANGED.format(current.id)}
        # The bundled revision names the bundled bytes even before the store records them.
        bundled_taken = bundled is not None and package.revision == bundled.revision and package.package_hash != bundled.package_hash
        if bundled_taken or self.store.revision_taken(package):
            known = {package.revision, current.revision, *self.store.revisions(current.id)}
            if bundled is not None:
                known.add(bundled.revision)
            return None, {'path': '/template/revision', 'message': REVISION_TAKEN, 'nextRevision': next_revision(known)}
        return package, None

    def captured(self, template_id):
        """Asset bytes of the current package of `template_id`; no template, no assets."""
        return {} if template_id is None else decoded_assets(self.store.current(template_id))

    def _create(self, text, name, assets):
        """Store `text` under a fresh id derived from `name`: (config state, None) or (None, check reply)."""
        error = {}

        def build(taken):
            headed = with_header(text, id=new_id(name, taken), name=name, revision=FIRST_REVISION)
            if headed is None:
                error['value'] = {'path': '/template', 'message': NO_HEADER}
                return None
            package, error['value'] = self.compile_new(headed, assets)
            return package
        package = self.store.create(build)
        if package is None:
            return None, refused(error['value'])
        return self.read(package.id), None

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
            return None, refused(error or {'path': '/template/name', 'message': NO_HEADER})
        return self._create(text, name, assets)

    def delete(self, template_id):
        self.store.delete(template_id)
        return {'schemaVersion': 1, **self.catalog()}

    def check(self, template_id, text):
        package, error = self.compile(template_id, text)
        if error is not None:
            return refused(error)
        return {'schemaVersion': 1, 'valid': True, 'package': summary(package), 'error': None}

    def save(self, template_id, text, revision=None):
        """Save a new current version of the template; the default template stays as it is. `revision` first replaces
        the text's revision line: the free one offered after the typed revision was refused as taken."""
        if revision is not None:
            text = with_header(text, revision=revision)
            if text is None:
                return None, refused({'path': '/template', 'message': NO_HEADER})
        package, error = self.compile(template_id, text)
        if error is not None:
            return None, refused(error)
        self.store.save(package, keep_text=True)
        return self.read(template_id), None

    def reset(self, template_id):
        self.store.reset(template_id)
        return self.read(template_id)

    def set_default(self, template_id):
        self.store.set_default(template_id)
        return {'schemaVersion': 1, **self.catalog()}
