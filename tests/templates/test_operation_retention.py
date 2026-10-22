"""Canonical byte replacement cannot reset captured spending or review history."""

import pytest

from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.template_review import record_review
from tests.templates.pipeline_fixtures import NOW, source_draft
from tests.templates.test_semantic_admission import proposed, review_attempt
from tests.templates.storage_fixtures import workspace


@pytest.mark.parametrize('tamper', ['cap', 'expiry', 'slot', 'state', 'usage', 'raw_return', 'input', 'receipt', 'release'])
def test_save_rejects_rewriting_retained_operation_authority_and_evidence(tmp_path, tamper):
    operation, facts, proposal, package, source = proposed()
    operation, attempt, _, _ = review_attempt(operation, proposal, package, source)
    operation, _ = record_review(operation, attempt, [source], NOW)
    before = source_draft(operation, facts)
    store = RichProjectStore(tmp_path)
    originals = {(before.project_id, key): raw for key, raw in workspace()[1].items()}
    store.save(before, originals, {})
    path = store.projects / before.project_id / 'workspace.json'
    raw = path.read_bytes()
    after = before.model_copy(deep=True)
    after.project_revision += 1
    changed = after.pre_draft.template_operations[0]
    if tamper == 'cap':
        changed.capture.policy.call_cap += 1
    elif tamper == 'expiry':
        changed.expires_at = '2026-10-21T01:00:00+00:00'
    elif tamper == 'slot':
        changed.attempts[-1].slot = 'initial'
    elif tamper == 'state':
        changed.attempts[-1].state = 'reserved'
    elif tamper == 'usage':
        changed.attempts[-1].usage.input_tokens = None
    elif tamper == 'raw_return':
        changed.attempts[-1].raw_return = '{}'
    elif tamper == 'input':
        changed.task_inputs[0].value['sources'] = []
    elif tamper == 'receipt':
        changed.receipts[0].reply.results[0].reason = 'A different historical review'
    else:
        changed.attempts[-1].state = 'released'
    with pytest.raises(ProjectStoreFailure):
        store.save(after, originals, {})
    assert path.read_bytes() == raw
    assert RichProjectStore(tmp_path).read_committed(before.project_id)[0] == before
