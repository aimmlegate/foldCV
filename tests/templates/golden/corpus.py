"""Loading the golden corpus: stored fixtures, the in-memory fixture builder and same-project clipboard placeholders."""

import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def corpus():
    return json.loads((HERE / 'synthetic/corpus.json').read_text())


def results():
    return json.loads((HERE / 'results.json').read_text())


def loaded(entry):
    """A stored fixture; its package assets come from the bundled template, so a changed template fails to load."""
    from packages.resume_core.models.template_workspace import WorkspaceV7
    from packages.resume_core.templates.models import remember_asset
    from tests.templates.storage_fixtures import package
    for asset in package().assets:
        remember_asset(asset.sha256, asset.bytes_base64, asset.mime_type)
    return WorkspaceV7.model_validate(entry['workspace']), {key: base64.b64decode(raw) for key, raw in entry['sources'].items()}


def with_capture(value, capture_id):
    return json.loads(json.dumps(value).replace('{clipboard}', capture_id))


def fixtures():
    """The starting projects the stored corpus was built from, one per shape the operations need; all synthetic."""
    from packages.resume_core.models.template_workspace import WorkspaceV7
    from packages.resume_core.rich_mutations import apply_rich_mutation
    from tests.templates.storage_fixtures import workspace
    from tests.templates.test_authored_anchors import anchored
    from tests.templates.test_bound_links import linked_workspace
    from tests.templates.test_builtin_scopes import scoped_workspace
    from tests.templates.test_relation_transactions import owner_sections, related_workspace
    from tests.templates.test_sync_preparation import moved
    from tests.templates.test_transactions import issue
    result = {'paper': workspace(), 'anchored': anchored(), 'linked': linked_workspace(), 'scoped': scoped_workspace()}
    value, sources = workspace()
    finding = issue('paste-issue', 'a-title'); finding.block_ids = ['block-paper-a']
    value.project.import_issues = [finding]
    result['issued'] = WorkspaceV7.model_validate(value.model_dump(by_alias=True)), sources
    value, sources = related_workspace()
    result['related'] = owner_sections(value), sources
    before, sources, prepared = moved()
    result['conflict'] = apply_rich_mutation(before, prepared.mutation)[0], sources
    return result
