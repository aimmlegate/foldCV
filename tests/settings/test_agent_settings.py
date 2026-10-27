"""The assistant settings file: own revision and model choice, independent of processing preferences."""

from concurrent.futures import ThreadPoolExecutor
import stat

import pytest

from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.assistant_store import AgentFailure
from packages.resume_core.models.agent import AgentSettingsRequest
from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.storage import atomic_write


def test_settings_choices_are_independent_revisioned_and_retained_without_catalog(tmp_path):
    processing = PreferencesStore(tmp_path)
    processing.select_model("processing-model")
    original = processing.path.read_bytes()
    settings = AgentSettingsStore(tmp_path)
    assert settings.load().selected_agent_model is None and settings.load().enabled
    assert not settings.path.exists()
    request = AgentSettingsRequest(expectedRevision=1, enabled=True, selectedAgentModel="assistant-model")
    saved = settings.save(request, ("assistant-model", "processing-model"))
    assert saved.revision == 2 and saved.selected_agent_model == "assistant-model"
    assert processing.path.read_bytes() == original
    assert AgentSettingsStore(tmp_path).load() == saved
    with pytest.raises(AgentFailure, match="AGENT_SETTINGS_CONFLICT"):
        settings.save(request, None)
    assert settings.save(AgentSettingsRequest(expectedRevision=2, enabled=False,
        selectedAgentModel="assistant-model"), None).selected_agent_model == "assistant-model"
    assert not AgentSettingsStore(tmp_path).load().enabled
    processing.select_model("other-processing")
    assert settings.load().selected_agent_model == "assistant-model"
    with pytest.raises(AgentFailure, match="AGENT_MODEL_UNAVAILABLE"):
        settings.save(AgentSettingsRequest(expectedRevision=3, enabled=True, selectedAgentModel="removed"), ())
    with pytest.raises(AgentFailure, match="AGENT_CONNECTION_UNAVAILABLE"):
        settings.save(AgentSettingsRequest(expectedRevision=3, enabled=True, selectedAgentModel="new"), None)
    assert settings.load().revision == 3


def test_concurrent_settings_writes_conflict_and_damage_does_not_reset(tmp_path):
    def save(model):
        try:
            return AgentSettingsStore(tmp_path).save(AgentSettingsRequest(expectedRevision=1,
                enabled=True, selectedAgentModel=model), ("a", "b")).selected_agent_model
        except AgentFailure as error:
            return error.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, ["a", "b"]))
    assert results.count("AGENT_SETTINGS_CONFLICT") == 1
    store = AgentSettingsStore(tmp_path)
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    raw = b'{"schemaVersion":1,"schemaVersion":1}'
    atomic_write(store.path, raw)
    with pytest.raises(AgentFailure, match="AGENT_SETTINGS_CORRUPT"):
        store.load()
    assert store.path.read_bytes() == raw
