"""Build and verify the golden mutation corpus through the old writer path (SR00).

    PYTHONPATH=services/api/src .venv/bin/python -m tests.templates.golden.old_path --write   # corpus.json, results.json
    PYTHONPATH=services/api/src .venv/bin/python -m tests.templates.golden.old_path --check   # two runs, same ids and hashes

The writer runs with a fixed proof: the lineage comes from a counter instead of random bytes, the epoch, incarnation and
session are the fixture's constants. This module drives the old stack and goes with it; corpus.json, results.json and
normalize.py stay as the oracle for the repository path.
"""

import argparse
import base64
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile

from tests.templates.golden.corpus import HERE, loaded, with_capture
from tests.templates.golden.normalize import created_ids, new_ids, normalized_hash


SESSION = 'editor-session'


@contextmanager
def fixed_identities():
    from packages.resume_core import background_store
    original, counter = background_store.identity, [0]
    def identity(prefix):
        counter[0] += 1
        return '%s_%024x' % (prefix, counter[0])
    background_store.identity = identity
    try:
        yield
    finally:
        background_store.identity = original


def fixtures():
    """Starting projects, one per shape the operations need; all synthetic test fixtures."""
    from tests.templates.storage_fixtures import workspace
    from tests.templates.test_authored_anchors import anchored
    from tests.templates.test_bound_links import linked_workspace
    from tests.templates.test_builtin_scopes import scoped_workspace
    from tests.templates.test_relation_transactions import owner_sections, related_workspace
    from tests.templates.test_sync_preparation import moved
    from tests.templates.test_transactions import issue
    from packages.resume_core.models.template_workspace import WorkspaceV7
    from packages.resume_core.rich_mutations import apply_rich_mutation
    result = {'paper': workspace(), 'anchored': anchored(), 'linked': linked_workspace(), 'scoped': scoped_workspace()}
    value, sources = workspace()
    finding = issue('paste-issue', 'a-title'); finding.block_ids = ['block-paper-a']
    value.project.import_issues = [finding]
    result['issued'] = WorkspaceV7.model_validate(value.model_dump(by_alias=True)), sources
    value, sources = related_workspace()
    result['related'] = owner_sections(value), sources
    before, sources, prepared = moved()
    result['conflict'] = apply_rich_mutation(before, prepared.mutation)[0], sources
    return result


def stored(fixture):
    value, sources = fixture
    return {'workspace': value.model_dump(mode='json', by_alias=True),
        'sources': {key: base64.b64encode(raw).decode('ascii') for key, raw in sorted(sources.items())}}


