"""Settings: read, check and activate the template YAML that new imports use.

Existing projects keep the package they captured (R10); a saved change affects only new imports.
"""

import base64

from pydantic import Field

from packages.resume_core.models.contracts import Wire
from packages.resume_core.templates.compiler import compile_bytes, compile_template
from packages.resume_core.templates.loading import CONFIG_BYTES
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import BUNDLED_TEMPLATE, TemplateStore

REVISION_TAKEN = "эта версия уже сохранена с другим содержимым; измените template.revision"


class TemplateConfigRequest(Wire):
    text: str = Field(max_length=CONFIG_BYTES)


def summary(package):
    return {'id': package.id, 'name': package.definition.template.name, 'revision': package.revision,
        'packageHash': package.package_hash}


class TemplateConfig:
    def __init__(self, root):
        self.store = TemplateStore(root)

    def read(self):
        package, bundled = self.store.active(), compile_template(BUNDLED_TEMPLATE)
        # The same package may have been captured from an older, longer text; show the bundled file's current form.
        same = package.package_hash == bundled.package_hash
        source = bundled if same else package
        return {'schemaVersion': 1, 'package': summary(package), 'format': source.original_format,
            'text': base64.b64decode(source.original_base64).decode('utf-8'), 'bundled': same}

    def compile(self, text):
        """Return (package, None) or (None, error). Assets keep the active package's bytes; new paths read the bundled folder."""
        active, bundled = self.store.active(), compile_template(BUNDLED_TEMPLATE)
        captured = {asset.path: base64.b64decode(asset.bytes_base64) for asset in active.assets}
        try:
            package = compile_bytes(text.encode('utf-8'), BUNDLED_TEMPLATE.parent, original_format='yaml', assets=captured)
        except SchemaFailure as error:
            return None, {'path': error.path, 'message': error.reason}
        except (ValueError, UnicodeError) as error:
            return None, {'path': '/', 'message': str(error).splitlines()[0] if str(error) else type(error).__name__}
        # The bundled revision counts as taken even before the store records it, so Reset can always restore it.
        bundled_taken = (package.id, package.revision) == (bundled.id, bundled.revision) and package.package_hash != bundled.package_hash
        if bundled_taken or self.store.revision_taken(package):
            return None, {'path': '/template/revision', 'message': REVISION_TAKEN}
        return package, None

    def check(self, text):
        package, error = self.compile(text)
        if error is not None:
            return {'schemaVersion': 1, 'valid': False, 'package': None, 'error': error}
        return {'schemaVersion': 1, 'valid': True, 'package': summary(package), 'error': None}

    def save(self, text):
        package, error = self.compile(text)
        if error is not None:
            return None, {'schemaVersion': 1, 'valid': False, 'package': None, 'error': error}
        self.store.activate(package)
        return self.read(), None

    def reset(self):
        self.store.activate(compile_template(BUNDLED_TEMPLATE))
        return self.read()
