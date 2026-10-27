"""Whole-workspace commits computed outside the lock: blobs first, revision of the computation checked (G4)."""

import hashlib

import pytest

from packages.resume_core.project_repository import RepositoryFailure, blob_path
from tests.repository.support import PROJECT, edit, repository, text_of


def render_blob(raw):
    digest = hashlib.sha256(raw).hexdigest()
    return ('renders', 'render-1', raw, digest)


def test_blobs_are_written_once_and_verified_when_present(tmp_path):
    repo = repository(tmp_path)
    directory = tmp_path / 'data/projects' / PROJECT
    first = repo.read(PROJECT).model_copy(deep=True)
    first.title = 'With render'
    repo.replace(PROJECT, base_revision=1, workspace=first, blobs=[render_blob(b'docx bytes')])
    path = blob_path(directory, 'renders', 'render-1')
    stamp = path.stat().st_mtime_ns
    second = repo.read(PROJECT).model_copy(deep=True)
    second.title = 'Again'
    repo.replace(PROJECT, base_revision=2, workspace=second, blobs=[render_blob(b'docx bytes')])
    assert path.stat().st_mtime_ns == stamp and path.read_bytes() == b'docx bytes'
    path.chmod(0o600)
    path.write_bytes(b'tampered')
    third = repo.read(PROJECT).model_copy(deep=True)
    third.title = 'Third'
    with pytest.raises(RepositoryFailure) as refused:
        repo.replace(PROJECT, base_revision=3, workspace=third, blobs=[render_blob(b'docx bytes')])
    assert refused.value.code == 'ARTIFACT_BYTES_MISMATCH' and repo.read(PROJECT).title == 'Again'


def test_a_barrier_is_written_only_when_undoable_keys_change(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1', action='one')
    titled = repo.read(PROJECT).model_copy(deep=True)
    titled.title = 'Renamed'
    repo.replace(PROJECT, base_revision=2, workspace=titled, reason='rename')
    assert repo.open(PROJECT).journal.state()['undo']['actionId'] == 'one'
    changed = repo.read(PROJECT).model_copy(deep=True)
    changed.project.document.regions[2].blocks[1].content[0].text = 'Published'
    repo.replace(PROJECT, base_revision=3, workspace=changed, reason='import')
    assert repo.open(PROJECT).journal.state() == {'undo': None, 'redo': None}
    lines = (tmp_path / 'data/projects' / PROJECT / 'history.jsonl').read_text().splitlines()
    assert '"reason":"import"' in lines[-1] and len(lines) == 2


def test_a_workspace_computed_from_an_older_revision_is_refused(tmp_path):
    repo = repository(tmp_path)
    computed = repo.read(PROJECT).model_copy(deep=True)
    computed.title = 'From revision one'
    edit(repo, 'Manual', identifier='edit-1')
    with pytest.raises(RepositoryFailure) as refused:
        repo.replace(PROJECT, base_revision=1, workspace=computed)
    assert refused.value.code == 'REVISION_CONFLICT' and refused.value.details['revision'] == 2
    current = repo.read(PROJECT)
    assert text_of(current) == 'Manual' and current.title == 'Synthetic papers'


def test_revisions_move_forward_and_memory_matches_the_file(tmp_path):
    from packages.resume_core.project_repository import ProjectRepository
    repo = repository(tmp_path)
    computed = repo.read(PROJECT).model_copy(deep=True)
    computed.title = 'Metadata only'
    outcome = repo.replace(PROJECT, base_revision=1, workspace=computed)
    current = repo.read(PROJECT)
    assert outcome.revision == current.project_revision == 2 and current.document_revision == 1
    assert ProjectRepository(tmp_path / 'data').read(PROJECT) == current
