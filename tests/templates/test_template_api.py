"""Template project responses keep the workspace, snapshot, presentation and saved revisions coherent."""

import pytest

from packages.resume_core.template_api import TemplateProjectResponseV1
from resume_api.projects.service import response_for_workspace
from tests.templates.pipeline_fixtures import setup_operation, source_draft
from tests.templates.test_materialize import issue_workspace


@pytest.mark.parametrize('change', ['snapshot', 'presentation', 'workspace', 'save_ack'])
def test_response_rejects_mismatched_workspace_snapshot_presentation_or_durable_ack(change):
    workspace, _sources = issue_workspace()
    value = response_for_workspace(workspace).model_dump(mode='json', by_alias=True)
    if change == 'snapshot':
        value['snapshot']['factsHash'] = '0' * 64
    elif change == 'presentation':
        value['presentation']['recipe']['style']['page']['first_body_top'] += 1
    elif change == 'workspace':
        value['workspace']['project']['document']['revision'] += 1
        value['workspace']['documentRevision'] += 1
    else:
        value['savedDocumentRevision'] += 1
    with pytest.raises(ValueError):
        TemplateProjectResponseV1.model_validate(value)


def test_template_predraft_has_null_snapshot_and_presentation():
    operation, _command, package, src, facts = setup_operation()
    before = source_draft(operation, facts, captured=package, src=src)
    response = response_for_workspace(before)
    assert response.workspace.schema_version == 7 and response.snapshot is None and response.presentation is None
    assert response.durability == 'durable'
    assert TemplateProjectResponseV1.model_validate(response.model_dump(mode='json', by_alias=True)) == response
