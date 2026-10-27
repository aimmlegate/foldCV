"""A bound link's URL edit changes only its URL cell and target, with its own Undo, and survives transfer."""

import pytest

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import BoundLink
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.archive_zip import write_zip
from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
from packages.resume_core.rich_fields import bound_link_fields
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.compiler import canonical
from tests.templates.editor_fixtures import TemplateEditor
from tests.templates.test_bound_links import linked_workspace
from tests.templates.test_template_preparation import command, response


def link_request(before, href, *, occurrence='url-occurrence', revision=None, identifier='link-target'):
    block = before.project.document.regions[2].blocks[0]
    value = command(before).model_dump(by_alias=True)
    value['clientMutationId'] = value['capture']['actionId'] = identifier
    value['operations'] = [{'opId': 'link', 'kind': 'set_link_target', 'blockId': block.id,
        'beforeRevision': block.revision if revision is None else revision, 'occurrenceId': occurrence, 'href': href}]
    return TemplateEditPreparationV1.model_validate(value)


def url_only(value):
    link = value.project.document.regions[2].blocks[0].content[0]
    link.label_binding = None
    span = link.content[0]
    span.record_id, span.field_key, span.cell_id = 'paper-a', 'url', 'a-url'
    span.occurrence_id = span.binding_root_id = 'url-occurrence'
    span.text = link.href
    return WorkspaceV7.model_validate(value.model_dump(by_alias=True))


def cells(workspace):
    record = next(value for value in workspace.project.facts.extensions if value.id == 'paper-a')
    return {cell.field_key: cell for cell in record.cells}


def values(workspace):
    # Undo restores values; revisions keep increasing.
    return {key: cell.model_dump(exclude={'revision'}) for key, cell in cells(workspace).items()}


@pytest.mark.parametrize('href', ['https://example.test/revised', '', 'example.test/no-scheme'])
@pytest.mark.parametrize('occurrence', ['url-occurrence', 'label-occurrence'])
def test_url_edit_changes_only_the_url_cell_and_target(href, occurrence):
    before, _ = linked_workspace()
    raw = canonical(before)
    prepared = prepare_edit(response(before), link_request(before, href, occurrence=occurrence))
    assert canonical(before) == raw
    after = prepared.preview.workspace
    link = after.project.document.regions[2].blocks[0].content[0]
    assert isinstance(link, BoundLink) and link.href == href
    # A cleared URL keeps the label as text and keeps the URL binding and its cell.
    assert ''.join(child.text for child in link.content) == 'Shared title'
    assert link.label_binding.cell_id == 'a-title' and link.url_binding.cell_id == 'a-url'
    old, new = cells(before), cells(after)
    assert new['url'].raw_input == href and new['url'].origin == 'human' and new['url'].state == 'human_raw'
    assert {key: value for key, value in new.items() if key != 'url'} == {key: value for key, value in old.items() if key != 'url'}
    assert prepared.mutation.kind == 'panel'
    assert {step.kind for step in prepared.mutation.steps} == {'put_extension', 'put_block'}


def test_url_only_link_shows_its_new_exact_url():
    before = url_only(linked_workspace()[0])
    prepared = prepare_edit(response(before), link_request(before, 'https://example.test/other'))
    link = prepared.preview.workspace.project.document.regions[2].blocks[0].content[0]
    assert link.href == 'https://example.test/other' and [child.text for child in link.content] == ['https://example.test/other']
    assert link.content[0].complete
    assert [(field.role, field.text) for field in bound_link_fields(prepared.preview.workspace.project.document)] == [
        ('url', 'https://example.test/other')]


def test_same_url_is_a_no_op_and_stale_or_unknown_targets_are_refused():
    before, _ = linked_workspace()
    assert prepare_edit(response(before), link_request(before, 'https://example.test/a')).mutation is None
    for request in [link_request(before, 'https://example.test/b', revision=99),
            link_request(before, 'https://example.test/b', occurrence='missing-occurrence')]:
        with pytest.raises(ValueError):
            prepare_edit(response(before), request)


def test_label_and_url_edits_have_independent_undo_through_the_journal_and_transfer(tmp_path):
    before, sources = linked_workspace()
    editor = TemplateEditor(tmp_path, before, sources)
    editor.edit(link_request(editor.current(), 'https://example.test/revised'))
    label = command(editor.current(), start=0, end=6, text='Human')
    label.client_mutation_id = label.capture.action_id = 'label-edit'
    editor.edit(label)
    current = editor.current()
    link = current.project.document.regions[2].blocks[0].content[0]
    assert (''.join(child.text for child in link.content), link.href) == ('Human title', 'https://example.test/revised')
    assert (cells(current)['title'].raw_input, cells(current)['url'].raw_input) == ('Human title', 'https://example.test/revised')
    moved, *_ = open_archive_v7(write_zip(archive_payload_v7(current, sources, {})), 'link-transfer')
    assert moved.project.document == current.project.document and moved.project.facts == current.project.facts
    # Undo takes back the label edit alone, then the URL edit alone; Redo restores only the URL.
    label_undone = editor.undo('undo-label', expected='label-edit').response.workspace
    link = label_undone.project.document.regions[2].blocks[0].content[0]
    assert (''.join(child.text for child in link.content), link.href) == ('Shared title', 'https://example.test/revised')
    assert values(label_undone)['title'] == values(before)['title']
    url_undone = editor.undo('undo-url', expected='link-target').response.workspace
    link = url_undone.project.document.regions[2].blocks[0].content[0]
    assert (''.join(child.text for child in link.content), link.href) == ('Shared title', 'https://example.test/a')
    assert values(url_undone) == values(before)
    redone = editor.redo('redo-url', expected='link-target').response.workspace
    link = redone.project.document.regions[2].blocks[0].content[0]
    assert (''.join(child.text for child in link.content), link.href) == ('Shared title', 'https://example.test/revised')
    assert values(redone)['title'] == values(before)['title']


def test_a_url_cell_waiting_on_a_manual_scope_is_refused():
    from packages.resume_core.template_facts import ambiguous_edit
    before, _ = linked_workspace()
    before.project.facts = ambiguous_edit(before.project.facts, ['a-journal', 'a-url'], 'Both', 'scoped', ['block-paper-a'])
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    with pytest.raises(ValueError, match='manual edit scope'):
        prepare_edit(response(before), link_request(before, 'https://example.test/b'))
