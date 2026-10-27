"""Every authored operation of the SR00 corpus gives the old path's normalized result through /v2, and undo and redo
return the exact earlier and later states (G3); two runs allocate the same raw ids."""

import pytest

from packages.resume_core.models.template_workspace import WorkspaceV7
from tests.projects.support import Editor, v2_app
from tests.templates.golden.corpus import corpus, loaded, results, with_capture
from tests.templates.golden.normalize import created_ids, new_ids, normalized_hash

CORPUS, GOLDEN = corpus(), results()


def run(root, entry):
    workspace, sources = loaded(CORPUS['fixtures'][entry['fixture']])
    with v2_app(root, [(workspace, sources)]) as (client, _app):
        editor = Editor(client, workspace.project_id)
        initial = editor.workspace()
        preparation = entry['preparation']
        if entry['clipboard'] is not None:
            preparation = with_capture(preparation, editor.capture(entry['clipboard'], 'golden-capture')['clipboardCaptureId'])
        edited = editor.edit(preparation)
        result = editor.workspace()
        allocated = created_ids(edited['createdIds'])
        action = edited['history']['undo']['actionId']
        editor.step('undo', 'golden-undo', expected=action)
        undone = editor.workspace()
        editor.step('redo', 'golden-redo', expected=action)
        redone = editor.workspace()
    created = sorted(set(allocated) | set(new_ids(result, initial)))
    undo_created = new_ids(undone, initial, result)
    redo_created = new_ids(redone, initial, result, undone)
    return allocated, {'initial': normalized_hash(initial, []), 'result': normalized_hash(result, created),
        'undo': normalized_hash(undone, [*created, *undo_created]),
        'redo': normalized_hash(redone, [*created, *undo_created, *redo_created])}


@pytest.mark.parametrize('entry', CORPUS['entries'], ids=lambda entry: entry['name'])
def test_v2_reproduces_the_golden_result_undo_and_redo(tmp_path, entry):
    first_ids, hashes = run(tmp_path / 'first', entry)
    second_ids, again = run(tmp_path / 'second', entry)
    assert hashes == GOLDEN[entry['name']]['hashes']
    assert first_ids == second_ids and len(first_ids) == len(GOLDEN[entry['name']]['allocated'])
    assert again == hashes
