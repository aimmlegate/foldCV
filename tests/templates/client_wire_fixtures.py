"""Exact server replies the browser tests read, rebuilt in the D104 project format.

A project names its import records by history file and its captured package carries no asset bytes, so every
retained reply, patch and hash changes. Each reply is rebuilt with the server's own serialization; the results the
browser derives are rebuilt the way it derives them, after the same method reproduced the retained values.

Usage, from the repository root, then address_map_fixtures.py --write for the preparation reply:
PYTHONPATH="services/api/src:$PWD" .venv/bin/python tests/templates/client_wire_fixtures.py --write
"""

import base64
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'services/api/src')]

from packages.resume_core.canonical_patch import apply_patch, build_patch  # noqa: E402
from packages.resume_core.models.template_delta import TemplatePreparedEditDeltaV1  # noqa: E402
from packages.resume_core.models.template_workspace import WorkspaceV7  # noqa: E402
from packages.resume_core.models.template_writer import WriterViewV2  # noqa: E402
from packages.resume_core.template_api import TemplateProjectResponseV1  # noqa: E402
from packages.resume_core.templates.compiler import canonical, sha256  # noqa: E402

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


def digest(value):
    return sha256(canonical(value))


def marked(fixture):
    """The retained text with its asset markers replaced by the file bytes they stand for."""
    def expand(text):
        for asset in fixture.get('assets', []):
            text = text.replace(asset['marker'], base64.b64encode((ROOT / asset['path']).read_bytes()).decode())
        return text
    return expand


def slim_workspace(value):
    return json.loads(canonical(WorkspaceV7.model_validate(value)))


def slim_response(text):
    return wire(TemplateProjectResponseV1.model_validate_json(text))


