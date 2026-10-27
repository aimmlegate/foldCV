"""Clipboard capture, paste, a changed source cell, and eviction of the oldest capture (plan SR04)."""

from tests.projects.support import Editor, v2_app
from tests.templates.golden.corpus import corpus, loaded, with_capture
from tests.templates.test_template_preparation import command


def entry(name):
    value = next(item for item in corpus()['entries'] if item['name'] == name)
    return value, loaded(corpus()['fixtures'][value['fixture']])


def full_cell(editor):
    """The whole title cell, so the capture keeps a field witness rather than a literal slice."""
    block = next(item for item in editor.workspace().project.document.blocks() if item.id == 'block-paper-a')
    return {'kind': 'range', 'range': {'beforeRevision': block.revision, 'blockId': block.id, 'cellId': None,
        'field': 'content', 'start': 0, 'end': len(block.content[0].text.encode('utf-16-le')) // 2}}


def paste_as(preparation, capture_id, mutation_id):
    body = with_capture(preparation, capture_id)
    body['clientMutationId'] = mutation_id
    body['capture']['actionId'] = mutation_id
    return body


def test_a_captured_fragment_pastes(tmp_path):
    paste, (workspace, sources) = entry('paste_inline_same_project')
    with v2_app(tmp_path, [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        capture = editor.capture(paste['clipboard'], 'copy-1')
        pasted = editor.edit(paste_as(paste['preparation'], capture['clipboardCaptureId'], 'paste-fragment'))
        assert pasted['revision'] == 2 and pasted['replayed'] is False


def test_a_changed_source_cell_refuses_the_paste(tmp_path):
    paste, (workspace, sources) = entry('paste_inline_same_project')
    with v2_app(tmp_path, [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        selection = full_cell(editor)
        held = editor.capture(selection, 'held')['clipboardCaptureId']
        change = command(editor.workspace(), end=selection['range']['end'], text='Changed title')
        change.client_mutation_id, change.capture.action_id = 'change-cell', 'change-cell'
        assert editor.edit(change.model_dump(mode='json', by_alias=True))['revision'] == 2
        refused = editor.edit(paste_as(paste['preparation'], held, 'paste-after-cell-change'), status=409)
        assert refused['error']['code'] == 'DEPENDENCY_CHANGED'


def test_an_evicted_capture_cannot_be_pasted(tmp_path):
    paste, (workspace, sources) = entry('paste_inline_same_project')
    with v2_app(tmp_path, [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        first = editor.capture(paste['clipboard'], 'evict-0')['clipboardCaptureId']
        for index in range(1, 21):
            editor.capture(paste['clipboard'], 'evict-' + str(index))
        expired = editor.edit(paste_as(paste['preparation'], first, 'paste-evicted'), status=409)
        assert expired['error']['code'] == 'REQUEST_EXPIRED'