def entries(projects):
    """One authored operation per kind of `AuthoredOperation`; literal and same-project paste both."""
    from tests.templates.test_block_paste import block_request
    from tests.templates.test_link_target_edit import link_request
    from tests.templates.test_panel_preparation import panel
    from tests.templates.test_paste_preparation import paste_request
    from tests.templates.test_structural_preparation import intent, place, selection
    from tests.templates.test_sync_preparation import resolve_request
    from tests.templates.test_template_preparation import command
    from types import SimpleNamespace
    placeholder = SimpleNamespace(capture=SimpleNamespace(clipboard_capture_id='{clipboard}'))
    def first(name):
        return projects[name][0].project.document.regions[2].blocks
    paper, anchored = projects['paper'][0], projects['anchored'][0]
    a, b = first('paper')[:2]
    cases = [
        ('replace_text', 'anchored', None, command(anchored, start=6, end=6, text=' typed',
            target={'kind': 'field', 'bindingId': first('anchored')[0].content[0].binding_id})),
        ('set_marks', 'paper', None, command(paper, start=0, end=6, kind='set_marks', styles={'bold': True})),
        ('split_block', 'anchored', None, intent(anchored, 'split_block', **selection(first('anchored')[0]), offset=7)),
        ('merge_blocks', 'paper', None, intent(paper, 'merge_blocks', leadingId=a.id, leadingRevision=a.revision,
            trailingId=b.id, trailingRevision=b.revision)),
        ('insert_paragraph', 'paper', None, intent(paper, 'insert_paragraph', contextBlockId=a.id, contextRevision=a.revision,
            placement=place(a.id), text='Exact human 😀')),
        ('copy_blocks', 'anchored', None, intent(anchored, 'copy_blocks', sources=[selection(first('anchored')[0])],
            placement=place(first('anchored')[-1].id))),
        ('copy_fragment', 'paper', None, intent(paper, 'copy_fragment', source={**selection(a), 'cellId': None,
            'field': 'content', 'start': 0, 'end': 12}, placement=place(a.id))),
        ('paste_inline_literal', 'paper', None, paste_request(paper)),
        ('paste_inline_same_project', 'issued', {'kind': 'range', 'range': {**selection(first('issued')[0]),
            'cellId': None, 'field': 'content', 'start': 1, 'end': 4}}, paste_request(projects['issued'][0], clipboard=placeholder)),
        ('paste_blocks', 'paper', {'kind': 'blocks', 'blocks': [selection(a), selection(b)]},
            block_request(paper, placeholder, after=b.id)),
        ('move_block', 'paper', None, intent(paper, 'move_block', **selection(b), placement=place())),
        ('remove_occurrences', 'anchored', None, intent(anchored, 'remove_occurrences', blocks=[selection(first('anchored')[0])])),
        ('delete_entity', 'related', None, intent(projects['related'][0], 'delete_entity', recordId='paper-a',
            beforeRevision=next(value.revision for value in projects['related'][0].project.facts.extensions if value.id == 'paper-a'))),
        ('builtin_panel', 'scoped', None, panel(projects['scoped'][0], values={'employer': 'Human employer 😀'})),
        ('format_blocks', 'anchored', None, intent(anchored, 'format_blocks', targets=[selection(first('anchored')[0])],
            patch={'blockKind': {'type': 'heading', 'level': 2}, 'alignment': 'center', 'textColor': '#334455',
                'backgroundColor': '#eeeeee'})),
        ('resolve_template_sync', 'conflict', None, resolve_request(projects['conflict'][0])),
        ('set_link_target', 'linked', None, link_request(projects['linked'][0], 'https://example.test/revised')),
    ]
    result = []
    for name, fixture, clipboard, preparation in cases:
        preparation.client_mutation_id = 'golden-' + name.replace('_', '-')
        preparation.capture.action_id = 'golden-action-' + name.replace('_', '-')
        preparation.capture.session_id, preparation.capture.action_token = SESSION, 1
        operation = preparation.operations[0]
        if operation.kind == 'builtin_panel':
            operation.command.capture = preparation.capture.model_copy(deep=True)
        value = preparation.model_dump(mode='json', by_alias=True)
        result.append({'name': name, 'kind': operation.kind, 'fixture': fixture, 'clipboard': clipboard, 'preparation': value})
    return result


