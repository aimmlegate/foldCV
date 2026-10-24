"""Deterministic fixtures for the application test package."""

import pytest

from packages.resume_core.project_limits import apply_preferences
from tests.support.foundation import FrozenClock, isolated_root, seeded_random


@pytest.fixture(autouse=True)
def default_settings_limits():
    # Settings limits are process-wide; a test that saves them must not leak into the next one.
    yield
    apply_preferences(None)


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def temp_root(tmp_path):
    return isolated_root(tmp_path)


@pytest.fixture
def fixture_random():
    return seeded_random()
