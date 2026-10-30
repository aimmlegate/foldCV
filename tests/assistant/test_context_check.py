"""The deterministic resume check of the assistant (assistant/context.check): empty blocks and links without a target
are named by block, with no edit."""

from types import SimpleNamespace

from packages.resume_core.models.template_document import BoundLink
from resume_api.assistant.context import _empty, check
from tests.assistant.fixtures import tabled
from tests.templates.storage_fixtures import workspace as papers


def test_an_image_without_a_caption_and_a_divider_are_not_empty_blocks():
    workspace, _sources = tabled()
    image = next(block for block in workspace.project.document.blocks() if block.id == 'image-block')
    image.props.caption = []
    assert check(workspace)['emptyBlocks'] == []
    assert not _empty(SimpleNamespace(type='divider', content=None, props=None))
    cell = workspace.project.document.regions[2].blocks[0]
    cell.content.rows[0].cells[0].content = []
    assert check(workspace)['emptyBlocks'] == [cell.id]


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
