"""Label and URL bindings have independent identity and authored values."""

import pytest

from packages.resume_core.models.template_document import BoundLink, PresentedText
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.archive_zip import write_zip
from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
from packages.resume_core.rich_fields import bound_link_fields
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.template_authoring import copy_fragment
from packages.resume_core.template_facts import human_edit
from tests.templates.storage_fixtures import workspace
from tests.templates.test_transactions import extension_step, request


def linked_workspace():
    value, sources = workspace()
    block = value.project.document.regions[2].blocks[0]
    label = block.content[0].model_copy(deep=True)
    label.binding_root_id = label.occurrence_id = 'label-occurrence'
    link = BoundLink(type='bound_link', href='https://example.test/a', content=[label],
        labelBinding={'recordId': 'paper-a', 'fieldKey': 'title', 'cellId': 'a-title', 'occurrenceId': 'label-occurrence'},
        urlBinding={'recordId': 'paper-a', 'fieldKey': 'url', 'cellId': 'a-url', 'occurrenceId': 'url-occurrence'},
        presentation=block.presentation)
    block.content = [link]
    return WorkspaceV7.model_validate(value.model_dump(by_alias=True)), sources


@pytest.mark.parametrize('role,text', [('label', 'Human label'), ('url', 'https://example.test/revised'), ('url', '')])
def test_bound_link_edits_change_only_the_selected_cell_and_survive_transfer(role, text):
    before, sources = linked_workspace()
    key = 'title' if role == 'label' else 'url'
    edited = human_edit(before.project.facts, 'paper-a', key, text)
    block = before.project.document.regions[2].blocks[0].model_copy(deep=True)
    if role == 'label':
        block.content[0].content[0].text = text
    else:
        block.content[0].href = text
    changed, _ = apply_rich_mutation(before, request(before, [extension_step(before, edited.extensions[0]),
        {'kind': 'put_block', 'parentId': 'main', 'afterId': None, 'beforeRevision': 1,
            'block': block.model_dump(by_alias=True)}]))
    fields = bound_link_fields(changed.project.document)
    assert [(field.role, field.reference.cell_id) for field in fields] == [('label', 'a-title'), ('url', 'a-url')]
    assert fields[0].text == (text if role == 'label' else 'Shared title')
    assert fields[1].text == (text if role == 'url' else 'https://example.test/a')
    untouched = 3 if role == 'label' else 0
    assert changed.project.facts.extensions[0].cells[untouched] == before.project.facts.extensions[0].cells[untouched]
    copied, _, _, _ = open_archive_v7(write_zip(archive_payload_v7(changed, sources, {})), 'bound-link-copy')
    assert copied.project.document == changed.project.document
    assert copied.project.facts == changed.project.facts


def test_url_only_binding_displays_its_exact_url_without_a_label_cell():
    value, _ = linked_workspace()
    link = value.project.document.regions[2].blocks[0].content[0]
    link.label_binding = None
    span = link.content[0]
    span.record_id, span.field_key, span.cell_id = 'paper-a', 'url', 'a-url'
    span.occurrence_id = span.binding_root_id = 'url-occurrence'
    span.text = link.href
    checked = WorkspaceV7.model_validate(value.model_dump(by_alias=True))
    fields = bound_link_fields(checked.project.document)
    assert len(fields) == 1 and fields[0].role == 'url'
    assert checked.project.document.regions[2].blocks[0].content[0].content[0].text == 'https://example.test/a'


@pytest.mark.parametrize('literal_label', [False, True])
def test_partial_link_copy_retains_literal_marks_target_and_exact_source_citations(literal_label):
    value, _ = linked_workspace()
    block = value.project.document.regions[2].blocks[0]
    if literal_label:
        block.content[0].content = [PresentedText(type='text', text='Shared title', styles={}, presentation=block.presentation)]
        value = WorkspaceV7.model_validate(value.model_dump(by_alias=True))
        block = value.project.document.regions[2].blocks[0]
    block.content[0].content[0].styles.italic = True
    copied = copy_fragment(value.project, block, 0, 6)
    assert copied.content[0].type == 'link' and copied.content[0].href == 'https://example.test/a'
    assert copied.content[0].content[0].text == 'Shared'
    assert copied.content[0].content[0].styles.italic
    assert copied.content[0].content[0].citations
    assert all(child.type == 'text' for child in copied.content[0].content)
    assert not hasattr(copied.content[0], 'label_binding') and not hasattr(copied.content[0], 'url_binding')


def test_complete_literal_label_copy_retains_both_cells_with_new_occurrence_roots():
    value, _ = linked_workspace()
    block = value.project.document.regions[2].blocks[0]
    link = block.content[0]
    link.content = [PresentedText(type='text', text='Shared title', styles={})]
    copied = copy_fragment(value.project, block, 0, len('Shared title')).content[0]
    assert copied.type == 'bound_link'
    assert copied.label_binding.cell_id == 'a-title' and copied.url_binding.cell_id == 'a-url'
    assert copied.label_binding.occurrence_id != 'label-occurrence'
    assert copied.url_binding.occurrence_id != 'url-occurrence'


def test_same_occurrence_root_cannot_select_another_cell():
    value, _ = linked_workspace()
    value.project.document.regions[2].blocks[1].content[0].occurrence_id = 'label-occurrence'
    value.project.document.regions[2].blocks[1].content[0].binding_root_id = 'label-occurrence'
    with pytest.raises(ValueError, match='different semantic cells'):
        WorkspaceV7.model_validate(value.model_dump(by_alias=True))
