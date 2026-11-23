"""F3-0 of the tester feedback of 2026-11-23: a deletion of a field's whole text takes the field off the page and keeps
its fact; a deletion of a part still edits the fact."""

import pytest

from packages.resume_core.editing.mutations import apply_rich_mutation
from packages.resume_core.editing.template_inverse import inverse_template_mutation, semantic
from packages.resume_core.models.template_document import FieldOccurrence, PresentedText
from packages.resume_core.models.template_workspace import WorkspaceV7
from tests.templates.e04_fixtures import e04_workspace
from tests.templates.test_structural_preparation import prepare
from tests.templates.test_transactions import authorization


def line(workspace, text):
    return next(block for block in workspace.project.document.blocks()
        if isinstance(block.content, list) and ''.join(getattr(span, 'text', '') for span in block.content) == text)


def block(workspace, identifier):
    return next(value for value in workspace.project.document.blocks() if value.id == identifier)


def shown(value):
    return ''.join(span.text for span in value.content)


def delete(before, target, start, end, text=''):
    return prepare(before, 'replace_text', range={'blockId': target.id, 'beforeRevision': target.revision,
        'cellId': None, 'field': 'content', 'start': start, 'end': end}, text=text, styles={})


def fields(value):
    return [span for span in value.content if isinstance(span, FieldOccurrence)]


def undone(before, result):
    after = result.preview.workspace
    inverse = inverse_template_mutation(before, after, origin_action_id=result.mutation.action_id,
        mutation_id='undo-' + result.mutation.client_mutation_id, session_id='session', action_token=2)
    return apply_rich_mutation(after, inverse, history_authorization=authorization(after, inverse))[0]


def test_a_whole_field_deleted_leaves_no_fragment_and_keeps_its_fact():
    before, _ = e04_workspace()
    employer = line(before, 'Example Labs')
    result = delete(before, employer, 0, 12)
    after = result.preview.workspace
    assert block(after, employer.id).content == []
    assert after.project.facts == before.project.facts
    assert [step.kind for step in result.mutation.steps] == ['replace_inline_range']


def test_a_part_deleted_still_edits_the_fact():
    before, _ = e04_workspace()
    employer = line(before, 'Example Labs')
    after = delete(before, employer, 7, 12).preview.workspace
    assert shown(block(after, employer.id)) == 'Example'
    record = next(value for value in after.project.facts.records if value.id == employer.content[0].record_id)
    assert record.employer.value == 'Example'


def test_a_replacement_of_the_whole_text_edits_the_fact():
    before, _ = e04_workspace()
    employer = line(before, 'Example Labs')
    after = delete(before, employer, 0, 12, 'New Labs').preview.workspace
    [span] = fields(block(after, employer.id))
    assert span.text == 'New Labs'
    record = next(value for value in after.project.facts.records if value.id == employer.content[0].record_id)
    assert record.employer.value == 'New Labs'


def test_other_occurrences_of_a_fact_shown_twice_stay_as_they_are():
    before, _ = e04_workspace()
    employer = line(before, 'Example Labs')
    copy = employer.model_copy(deep=True)
    copy.id = 'block-employer-copy'
    copy.content[0].binding_id = 'copy-fragment'
    copy.content[0].binding_root_id = copy.content[0].occurrence_id = 'copy-occurrence'
    section = next(value for value in before.project.document.blocks() if employer in value.children)
    section.children.insert(1, copy)
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    after = delete(before, line(before, 'Example Labs'), 0, 12).preview.workspace
    assert block(after, employer.id).content == []
    kept = block(after, copy.id)
    assert [(span.type, span.text, span.occurrence_id) for span in kept.content] == [
        ('fact_field', 'Example Labs', 'copy-occurrence')]
    assert after.project.facts == before.project.facts


def test_a_line_with_two_fields_and_a_literal_between_them():
    before, _ = e04_workspace()
    dates = line(before, '03.2020–11.2023')
    whole = delete(before, dates, 0, 15).preview.workspace
    assert block(whole, dates.id).content == [] and whole.project.facts == before.project.facts
    # The start field and the dash go whole; the end field loses a part, so only its fact changes.
    part = delete(before, dates, 0, 11).preview.workspace
    [span] = fields(block(part, dates.id))
    assert (shown(block(part, dates.id)), span.occurrence_id) == ('2023', dates.content[2].occurrence_id)
    record = next(value for value in part.project.facts.records if value.id == dates.content[0].record_id)
    old = next(value for value in before.project.facts.records if value.id == record.id)
    assert record.model_dump(exclude={'period', 'revision', 'periods', 'user_corrected'}) == old.model_dump(
        exclude={'period', 'revision', 'periods', 'user_corrected'})
    assert part.project.facts != before.project.facts


def test_a_literal_cut_with_a_whole_field_keeps_the_fact():
    before, _ = e04_workspace()
    role = line(before, 'Role: Backend Engineer')
    after = delete(before, role, 3, 22).preview.workspace
    assert [(span.type, span.text) for span in block(after, role.id).content] == [('text', 'Rol')]
    assert after.project.facts == before.project.facts


def test_an_empty_fragment_an_older_save_left_goes_with_the_field():
    before, _ = e04_workspace()
    employer = line(before, 'Example Labs')
    employer.content.append(employer.content[0].model_copy(update={'binding_id': 'older-empty', 'text': ''}, deep=True))
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    result = delete(before, line(before, 'Example Labs'), 0, 12)
    assert block(result.preview.workspace, employer.id).content == []
    assert result.preview.workspace.project.facts == before.project.facts
    assert semantic(undone(before, result).project.document) == semantic(before.project.document)


def test_a_field_emptied_before_keeps_its_old_fragment():
    before, _ = e04_workspace()
    employer = line(before, 'Example Labs')
    employer.content.append(PresentedText(type='text', text=' Ltd', styles={}))
    employer.content[0].text = ''
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    after = delete(before, block(before, employer.id), 2, 4).preview.workspace
    assert [(span.type, span.text) for span in block(after, employer.id).content] == [('fact_field', ''), ('text', ' L')]
    assert after.project.facts == before.project.facts


def test_a_whole_technology_name_stays_locked():
    before, _ = e04_workspace()
    with pytest.raises(ValueError, match='TECHNOLOGY_NAME_EMPTY'):
        delete(before, line(before, 'Python'), 0, 6)


def test_the_inverse_restores_the_occurrence_with_the_same_ids():
    before, _ = e04_workspace()
    dates = line(before, '03.2020–11.2023')
    result = delete(before, dates, 0, 15)
    restored = undone(before, result)
    assert block(restored, dates.id).content == dates.content
    assert restored.project.facts == before.project.facts


def test_a_bound_link_whose_whole_label_is_deleted_goes_with_its_url():
    from tests.templates.test_bound_links import linked_workspace
    before, _ = linked_workspace()
    target = before.project.document.regions[2].blocks[0]
    target.content.append(PresentedText(type='text', text=' trailing', styles={}))
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    target = before.project.document.regions[2].blocks[0]
    for end in (12, 15):
        result = delete(before, target, 0, end)
        after = result.preview.workspace.project.document.regions[2].blocks[0]
        assert [(span.type, span.text) for span in after.content] == [('text', ' trailing'[end - 12:])]
        assert result.preview.workspace.project.facts == before.project.facts
        assert semantic(undone(before, result).project.document) == semantic(before.project.document)
