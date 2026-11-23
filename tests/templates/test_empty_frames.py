"""F2 of the tester feedback of 2026-11-23: an occurrence removal that takes the last line of a section takes the section."""

from packages.resume_core.editing.mutations import apply_rich_mutation
from packages.resume_core.editing.template_inverse import inverse_template_mutation
from tests.assistant.test_compiler import commit, ops, stored
from tests.templates.e04_fixtures import e04_workspace
from tests.templates.test_structural_preparation import prepare, selection
from tests.templates.test_transactions import authorization


def sections(workspace):
    return [block for block in workspace.project.document.blocks() if block.type == 'section']


def ids(workspace):
    return [block.id for block in workspace.project.document.blocks()]


def removed(before, blocks):
    return prepare(before, 'remove_occurrences', blocks=[selection(block) for block in blocks])


def test_the_section_goes_with_its_last_lines_and_the_heading_stays():
    before, _ = e04_workspace()
    first, second = sections(before)
    result = removed(before, second.children)
    after = result.preview.workspace
    assert second.id not in ids(after) and not {child.id for child in second.children} & set(ids(after))
    assert first.id in ids(after) and any(block.type == 'heading' for block in after.project.document.blocks())
    assert after.project.facts == before.project.facts
    # One root removal: the section takes its lines with it.
    assert [step.block_id for step in result.mutation.steps if step.kind == 'remove_block'] == [second.id]


def test_a_section_stays_while_one_of_its_lines_stays():
    before, _ = e04_workspace()
    first, _second = sections(before)
    after = removed(before, first.children[1:]).preview.workspace
    kept = next(block for block in after.project.document.blocks() if block.id == first.id)
    assert [child.id for child in kept.children] == [first.children[0].id]
    alone = removed(after, kept.children).preview.workspace
    assert first.id not in ids(alone)


def test_a_section_that_was_empty_before_stays():
    before, _ = e04_workspace()
    first, second = sections(before)
    region = next(region for region in before.project.document.regions if second in region.blocks)
    # A moved last line can leave an empty section; the removal of other lines does not take it.
    for line in second.children:
        current = next(block for block in before.project.document.blocks() if block.id == line.id)
        before = prepare(before, 'move_block', **selection(current), placement={'parentId': region.id, 'afterId': second.id}).preview.workspace
    first, second = sections(before)
    assert second.children == []
    after = removed(before, first.children).preview.workspace
    assert first.id not in ids(after)
    assert second.id in ids(after), 'the operation did not empty it'


def test_facts_and_anchors_stay_and_the_inverse_restores_the_same_ids():
    before, _ = e04_workspace()
    _first, second = sections(before)
    result = removed(before, [second.children[-1], second.children[0]])
    after = result.preview.workspace
    assert after.project.facts == before.project.facts
    assert len(after.project.import_coverage) == len(before.project.import_coverage)
    inverse = inverse_template_mutation(before, after, origin_action_id=result.mutation.action_id,
        mutation_id='undo-empty-frame', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(after, inverse, history_authorization=authorization(after, inverse))
    def shape(workspace):
        return [(block.id, block.type, [child.id for child in block.children], [span.model_dump(by_alias=True) for span in block.content] if isinstance(block.content, list) else block.content.model_dump(by_alias=True))
            for block in workspace.project.document.blocks()]
    assert shape(restored) == shape(before), 'the same IDs, order and content come back'
    assert restored.project.facts == before.project.facts
    assert restored.project.import_coverage == before.project.import_coverage


def test_an_assistant_delete_of_the_last_line_also_removes_its_section(tmp_path):
    workspace, sources = e04_workspace()
    _first, second = sections(workspace)
    repository = stored(tmp_path, workspace, sources)
    commit(repository, workspace.project_id, ops({'op': 'delete_blocks', 'blockIds': [child.id for child in second.children]}))
    after = repository.read(workspace.project_id)
    assert second.id not in ids(after)
    assert after.project.facts.records == workspace.project.facts.records
