"""Loading the golden corpus: stored fixtures and same-project clipboard placeholders."""

import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def corpus():
    return json.loads((HERE / 'synthetic/corpus.json').read_text())


def results():
    return json.loads((HERE / 'results.json').read_text())


def loaded(entry):
    """A stored fixture; its package assets come from the bundled template, so a changed template fails to load."""
    from packages.resume_core.models.template_workspace import WorkspaceV7
    from packages.resume_core.templates.models import remember_asset
    from tests.templates.storage_fixtures import package
    for asset in package().assets:
        remember_asset(asset.sha256, asset.bytes_base64, asset.mime_type)
    return WorkspaceV7.model_validate(entry['workspace']), {key: base64.b64decode(raw) for key, raw in entry['sources'].items()}


def with_capture(value, capture_id):
    return json.loads(json.dumps(value).replace('{clipboard}', capture_id))
