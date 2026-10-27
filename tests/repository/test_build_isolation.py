"""Builds get the shared committed object and must not change it; a refused commit changes neither memory nor file."""

import pytest

from packages.resume_core.project_repository import RepositoryFailure
from tests.repository.support import PROJECT, repository, text_of, typing


def test_a_build_that_changes_the_committed_object_fails_under_verification(tmp_path, monkeypatch):
    monkeypatch.setenv('FOLDCV_VERIFY', '1')
    repo = repository(tmp_path)
    raw = (tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes()
    def mutating(workspace):
        workspace.title = 'Changed in place'
        return typing('Text', identifier='edit-1')(workspace)
    with pytest.raises(RuntimeError, match='changed the committed workspace'):
        repo.mutate(PROJECT, base_revision=1, client_mutation_id='edit-1', request_sha256='a' * 64, action_id='edit-1',
            kind='edit', build=mutating)
    assert (tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes() == raw


def test_a_validator_failure_leaves_memory_and_file_unchanged(tmp_path):
    repo = repository(tmp_path)
    committed = repo.read(PROJECT)
    raw = (tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes()
    def invalid(workspace):
        after = typing('Text', identifier='edit-1')(workspace)
        after.project.document.regions[2].blocks.append(after.project.document.regions[2].blocks[0].model_copy(deep=True))
        return after
    with pytest.raises(RepositoryFailure):
        repo.mutate(PROJECT, base_revision=1, client_mutation_id='edit-1', request_sha256='a' * 64, action_id='edit-1',
            kind='edit', build=invalid)
    assert repo.read(PROJECT) is committed and text_of(committed) == 'Shared title'
    assert (tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes() == raw
    assert 'edit-1' not in repo.open(PROJECT).replays


def test_a_build_without_a_change_writes_nothing_and_keeps_the_id_free(tmp_path):
    repo = repository(tmp_path)
    raw = (tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes()
    outcome = repo.mutate(PROJECT, base_revision=1, client_mutation_id='edit-1', request_sha256='a' * 64, action_id='edit-1',
        kind='edit', build=lambda _workspace: None)
    assert outcome.revision == 1 and not outcome.replayed and 'edit-1' not in repo.open(PROJECT).replays
    assert (tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes() == raw
