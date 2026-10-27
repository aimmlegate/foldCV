"""The deterministic resume check of the assistant (assistant/context.check): empty blocks and links without a target
are named by block, with no edit."""

from packages.resume_core.models.template_document import BoundLink
from resume_api.assistant.context import check
from tests.templates.storage_fixtures import workspace as papers


def test_check_names_empty_blocks_and_links_without_a_target_and_changes_nothing():
    workspace, _sources = papers()
    clean = check(workspace)
    assert clean['emptyBlocks'] == [] and clean['linksWithoutTarget'] == [] and clean['openImportIssues'] == []
    first, second = workspace.project.document.regions[2].blocks[:2]
    first.content = []
    text = second.content[0].model_copy(deep=True)
    second.content = [BoundLink.model_construct(type='bound_link', href='', content=[text], label_binding=None,
        url_binding=None, presentation=None)]
    before = workspace.model_copy(deep=True)
    report = check(workspace)
    assert report['emptyBlocks'] == [first.id] and report['linksWithoutTarget'] == [second.id]
    assert report['projectRevision'] == workspace.project_revision and workspace == before