def run_entry(entry, fixture, root):
    """Edit, undo and redo of one entry on a fresh store; raw created ids and normalized hashes."""
    from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
    from packages.resume_core.models.template_writer import WriterCaptureClipboardV2, WriterPrepareEditV2
    from packages.resume_core.templates.presentation import snapshot_identity
    from tests.templates.test_preparation_store import save_request
    from tests.templates.test_template_local_history import history_request
    from tests.templates.test_template_writers import TemplateWriterFixture
    workspace, sources = loaded(fixture)
    with fixed_identities():
        writer = TemplateWriterFixture(root, workspace, sources)
        initial = writer.current()
        preparation = entry['preparation']
        capture_id = None
        if entry['clipboard'] is not None:
            capture = writer.writers.capture_clipboard(writer.project, WriterCaptureClipboardV2(schemaVersion=2,
                proof=writer.proof, clientCaptureId='golden-capture', snapshot=snapshot_identity(initial),
                selection=entry['clipboard']))
            capture_id = capture.clipboard_capture_id
            preparation = with_capture(preparation, capture_id)
        request = WriterPrepareEditV2(schemaVersion=2, proof=writer.proof,
            preparation=TemplateEditPreparationV1.model_validate(preparation))
        prepared = writer.writers.prepare_edit(writer.project, request)
        saved = writer.writers.save(writer.project, save_request(writer, prepared), originals=writer.originals)
        result = writer.current()
        allocated = created_ids(prepared.created_ids)
        undo = writer.writers.local_history_command(writer.project, history_request(writer, saved.local_history_ack,
            'undo', 'golden-undo'), originals=writer.originals)
        undone = writer.current()
        redo = writer.writers.local_history_command(writer.project, history_request(writer, undo.local_history_ack,
            'redo', 'golden-redo'), originals=writer.originals)
        redone = writer.current()
    # A step's created ids: the allocator's slots and any id that no earlier state of the entry held.
    created = sorted(set(allocated) | set(new_ids(result, initial)))
    undo_created = new_ids(undone, initial, result)
    redo_created = new_ids(redone, initial, result, undone)
    return {'proof': {'lineage': writer.proof.lineage, 'epoch': writer.proof.epoch, 'incarnation': writer.proof.incarnation,
            'sessionId': writer.proof.session_id},
        'clipboardCaptureId': capture_id,
        'allocated': allocated, 'created': created, 'undoCreated': undo_created, 'redoCreated': redo_created,
        # G3: undo returns the earlier values and redo the edit's values, so their oracles are the initial and result
        # hashes. The old path's own undo and redo are kept beside them; they agree except where the old inverse
        # re-stamped history metadata (listed in SR00.md).
        'hashes': {'initial': normalized_hash(initial, []), 'result': normalized_hash(result, created),
            'undo': normalized_hash(initial, []), 'redo': normalized_hash(result, created)},
        'oldPath': {'undo': normalized_hash(undone, [*created, *undo_created]),
            'redo': normalized_hash(redone, [*created, *undo_created, *redo_created])}}


def run_corpus(corpus):
    output = {}
    for entry in corpus['entries']:
        with tempfile.TemporaryDirectory(prefix='foldcv-golden-', dir='/private/tmp') as folder:
            output[entry['name']] = run_entry(entry, corpus['fixtures'][entry['fixture']], Path(folder))
    return output


def build():
    projects = fixtures()
    corpus = {'schemaVersion': 1, 'proof': {'lineage': 'lineage_%024x' % 1, 'epoch': None, 'incarnation': 'connection-one',
            'sessionId': SESSION, 'note': 'lineage from fixed_identities(); epoch as the fixture opening grants it'},
        'normalization': {'dropped': sorted(__import__('tests.templates.golden.normalize', fromlist=['DROPPED']).DROPPED),
            'createdIds': 'ids of the step replaced by #n in order of first appearance in the canonical text'},
        'fixtures': {name: stored(value) for name, value in sorted(projects.items())},
        'entries': entries(projects)}
    return corpus


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.write:
        if (HERE / 'results.json').exists():
            sys.exit('golden results exist; they are never rewritten')
        corpus = build()
        results = run_corpus(corpus)
        corpus['proof']['epoch'] = next(iter(results.values()))['proof']['epoch']
        (HERE / 'synthetic/corpus.json').write_text(json.dumps(corpus, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
        (HERE / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
        print(json.dumps({name: {**value['hashes'], 'oldPathAgrees': value['oldPath'] == {'undo': value['hashes']['undo'],
            'redo': value['hashes']['redo']}} for name, value in results.items()}, indent=1))
    if args.check:
        corpus = json.loads((HERE / 'synthetic/corpus.json').read_text())
        golden = json.loads((HERE / 'results.json').read_text())
        first, second = run_corpus(corpus), run_corpus(corpus)
        same = first == second == golden
        print(json.dumps({'runsEqual': first == second, 'equalToGolden': first == golden,
            'entries': len(first)}, indent=1))
        sys.exit(0 if same else 1)


if __name__ == '__main__':
    main()
