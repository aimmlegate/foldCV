"""Deterministic prepared address-map fixtures shared with browser verifier tests."""

import json
import sys
from pathlib import Path

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.models.template_writer import WriterPrepareEditV2, WriterPreparedDeltaV2
from packages.resume_core.template_address_map import address_map_sha256, build_address_map
from packages.resume_core.template_api import TemplateProjectResponseV1
from packages.resume_core.template_delta import prepared_delta
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.templates.presentation import snapshot_identity
from tests.templates.storage_fixtures import workspace
from tests.templates.test_template_preparation import proof, response

ROOT = Path(__file__).resolve().parents[2]
TRANSPORT = ROOT / 'tests/fixtures/synthetic/templates/preparation-transport.json'
ADDRESS = ROOT / 'tests/fixtures/synthetic/templates/address-maps.json'


def literal(text, ref):
    return {'type': 'text', 'text': text, 'styles': {}, 'presentation': ref}


def field(key, cell, binding, occurrence, text, ref, *, complete=True):
    return {'type': 'fact_field', 'bindingId': binding, 'bindingRootId': occurrence, 'occurrenceId': occurrence,
        'recordId': 'paper-a', 'fieldKey': key, 'cellId': cell, 'text': text, 'styles': {}, 'syncedFactRevision': 1,
        'complete': complete, 'presentation': ref}


def joined(content=None):
    before, _sources = workspace()
    data = before.model_dump(by_alias=True)
    block = data['project']['document']['regions'][2]['blocks'][0]
    ref = block['content'][0]['presentation']
    block['content'] = content(ref) if content else [literal('By ', ref),
        field('title', 'a-title', 'fragment-paper-a', 'occurrence-paper-a', 'Shared title', ref),
        literal(' / ', ref), field('journal', 'a-journal', 'binding-journal', 'occurrence-journal', 'Journal North', ref),
        literal('.', ref)]
    return WorkspaceV7.model_validate(data)


def tabled(cell_id='cell-a'):
    from packages.resume_core.models.template_document import TemplateTableBlock
    before = joined()
    old = before.project.document.regions[2].blocks[0]
    before.project.document.regions[2].blocks[0] = TemplateTableBlock(type='table', id=old.id, revision=old.revision,
        props={}, children=[], provenance=[], presentation=old.presentation, content={'rows': [{'id': 'row', 'cells': [
            {'id': cell_id, 'revision': 1, 'content': old.content}]}], 'columnWidths': [None], 'headerRows': 0, 'headerCols': 0})
    return WorkspaceV7.model_validate(before.model_dump(by_alias=True))


def block_of(value, identifier):
    return next(block for block in value.project.document.blocks() if block.id == identifier)


def operation_request(value, operation, identifier='address-edit'):
    return TemplateEditPreparationV1(schemaVersion=1, clientMutationId=identifier, snapshot=snapshot_identity(value),
        capture={'sessionId': 'session', 'actionId': 'action-' + identifier, 'actionToken': 1, 'dependencies': []},
        operations=[{'opId': 'op', **operation}])


def text_request(value, start, end, text='X', *, target=None, block='block-paper-a', kind='replace_text', styles=None,
        identifier='address-edit', cell=None):
    found = block_of(value, block)
    selected = {'blockId': found.id, 'beforeRevision': found.revision, 'cellId': cell, 'field': 'content',
        'start': start, 'end': end}
    if target is not None:
        selected['insertionTarget'] = target
    operation = {'kind': kind, 'range': selected, 'styles': styles or {}}
    if kind == 'replace_text':
        operation['text'] = text
    return operation_request(value, operation, identifier)


def trimmed(value):
    # The verifier reads only the snapshot and document; the captured package stays out of the fixture.
    raw = value.model_dump(mode='json', by_alias=True)
    return canonical({'snapshot': raw['snapshot'], 'workspace': {'project': {'document': raw['workspace']['project']['document']}}}).decode()


