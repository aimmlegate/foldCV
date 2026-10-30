"""Deterministic fixtures for the application test package."""

import pytest

from packages.resume_core.project_limits import apply_preferences
from tests.support.foundation import FrozenClock, isolated_root, seeded_random


@pytest.fixture(autouse=True)
def default_settings_limits():
    # Settings limits are process-wide; a test that saves them must not leak into the next one.
    yield
    apply_preferences(None)


@pytest.fixture(autouse=True)
def free_inference_permit():
    # The permit is process-wide too; an import keeps it while an attempt's cleanup is unproven, which must not
    # hold the next test.
    yield
    from resume_api.inference_admission import INFERENCE
    with INFERENCE.condition:
        INFERENCE.shared, INFERENCE.exclusive, INFERENCE.blocked = 0, False, False
        INFERENCE.reservations.clear()
        INFERENCE._notify()


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def temp_root(tmp_path):
    return isolated_root(tmp_path)


@pytest.fixture
def fixture_random():
    return seeded_random()
