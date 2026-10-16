"""Scoped typed inverses restore edits while retaining independent later input."""

import pytest

from packages.resume_core.agent_edits import semantic
from packages.resume_core.background_inverse import inverse_mutation
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.rich_mutations import apply_rich_mutation, locate
from tests.support.agent import isolated_project


def mutation(workspace, steps, identifier="original"):
    return RichMutation(schemaVersion=1, projectId=workspace.project_id, clientMutationId=identifier,
        actionId=identifier, kind="structure", capture={"sessionId": "session", "actionId": identifier,
            "actionToken": 0, "dependencies": []}, steps=steps)


def block(workspace, identifier):
    found = locate(workspace.project.document, identifier)
    return found[0][found[1]]


def put(workspace, identifier, parent="job-section", after=None, text="Changed"):
    value = block(workspace, identifier).model_copy(deep=True)
    if isinstance(value.content, list):
        value.content[0].text = text
    value.children = []
    return {"kind": "put_block", "parentId": parent, "afterId": after,
        "beforeRevision": value.revision, "block": value, "keepChildren": True}


@pytest.mark.parametrize("shape", ["text", "move", "move-and-text", "insert", "remove", "replace-tree", "fact", "remove-fact"])
def test_typed_inverse_restores_each_kind_of_edit(tmp_path, shape):
    _, _, before, _ = isolated_project(tmp_path)
    if shape == "text":
        steps = [put(before, "narrative")]
    elif shape == "move":
        steps = [{"kind": "move_block", "blockId": "quote", "parentId": "job-section", "afterId": None,
            "beforeRevision": block(before, "quote").revision}]
    elif shape == "move-and-text":
        steps = [{"kind": "move_block", "blockId": "quote", "parentId": "job-section", "afterId": None,
            "beforeRevision": block(before, "quote").revision}, put(before, "quote", text="Changed quote")]
    elif shape == "insert":
        value = block(before, "narrative").model_copy(update={"id": "inserted", "children": []})
        steps = [{"kind": "put_block", "block": value, "parentId": "job-section", "afterId": None,
            "beforeRevision": None}]
    elif shape == "remove":
        steps = [{"kind": "remove_block", "blockId": "job-section", "beforeRevision": block(before, "job-section").revision}]
    elif shape == "replace-tree":
        value = block(before, "job-section").model_copy(deep=True)
        value.children = [value.children[0].model_copy(update={"id": "replacement", "children": []})]
        steps = [{"kind": "put_block", "block": value, "parentId": locate(before.project.document, "job-section")[2].id, "afterId": None,
            "beforeRevision": value.revision}]
    elif shape == "remove-fact":
        steps = [{"kind": "remove_record", "recordId": "language-1", "beforeRevision": 1}]
    else:
        value = before.project.facts.records[0].model_copy(deep=True)
        value.user_corrected = not value.user_corrected
        steps = [{"kind": "put_record", "record": value, "beforeRevision": value.revision}]
    after, _ = apply_rich_mutation(before, mutation(before, steps))
    inverse = inverse_mutation(before, after, mutation_id="inverse", session_id="session")
    assert inverse is not None
    restored, duplicate = apply_rich_mutation(after, inverse)
    assert not duplicate
    assert semantic(restored.project.document) == semantic(before.project.document)
    assert semantic(restored.project.facts) == semantic(before.project.facts)


def test_inverse_does_not_replace_an_independent_later_block(tmp_path):
    _, _, before, _ = isolated_project(tmp_path)
    after, _ = apply_rich_mutation(before, mutation(before, [put(before, "narrative")]))
    inverse = inverse_mutation(before, after, mutation_id="inverse", session_id="session")
    latest, _ = apply_rich_mutation(after, mutation(after, [put(after, "quote", text="Independent user input")], "later"))
    restored, _ = apply_rich_mutation(latest, inverse)
    assert block(restored, "quote").content[0].text == "Independent user input"
    assert semantic(block(restored, "narrative")) == semantic(block(before, "narrative"))
