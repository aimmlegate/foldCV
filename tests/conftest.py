"""Deterministic fixtures for the application test package."""

import pytest

from tests.support.foundation import FrozenClock, isolated_root, seeded_random


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def temp_root(tmp_path):
    return isolated_root(tmp_path)


@pytest.fixture
def fixture_random():
    return seeded_random()
