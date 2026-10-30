"""One editor token per open project: open always grants a fresh one; replaced and unknown tokens differ (2.5)."""

import pytest

from packages.resume_core.project_repository import ProjectRepository, RepositoryFailure
from tests.repository.support import PROJECT, repository


def code(session, token):
    with pytest.raises(RepositoryFailure) as refused:
        session.require_editor(token)
    return refused.value.code


def test_open_grants_a_fresh_token_and_the_previous_one_is_replaced(tmp_path):
    session = repository(tmp_path).open(PROJECT)
    first = session.open_editor()
    session.require_editor(first)
    second = session.open_editor()
    session.require_editor(second)
    assert second != first and code(session, first) == 'EDITOR_REPLACED'


def test_unknown_missing_and_restarted_tokens_ask_the_page_to_reopen(tmp_path):
    repo = repository(tmp_path)
    session = repo.open(PROJECT)
    token = session.open_editor()
    assert code(session, 'editor_forged') == 'EDITOR_TOKEN_UNKNOWN' and code(session, None) == 'EDITOR_TOKEN_UNKNOWN'
    restarted = ProjectRepository(tmp_path / 'data').open(PROJECT)
    assert code(restarted, token) == 'EDITOR_TOKEN_UNKNOWN'


def test_only_a_bounded_number_of_replaced_tokens_is_remembered(tmp_path):
    session = repository(tmp_path).open(PROJECT)
    tokens = [session.open_editor() for _ in range(20)]
    assert code(session, tokens[-2]) == 'EDITOR_REPLACED' and code(session, tokens[0]) == 'EDITOR_TOKEN_UNKNOWN'


@pytest.mark.parametrize('token', ['токен', 'editor_\ud800'])
def test_a_token_that_is_not_ascii_is_unknown_and_never_a_crash(tmp_path, token):
    session = repository(tmp_path).open(PROJECT)
    first = session.open_editor()
    session.open_editor()
    assert code(session, token) == 'EDITOR_TOKEN_UNKNOWN' and code(session, first) == 'EDITOR_REPLACED'
