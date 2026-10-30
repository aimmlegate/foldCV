"""Stale requests are refused by revision; a retried id is applied once, also after a restart (G2)."""

import hashlib
import json

import pytest

from packages.resume_core import project_repository
from packages.resume_core.project_repository import ProjectRepository, RepositoryFailure
from tests.repository.support import PROJECT, edit, repository, text_of, typing


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


DETAILS = {'created_ids': {'split': {'slot': 'identifier-new'}}, 'created_blocks': {'split': ['block-new']},
    'changed_block_ids': ['block-old', 'block-new']}


def split_like(repo, details=DETAILS):
    """An edit whose reply names what it created, as a split does."""
    return repo.mutate(PROJECT, base_revision=repo.read(PROJECT).project_revision, client_mutation_id='edit-1',
        request_sha256='a' * 64, action_id='edit-1', kind='edit',
        build=lambda workspace: (typing('New', identifier='edit-1')(workspace), details))


def test_a_retry_gets_the_same_reply_after_a_restart_and_after_an_eviction(tmp_path):
    repo = repository(tmp_path)
    first = split_like(repo)
    assert first.details == DETAILS
    restarted = split_like(ProjectRepository(tmp_path / 'data'))
    assert restarted.replayed and restarted.details == DETAILS and restarted.revision == first.revision
    repo.close(PROJECT)
    evicted = split_like(repo)
    assert evicted.replayed and evicted.details == DETAILS


def test_an_edit_that_names_no_ids_adds_nothing_to_the_replay_row_and_a_huge_one_stays_bounded(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'Plain', identifier='edit-0')
    path = tmp_path / 'data/projects' / PROJECT / 'workspace.json'
    assert set(json.loads(path.read_bytes())['mutationReplay'][-1]) == {'clientMutationId', 'requestSha256', 'resultingRevision'}
    split_like(repo, {'changed_block_ids': ['block-' + str(index) for index in range(project_repository.REPLAY_DETAIL_IDS + 1)]})
    assert 'changedBlockIds' not in json.loads(path.read_bytes())['mutationReplay'][-1]
