"""Settings: read, check and save the YAML of each template, and choose the default template for new imports.

Existing projects keep the package they captured (R10); a saved change affects only new imports.
"""

import base64

from pydantic import Field

from packages.resume_core.models.contracts import Wire
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.loading import CONFIG_BYTES
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import TemplateStore, bundled_folder

from .template_reasons import reason_text

REVISION_TAKEN = "эта версия уже сохранена с другим содержимым; измените template.revision"
ID_CHANGED = "template.id менять нельзя, укажите «{}»"


class TemplateConfigRequest(Wire):
    text: str = Field(max_length=CONFIG_BYTES)


class TemplateDefaultRequest(Wire):
    template_id: str = Field(min_length=1, max_length=200)


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
        self.store.save(package)
        return self.read(template_id), None

    def reset(self, template_id):
        self.store.reset(template_id)
        return self.read(template_id)

    def set_default(self, template_id):
        self.store.set_default(template_id)
        return {'schemaVersion': 1, **self.catalog()}
