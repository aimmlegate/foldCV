"""Startup freezes what it allocated and raises the GC thresholds (D108); the launcher calls it after create_app."""

import gc
import inspect

from resume_api import launcher
from resume_api.lifecycle import GC_THRESHOLD, tune_garbage_collector


def test_tuning_changes_threshold_and_freeze_count_and_can_be_restored():
    before_threshold, before_frozen = gc.get_threshold(), gc.get_freeze_count()
    keep = [object() for _ in range(1000)]
    try:
        previous = tune_garbage_collector()
        assert previous == before_threshold
        assert gc.get_threshold() == GC_THRESHOLD and gc.get_freeze_count() > before_frozen
    finally:
        gc.unfreeze()
        gc.set_threshold(*before_threshold)
    assert gc.get_threshold() == before_threshold and keep


def test_the_launcher_tunes_after_the_app_exists():
    source = inspect.getsource(launcher.launch)
    assert 0 < source.index('create_app(') < source.index('tune_garbage_collector()')
