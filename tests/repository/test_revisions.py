"""Stale requests are refused by revision; a retried id is applied once, also after a restart (G2)."""

import hashlib
import json

import pytest

from packages.resume_core import project_repository
from packages.resume_core.project_repository import ProjectRepository, RepositoryFailure
from tests.repository.support import PROJECT, edit, repository, text_of


def test_a_stale_base_is_refused_with_the_current_revision_and_the_applied_ids(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1')
    with pytest.raises(RepositoryFailure) as refused:
        edit(repo, 'Late', identifier='edit-2', base=1)
    assert refused.value.code == 'REVISION_CONFLICT'
    assert refused.value.details == {'revision': 2, 'appliedClientMutationIds': ['edit-1']}
    assert text_of(repo.read(PROJECT)) == 'One'


def test_a_retry_returns_the_stored_outcome_and_applies_nothing(tmp_path):
    repo = repository(tmp_path)
    first = edit(repo, 'Once', identifier='edit-1')
    path = tmp_path / 'data/projects' / PROJECT / 'workspace.json'
    raw = path.read_bytes()
    retried = edit(repo, 'Once', identifier='edit-1', base=1)
    assert retried.replayed and retried.revision == first.revision == 2 and path.read_bytes() == raw


def test_a_reused_id_with_another_request_is_refused(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'Once', identifier='edit-1')
    with pytest.raises(RepositoryFailure) as refused:
        edit(repo, 'Different', identifier='edit-1', base=1)
    assert refused.value.code == 'MUTATION_ID_REUSED' and text_of(repo.read(PROJECT)) == 'Once'


def test_after_a_restart_the_retry_is_recognized_from_the_file(tmp_path):
    repo = repository(tmp_path)
    first = edit(repo, 'Once', identifier='edit-1')
    reopened = ProjectRepository(tmp_path / 'data')
    retried = reopened.mutate(PROJECT, base_revision=1, client_mutation_id='edit-1', request_sha256=first.request_sha256,
        action_id='edit-1', kind='edit', build=lambda _workspace: pytest.fail('a retry must not build'))
    assert retried.replayed and retried.revision == 2


def test_the_file_keeps_a_bounded_window_and_memory_follows_it(tmp_path, monkeypatch):
    monkeypatch.setattr(project_repository, 'REPLAY_WINDOW', 3)
    repo = repository(tmp_path)
    for index in range(5):
        edit(repo, 'Text %d' % index, identifier='edit-%d' % index)
    rows = json.loads((tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes())['mutationReplay']
    assert [row['clientMutationId'] for row in rows] == ['edit-2', 'edit-3', 'edit-4']
    assert [row['resultingRevision'] for row in rows] == [4, 5, 6]
    assert list(repo.open(PROJECT).replays) == ['edit-2', 'edit-3', 'edit-4']
    assert rows[-1]['requestSha256'] == hashlib.sha256(json.dumps(['edit-4', 'Text 4', 0], separators=(',', ':')).encode()).hexdigest()