def replaced(value, old, new):
    if isinstance(value, dict):
        return {key: replaced(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [replaced(item, old, new) for item in value]
    return new if value == old else value


def slim_writer(text):
    data = json.loads(text)
    response = TemplateProjectResponseV1.model_validate(data['response'])
    workspace = wire(response.workspace)
    data = replaced(data, data['workspaceSha256'], sha256(workspace.encode()))
    data['response'], data['workspaceWire'] = json.loads(wire(response)), workspace
    return wire(WriterViewV2.model_validate(data))


def rebuilt_preview(base, delta, workspace):
    """The browser's pending response after a prepared delta (template-delta.ts)."""
    if delta.mutation_wire is None:
        return base
    patch = delta.presentation_patch
    blocks = {key: value for key, value in base['presentation']['blocks'].items() if key not in patch.remove}
    blocks.update({key: value.model_dump(mode='json', by_alias=True) for key, value in patch.set.items()})
    snapshot = delta.result_snapshot.model_dump(mode='json', by_alias=True)
    presentation = {'schemaVersion': 1, 'snapshot': snapshot, 'recipe': base['presentation']['recipe'], 'blocks': blocks}
    if base['presentation'].get('editor') is not None and patch.editor is not None:
        presentation['editor'] = apply_patch(copy.deepcopy(base['presentation']['editor']), patch.editor.steps)
    return {'schemaVersion': 1, 'workspace': workspace, 'snapshot': snapshot, 'presentation': presentation,
        'durability': 'pending', 'saveError': None, 'savedProjectRevision': base['savedProjectRevision'],
        'savedDocumentRevision': base['savedDocumentRevision'],
        'identity': delta.result_identity.model_dump(mode='json', by_alias=True) if delta.result_identity else None,
        'generation': delta.result_generation.model_dump(mode='json', by_alias=True) if delta.result_generation else None}


def rebuilt_commit(preview, ack, workspace):
    """The browser's durable response after a committed save (template-save.ts)."""
    snapshot = ack['committedSnapshot']
    return {'schemaVersion': 1, 'workspace': workspace, 'snapshot': snapshot, 'presentation': preview['presentation'],
        'durability': 'durable', 'saveError': None, 'savedProjectRevision': snapshot['projectRevision'],
        'savedDocumentRevision': snapshot['documentRevision'], 'identity': ack['committedIdentity'],
        'generation': ack['committedGeneration']}


def slim_delta(old_base, new_base, text):
    """The same edit against the slim base: its result workspace, patch and hashes in the new format."""
    delta = TemplatePreparedEditDeltaV1.model_validate_json(text)
    old_result = apply_patch(copy.deepcopy(old_base['workspace']), delta.workspace_patch)
    new_result = slim_workspace(old_result)
    updated = delta.model_copy(update={'workspace_patch': build_patch(new_base['workspace'], new_result),
        'base_workspace_sha256': digest(new_base['workspace']), 'result_workspace_sha256': digest(new_result)})
    return delta, updated, old_result, new_result


def prepared_delta_fixture(fixture):
    old_base = json.loads(fixture['baseWire'])
    base_text = slim_response(fixture['baseWire'])
    new_base = json.loads(base_text)
    for case in fixture['cases']:
        old, new, old_result, new_result = slim_delta(old_base, new_base, case['deltaWire'])
        if digest(rebuilt_preview(old_base, old, old_result)) != case['responseSha256']:
            raise ValueError('the rebuilt preview does not reproduce the retained response: ' + case['name'])
        case['deltaWire'] = wire(new)
        case['responseSha256'] = digest(rebuilt_preview(new_base, new, new_result))
        case['workspaceSha256'] = digest(new_result)
    fixture['baseWire'] = base_text
    return fixture


def committed_delta_fixture(fixture):
    old_base = json.loads(fixture['baseWire'])
    base_text = slim_response(fixture['baseWire'])
    new_base = json.loads(base_text)
    old, new, old_preview_workspace, new_preview_workspace = slim_delta(old_base, new_base, fixture['deltaWire'])
    old_preview = rebuilt_preview(old_base, old, old_preview_workspace)
    new_preview = rebuilt_preview(new_base, new, new_preview_workspace)
    old_prepared, new_prepared = digest(old_preview_workspace), digest(new_preview_workspace)
    for case in fixture['cases']:
        ack = json.loads(case['ackWire'])
        if ack.get('kind') == 'committed':
            old_committed = apply_patch(copy.deepcopy(old_preview_workspace), ack['commitPatch'])
            if case['responseSha256'] != digest(rebuilt_commit(old_preview, ack, old_committed)):
                raise ValueError('the rebuilt commit does not reproduce the retained response: ' + case['name'])
            committed = {**new_preview_workspace, 'updatedAt': old_committed['updatedAt']}
            old_sha, new_sha = ack['committedWorkspaceSha256'], digest(committed)
            ack['commitPatch'] = [step.model_dump(mode='json', by_alias=True) if hasattr(step, 'model_dump') else step
                for step in build_patch(new_preview_workspace, committed)]
            ack = replaced(ack, old_sha, new_sha)
            ack = replaced(ack, old_prepared, new_prepared)
            case['responseSha256'] = digest(rebuilt_commit(new_preview, ack, committed))
        else:
            ack = replaced(ack, old_prepared, new_prepared)
        case['ackWire'] = wire(ack)
    fixture['baseWire'], fixture['deltaWire'] = base_text, wire(new)
    return fixture


def transport_fixture(fixture):
    """The writer transport case: its base, save request, advance and save replies; address_map_fixtures.py
    rebuilds the preparation reply from the converted base afterwards."""
    old_base = json.loads(fixture['baseWire'])
    base_text = slim_response(fixture['baseWire'])
    new_base = json.loads(base_text)
    reply = json.loads(fixture['replyWire'])
    old, new, old_preview_workspace, new_preview_workspace = slim_delta(old_base, new_base, wire(reply['delta']))
    swaps = [(digest(old_base['workspace']), digest(new_base['workspace'])),
        (digest(old_preview_workspace), digest(new_preview_workspace))]
    for case in fixture['cases']:
        ack = json.loads(case['replyWire'])
        if ack.get('kind') == 'committed':
            old_committed = apply_patch(copy.deepcopy(old_preview_workspace), ack['commitPatch'])
            committed = {**new_preview_workspace, 'updatedAt': old_committed['updatedAt']}
            ack['commitPatch'] = [step.model_dump(mode='json', by_alias=True) if hasattr(step, 'model_dump') else step
                for step in build_patch(new_preview_workspace, committed)]
            ack = replaced(ack, ack['committedWorkspaceSha256'], digest(committed))
        for before, after in swaps:
            ack = replaced(ack, before, after)
        case['replyWire'] = wire(ack)
    for key in ('saveRequestWire', 'advanceWire'):
        value = json.loads(fixture[key])
        for before, after in swaps:
            value = replaced(value, before, after)
        fixture[key] = wire(value)
    fixture['baseWire'] = base_text
    return fixture


def client_responses_fixture(fixture, names):
    expand = marked(fixture)
    for name in names:
        text = expand(fixture[name])
        fixture[name] = slim_writer(text) if name == 'writer' else slim_response(text)
    # Asset bytes left the replies; markers no longer stand for anything.
    fixture['assets'] = [asset for asset in fixture['assets'] if any(asset['marker'] in fixture[name] for name in names)]
    return fixture


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def main():
    if sys.argv[1:] != ['--write']:
        raise SystemExit('usage: client_wire_fixtures.py --write')
    preload_assets()
    for name, convert in [('client-responses.json', lambda value: client_responses_fixture(value, ['authored', 'writer', 'predraft'])),
            ('client-compiler3.json', lambda value: client_responses_fixture(value, ['compiler1', 'compiler2', 'compiler3'])),
            ('prepared-delta.json', prepared_delta_fixture), ('committed-delta.json', committed_delta_fixture),
            ('preparation-transport.json', transport_fixture)]:
        path = FIXTURES / name
        path.write_text(encoded(convert(json.loads(path.read_text(encoding='utf-8')))), encoding='utf-8')
        print('rebuilt', name)


if __name__ == '__main__':
    main()