def cases():
    from tests.templates.test_scope_displays import copied_workspace
    field_target = {'kind': 'field', 'bindingId': 'fragment-paper-a'}
    scoped, _sources, _copied = copied_workspace()
    plans = [
        ('field-typing', joined, lambda value: text_request(value, 8, 8, target=field_target)),
        ('literal-edge', joined, lambda value: text_request(value, 15, 15, '!', target={'kind': 'literal'})),
        ('cross-field-scope', joined, lambda value: text_request(value, 10, 22, 'merged')),
        ('scope-repeat-detach', lambda: scoped, lambda value: text_request(value, 1, 4, '!')),
        ('empty-anchor', joined, lambda value: text_request(value, 3, 15, '')),
        ('split', joined, lambda value: operation_request(value, {'kind': 'split_block', 'blockId': 'block-paper-a',
            'beforeRevision': 1, 'offset': 8})),
        ('merge', lambda: workspace()[0], lambda value: operation_request(value, {'kind': 'merge_blocks',
            'leadingId': 'block-paper-a', 'leadingRevision': 1, 'trailingId': 'block-paper-b', 'trailingRevision': 1})),
        ('marks', joined, lambda value: text_request(value, 5, 20, kind='set_marks', styles={'bold': True})),
        ('insert-paragraph', joined, lambda value: operation_request(value, {'kind': 'insert_paragraph',
            'contextBlockId': 'block-paper-a', 'contextRevision': 1,
            'placement': {'parentId': 'main', 'afterId': 'block-paper-a'}, 'text': 'Fresh'})),
        ('copy-none', joined, lambda value: operation_request(value, {'kind': 'copy_blocks',
            'sources': [{'blockId': 'block-paper-a', 'beforeRevision': 1}],
            'placement': {'parentId': 'main', 'afterId': 'block-paper-b'}})),
        ('table-cell', lambda: tabled('content'), lambda value: text_request(value, 8, 8, target=field_target, cell='content')),
        ('no-op', joined, lambda value: text_request(value, 3, 15, 'Shared title')),
    ]
    result = []
    for name, build, make in plans:
        value = build()
        request = make(value)
        base = response(value)
        prepared = prepare_edit(base, request, proof())
        address = build_address_map(base, request, prepared)
        result.append({'name': name, 'clientMutationId': prepared.client_mutation_id, 'requestHash': prepared.request_hash,
            'createdIds': prepared.created_ids, 'mapSha256': address_map_sha256(address),
            'mapWire': canonical(address).decode(), 'baseWire': trimmed(base), 'resultWire': trimmed(prepared.preview)})
    return {'scope': 'Synthetic pure preparation address maps; trimmed responses keep snapshot and document only',
        'cases': result}


def transport():
    value = json.loads(TRANSPORT.read_text(encoding='utf-8'))
    base = TemplateProjectResponseV1.model_validate_json(value['baseWire'])
    request = WriterPrepareEditV2.model_validate_json(value['requestWire'])
    prepared = prepare_edit(base, request.preparation, request.proof)
    reply = json.loads(value['replyWire'])
    delta = prepared_delta(base, prepared)
    # The workspace patch and hashes follow the project format (D104); the edit itself must reproduce.
    format_fields = {'workspacePatch', 'baseWorkspaceSha256', 'resultWorkspaceSha256'}
    if ({key: item for key, item in json.loads(canonical(delta)).items() if key not in format_fields}
            != {key: item for key, item in reply['delta'].items() if key not in format_fields}):
        raise ValueError('retained transport delta is not reproducible from its base and request')
    value['baseWire'] = canonical(base).decode()
    address = build_address_map(base, request.preparation, prepared)
    wrapped = WriterPreparedDeltaV2(schemaVersion=2, preparationInputSha256=reply['preparationInputSha256'],
        requestHash=reply['requestHash'], delta=delta, addressMap=address, addressMapSha256=address_map_sha256(address))
    value['replyWire'] = canonical(wrapped).decode()
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        ADDRESS.write_text(encoded(cases()), encoding='utf-8')
        TRANSPORT.write_text(encoded(transport()), encoding='utf-8')
    else:
        raise SystemExit('usage: address_map_fixtures.py --write')
