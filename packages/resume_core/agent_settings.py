"""Independent assistant preference, with explicit catalog choice and revision checks."""

from pathlib import Path

from pydantic import ValidationError

from .assistant_store import AgentFailure
from .models.agent import AgentSettings, AgentSettingsRequest, wire_bytes
from .reasoning import ModelReasoning
from .project_store import owned_file, strict_json
from .storage import StorageFailure, atomic_write, locked_root


class AgentSettingsStore:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "assistant-settings.json"

    def _read(self) -> AgentSettings:
        if not self.path.exists() and not self.path.is_symlink():
            return AgentSettings(schemaVersion=1, revision=1, enabled=True, selectedAgentModel=None)
        try:
            owned_file(self.path, 4096)
            with self.path.open("rb") as stream:
                raw = stream.read(4097)
            if len(raw) > 4096:
                raise ValueError("oversized settings")
            return AgentSettings.model_validate(strict_json(raw))
        except (StorageFailure, OSError, ValueError, ValidationError):
            raise AgentFailure("AGENT_SETTINGS_CORRUPT") from None

    def load(self) -> AgentSettings:
        try:
            with locked_root(self.root, ".assistant-settings.lock"):
                return self._read()
        except (StorageFailure, OSError):
            raise AgentFailure("AGENT_SETTINGS_CORRUPT") from None

    def save(self, request: AgentSettingsRequest, catalog: tuple[str, ...] | None,
             reasoning: dict[str, ModelReasoning] | None = None) -> AgentSettings:
        try:
            with locked_root(self.root, ".assistant-settings.lock"):
                current = self._read()
                if request.expected_revision != current.revision:
                    raise AgentFailure("AGENT_SETTINGS_CONFLICT")
                model, effort = request.selected_agent_model, request.reasoning_effort
                if model is not None and model != current.selected_agent_model:
                    if catalog is None:
                        raise AgentFailure("AGENT_CONNECTION_UNAVAILABLE")
                    if model not in catalog:
                        raise AgentFailure("AGENT_MODEL_UNAVAILABLE")
                if effort is not None and (model, effort) != (current.selected_agent_model, current.reasoning_effort):
                    metadata = (reasoning or {}).get(model) if model is not None else None
                    if catalog is None:
                        raise AgentFailure("AGENT_CONNECTION_UNAVAILABLE")
                    if metadata is None or effort not in metadata.supported:
                        raise AgentFailure("AGENT_MODEL_INCOMPATIBLE")
                result = AgentSettings(schemaVersion=1, revision=current.revision + 1,
                    enabled=request.enabled, selectedAgentModel=model, reasoningEffort=effort)
                atomic_write(self.path, wire_bytes(result))
                return result
        except (StorageFailure, OSError):
            raise AgentFailure("AGENT_SETTINGS_SAVE_FAILED") from None

    def restore_model(self, model: str | None, effort: str | None = None) -> AgentSettings:
        """A provider switch restores that provider's assistant model and effort; the next run checks them
        against the catalog."""
        try:
            with locked_root(self.root, ".assistant-settings.lock"):
                current = self._read()
                if (current.selected_agent_model, current.reasoning_effort) == (model, effort):
                    return current
                result = AgentSettings(schemaVersion=1, revision=current.revision + 1,
                    enabled=current.enabled, selectedAgentModel=model, reasoningEffort=effort)
                atomic_write(self.path, wire_bytes(result))
                return result
        except (StorageFailure, OSError):
            raise AgentFailure("AGENT_SETTINGS_SAVE_FAILED") from None
