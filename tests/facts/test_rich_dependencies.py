"""Dependency stamps: unrelated typing stays current, a replaced block or unknown field is stale."""

import pytest

from packages.resume_core.rich_dependencies import dependency, dependencies_current
from packages.resume_core.rich_fields import field_key
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from tests.support.rich import mutation, patch, without_sources


def test_dependencies_reject_missing_unknown_field_and_equal_text_replacement_but_allow_unrelated_typing():
    workspace = without_sources()
    stamps = [dependency(workspace, "block", "title"), dependency(workspace, "field", field_key("candidate-1", "title")),
        dependency(workspace, "ownership", "title")]
    edited, _ = apply_rich_mutation(workspace, patch(workspace, "Unrelated"))
    assert dependencies_current(edited, stamps)
    block = workspace.project.document.regions[0].blocks[1]
    replace = {"kind": "put_block", "parentId": "header", "afterId": "name", "beforeRevision": block.revision, "block": block.model_dump(by_alias=True)}
    replaced, _ = apply_rich_mutation(workspace, mutation(workspace, [replace]))
    assert not dependencies_current(replaced, stamps)
    missing = {"kind": "field", "id": '["fact","candidate-1","missing"]', "revision": 1, "fingerprint": None}
    with pytest.raises(RichMutationFailure, match="STALE_MUTATION"):
        apply_rich_mutation(workspace, mutation(workspace, [replace], [missing]))
