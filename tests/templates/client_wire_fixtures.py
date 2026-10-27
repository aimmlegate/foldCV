"""Exact project responses for client tests, rebuilt in the D104 project format.

A project names its import records by history file and its captured package carries no asset bytes, so every
retained response changes. Each response is rebuilt with the server's own serialization.

Usage, from the repository root:
PYTHONPATH="services/api/src:$PWD" .venv/bin/python tests/templates/client_wire_fixtures.py --write
"""

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'services/api/src')]

from packages.resume_core.template_api import TemplateProjectResponseV1  # noqa: E402
from packages.resume_core.templates.compiler import canonical  # noqa: E402

FIXTURES = ROOT / 'tests/fixtures/synthetic/templates'


def preload_assets():
    """Captured asset bytes by hash from the repository's template folders: converted replies no longer carry them."""
    import hashlib
    from packages.resume_core.templates.models import remember_asset
    for path in [*ROOT.glob('templates/*/assets/*'), *ROOT.glob('tests/fixtures/synthetic/templates/**/assets/*')]:
        if path.is_file():
            raw = path.read_bytes()
            remember_asset(hashlib.sha256(raw).hexdigest(), base64.b64encode(raw).decode())


def wire(value):
    return canonical(value).decode()


def marked(fixture):
    """The retained text with its asset markers replaced by the file bytes they stand for."""
    def expand(text):
        for asset in fixture.get('assets', []):
            text = text.replace(asset['marker'], base64.b64encode((ROOT / asset['path']).read_bytes()).decode())
        return text
    return expand


def slim_response(text):
    return wire(TemplateProjectResponseV1.model_validate_json(text))


def client_responses_fixture(fixture, names):
    expand = marked(fixture)
    for name in names:
        text = expand(fixture[name])
        fixture[name] = slim_response(text)
    # Asset bytes left the replies; markers no longer stand for anything.
    fixture['assets'] = [asset for asset in fixture['assets'] if any(asset['marker'] in fixture[name] for name in names)]
    return fixture


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def main():
    if sys.argv[1:] != ['--write']:
        raise SystemExit('usage: client_wire_fixtures.py --write')
    preload_assets()
    for name, convert in [('client-responses.json', lambda value: client_responses_fixture(value, ['authored', 'predraft'])),
            ('client-compiler3.json', lambda value: client_responses_fixture(value, ['compiler1', 'compiler2', 'compiler3']))]:
        path = FIXTURES / name
        path.write_text(encoded(convert(json.loads(path.read_text(encoding='utf-8')))), encoding='utf-8')
        print('rebuilt', name)


if __name__ == '__main__':
    main()
