"""Bounded private drafts under the existing assistant/lifecycle lock order."""

from datetime import datetime, timedelta
import json

from .agent_store import AgentFailure, digest, run_in
from .models.assistant_proposals import AssistantStoredProposalV1
from .project_store import owned_file, strict_json
from .storage import StorageFailure, atomic_write, private_directory

VERSION_BYTES = 2 * 1024 * 1024
PROJECT_BYTES = 10 * 1024 * 1024
APPLICATION_BYTES = 100 * 1024 * 1024
VERSION_COUNT = 20
RETENTION_DAYS = 7
CONTROL_RESERVE_BYTES = 32 * 1024
POLICY_REVISION = 1
PROTECTED = {"applying", "outcome_unknown"}
TRANSITIONS = {
    "building": {"ready", "incomplete", "invalid", "cancelled"},
    "ready": {"applying", "stale", "discarded", "expired"},
    "incomplete": {"discarded", "expired"}, "stale": {"discarded", "expired"},
    "applying": {"applied", "failed_before_commit", "outcome_unknown"},
    "failed_before_commit": {"ready", "discarded"},
    "outcome_unknown": {"applied", "failed_before_commit"},
}


def stored_proposal(payload):
    if not isinstance(payload, dict):
        raise ValueError("proposal payload must be an object")
    if payload.get("recordKind") == "action_v1":
        from .models.assistant_actions import AssistantStoredActionV1
        return AssistantStoredActionV1.model_validate(payload)
    return AssistantStoredProposalV1.model_validate(payload)


def encoded(value):
    payload = value.model_dump(mode="json", by_alias=True)
    return json.dumps({"payload": payload, "sha256": digest(payload)}, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()



def capacity_failure(code, reason):
    error = AgentFailure(code)
    error.capacity_reason = reason
    return error


def minimum_storage_reason(workspace):
    # Even an empty rewritten document must retain the authored baseline and its resources.
    if workspace.project is None:
        return None
    baseline = len(json.dumps(workspace.model_dump(mode="json", by_alias=True), ensure_ascii=False, separators=(",", ":")).encode())
    resources = len(json.dumps({"sources": [source.model_dump(mode="json", by_alias=True) for source in workspace.project.sources],
        "assets": [asset.model_dump(mode="json", by_alias=True) for asset in workspace.project.assets],
        "template": workspace.project.template.model_dump(mode="json", by_alias=True)}, ensure_ascii=False, separators=(",", ":")).encode())
    if baseline + resources + CONTROL_RESERVE_BYTES > VERSION_BYTES:
        return "Текущий документ и обязательные ресурсы не помещаются в лимит хранения варианта. Доступны проверки, текстовый черновик в чате и существующая правка выделенного текста. Меньшая область не убирает размер тех же ресурсов."
    return None


def fit_control_capacity(value, *, allocate=False):
    value.control_padding = ""
    active = value.proposal.state in {"building", "ready", "incomplete", "applying", "outcome_unknown", "failed_before_commit"}
    if active and not value.compacted:
        if allocate or value.control_capacity == 0:
            # Physical padding reserves exact encoded space for approval, revocation and outcomes.
            value.control_capacity = len(encoded(value)) + CONTROL_RESERVE_BYTES
            value.control_capacity = len(encoded(value)) + CONTROL_RESERVE_BYTES
        remaining = value.control_capacity - len(encoded(value))
        if not 0 <= remaining <= value.control_capacity:
            raise capacity_failure("AGENT_EDIT_LIMIT", "Не осталось зарезервированного места для результата. Черновик сохранён; подготовьте меньший вариант.")
        value.control_padding = "_" * remaining
    else:
        value.control_capacity = 0
    if len(encoded(value)) > VERSION_BYTES:
        raise capacity_failure("AGENT_EDIT_LIMIT", "Вариант вместе с резервом результата превышает 2 МиБ. Предыдущий черновик сохранён; выберите меньшую задачу или существующую правку выделенного текста.")
    return value


def at(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def expiry(created):
    return (at(created) + timedelta(days=RETENTION_DAYS)).isoformat()


def reviewed_value(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {key: reviewed_value(part) for key, part in value.items() if key != "revision"}
    if isinstance(value, list):
        return [reviewed_value(part) for part in value]
    return value


def content_digest(workspace):
    project = workspace.project
    return digest(reviewed_value({"format": "assistant-content-v1", "document": project.document,
        "facts": project.facts, "assets": project.assets, "template": project.template, "sources": project.sources}))


def proposal_before_digest(value, workspace, *, archived=False):
    if getattr(value, "record_kind", None) == "action_v1":
        from .assistant_actions import action_baseline_digest
        return action_baseline_digest(workspace, archived)
    return content_digest(workspace)


class AssistantProposals:
    def __init__(self, agent_store):
        self.agent = agent_store
        self.root = agent_store.assistant / "proposals"

    def directory(self, project):
        return self.root / project

    def _read(self, path):
        try:
            owned_file(path, VERSION_BYTES)
            envelope = strict_json(path.read_bytes())
            if set(envelope) != {"payload", "sha256"} or digest(envelope["payload"]) != envelope["sha256"]:
                raise ValueError("changed proposal payload")
            value = stored_proposal(envelope["payload"])
            if value.proposal.state == "ready" and value.policy_revision != POLICY_REVISION:
                value.proposal.state = "stale"
                value.proposal.reason = "Вариант подготовлен до текущих проверок охвата и сохранности. Подготовьте новую версию для просмотра."
                atomic_write(path, encoded(value))
            return value
        except (StorageFailure, OSError, ValueError, RecursionError):
            raise AgentFailure("AGENT_STORE_CORRUPT") from None

    def _items(self, project):
        directory = self.directory(project)
        if self.root.is_symlink() or directory.is_symlink():
            raise AgentFailure("AGENT_STORE_CORRUPT")
        if not directory.exists():
            return []
        if len(list(directory.iterdir())) > VERSION_COUNT:
            raise AgentFailure("AGENT_PROJECT_FULL")
        result = []
        for path in sorted(directory.iterdir()):
            if path.suffix != ".json":
                raise AgentFailure("AGENT_STORE_CORRUPT")
            value = self._read(path)
            if value.proposal.project_id != project or path.name != self.filename(value):
                raise AgentFailure("AGENT_STORE_CORRUPT")
            result.append(value)
        return result

    @staticmethod
    def filename(value):
        return f"{value.proposal.id}-{value.proposal.version}.json"

    def _expire(self, project):
        values = self._items(project)
        for value in values:
            proposal = value.proposal
            if at(self.agent.clock()) >= at(proposal.expires_at) and proposal.state not in PROTECTED | {"expired"}:
                proposal.state, proposal.reason = "expired", "Срок хранения варианта истёк. Подготовьте новый вариант."
                value.baseline = value.candidate = value.batch = None
                value.history = None
                value.read_groups = []
                fit_control_capacity(value)
                value.operations, value.snapshot_ids, value.dependencies, value.unchanged = [], [], [], []
                if hasattr(value, "action"):
                    value.action = None
                proposal.operation_count, proposal.coverage, proposal.changes = 0, [], []
                atomic_write(self.directory(project) / self.filename(value), encoded(value))
        return values

    def list(self, project):
        with self.agent._guard(project):
            return self._expire(project)

    def get(self, project, proposal_id, version):
        values = self.list(project)
        value = next((item for item in values if item.proposal.id == proposal_id and item.proposal.version == version), None)
        if value is None:
            raise AgentFailure("ASSISTANT_PROPOSAL_MISSING")
        return value

    def compact_applied(self, project, proposal_id, version, *, receipt=None, settle=False):
        with self.agent._guard(project) as directory:
            value = next((item for item in self._items(project) if (item.proposal.id, item.proposal.version) == (proposal_id, version)), None)
            if value is None or value.compacted:
                return
            if value.approval is None or (value.proposal.state != "applied"
                    and not (settle and value.proposal.state in PROTECTED)):
                raise AgentFailure("AGENT_TOOL_DENIED")
            if receipt is None:
                state = self.agent._read(project, directory)
                _, _, journal = run_in(state, value.proposal.origin_run_id)
                proof = next((part for part in journal.batches if part.key == value.approval.batch_id), None)
                receipt = proof.receipt if proof else None
            if (receipt is None or not receipt.durable or (receipt.run_id, receipt.batch_id, receipt.request_sha256) !=
                    (value.proposal.origin_run_id, value.approval.batch_id, value.approval.request_sha256)):
                raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
            value.proposal.state, value.proposal.reason = "applied", "Показанные изменения сохранены."
            value.approval.phase = "receipt_stored"
            value.baseline = value.candidate = value.batch = None
            value.history = None
            value.read_groups = []
            value.operations, value.snapshot_ids, value.dependencies, value.unchanged = [], [], [], []
            value.compacted = True
            AssistantStoredProposalV1.model_validate(value.model_dump(by_alias=True))
            fit_control_capacity(value)
            atomic_write(self.directory(project) / self.filename(value), encoded(value))

    def update(self, project, transform):
        with self.agent._guard(project):
            values = self._expire(project)
            previous = {self.filename(value): value.model_copy(deep=True) for value in values}
            for value in list(values):
                if value.proposal.state == "expired":
                    (self.directory(project) / self.filename(value)).unlink()
                    values.remove(value)
            for directory in self.root.iterdir() if self.root.exists() else []:
                if directory.name == project:
                    continue
                if directory.is_symlink() or not directory.is_dir():
                    raise AgentFailure("AGENT_STORE_CORRUPT")
                for old in self._expire(directory.name):
                    if old.proposal.state == "expired":
                        (directory / self.filename(old)).unlink()
            value = transform(values)
            checked = stored_proposal(value.model_dump(by_alias=True))
            path = self.directory(project) / self.filename(checked)
            prior = previous.get(path.name)
            if checked.proposal.project_id != project:
                raise AgentFailure("AGENT_SCOPE_INVALID")
            def frozen(item):
                return item.model_dump(mode="json", by_alias=True,
                    exclude={"proposal": {"state", "reason"}, "approval": True, "revoked_acceptances": True,
                        "control_capacity": True, "control_padding": True})
            if prior is not None:
                old_state, new_state = prior.proposal.state, checked.proposal.state
                if new_state != old_state and new_state not in TRANSITIONS.get(old_state, set()):
                    raise AgentFailure("AGENT_TOOL_DENIED")
                if old_state != "building" and frozen(prior) != frozen(checked):
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            allocate = prior is None or prior.proposal.state == "building" and frozen(prior) != frozen(checked)
            fit_control_capacity(checked, allocate=allocate)
            raw = encoded(checked)
            if len(raw) > VERSION_BYTES:
                raise capacity_failure("AGENT_EDIT_LIMIT", "Вариант превышает 2 МиБ; предыдущий черновик сохранён.")
            existing = path.exists()
            if not existing and len(values) >= VERSION_COUNT:
                raise capacity_failure("AGENT_PROJECT_FULL", "Сохранено 20 версий. Предыдущие варианты доступны; освободите место перед новой подготовкой.")
            if self.root.is_symlink():
                raise AgentFailure("AGENT_STORE_CORRUPT")
            total = project_bytes = 0
            for directory in self.root.iterdir() if self.root.exists() else []:
                if directory.is_symlink() or not directory.is_dir():
                    raise AgentFailure("AGENT_STORE_CORRUPT")
                for item in directory.iterdir():
                    owned_file(item, VERSION_BYTES)
                    size = item.stat().st_size if item != path else 0
                    total += size
                    if directory == self.directory(project):
                        project_bytes += size
            if total + len(raw) > APPLICATION_BYTES or project_bytes + len(raw) > PROJECT_BYTES:
                raise capacity_failure("AGENT_PROJECT_FULL", "Достигнут лимит хранения: 10 МиБ на проект или 100 МиБ на приложение. Предыдущий черновик сохранён; освободите место перед новой подготовкой.")
            private_directory(path.parent)
            atomic_write(path, raw)
            return checked

    def compact_action(self, project, proposal_id, version, operation):
        with self.agent._guard(project):
            value = self._read(self.directory(project) / f"{proposal_id}-{version}.json")
            if value.compacted:
                return
            if (getattr(value, "record_kind", None) != "action_v1" or value.approval is None
                    or not operation.durable or operation.status != "completed"
                    or (operation.id, operation.project_id, operation.run_id) !=
                        (value.approval.batch_id, project, value.proposal.origin_run_id)):
                raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
            value.proposal.state, value.proposal.reason = "applied", "Показанное действие выполнено."
            value.approval.phase = "receipt_stored"
            value.action = value.baseline = value.candidate = value.batch = value.history = None
            value.operations, value.snapshot_ids, value.dependencies, value.unchanged, value.read_groups = [], [], [], [], []
            value.compacted = True
            fit_control_capacity(value)
            stored_proposal(value.model_dump(by_alias=True))
            atomic_write(self.directory(project) / self.filename(value), encoded(value))

    def remove_noop(self, project, proposal_id, version, checksum):
        with self.agent._guard(project):
            value = self._read(self.directory(project) / f"{proposal_id}-{version}.json")
            expected = digest([proposal_id, version, value.proposal.content_sha256, "no_change"])
            if not value.no_change or value.proposal.state != "invalid" or expected != checksum:
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            (self.directory(project) / self.filename(value)).unlink()

    def recover(self):
        errors = {}
        if not self.root.exists():
            return errors
        if self.root.is_symlink() or not self.root.is_dir():
            raise AgentFailure("AGENT_STORE_CORRUPT")
        for path in self.root.iterdir():
            try:
                for item in self.list(path.name):
                    if item.proposal.state == "building":
                        self.finish(path.name, item.proposal.origin_run_id)
            except AgentFailure as error:
                if error.code not in {"AGENT_NOT_FOUND", "AGENT_PROJECT_DELETED"}:
                    errors[path.name] = error.code
        return errors

    def finish(self, project, run_id, *, cancelled=False):
        for item in self.list(project):
            if item.proposal.origin_run_id != run_id or item.proposal.state not in {"building", "ready"}:
                continue
            def end(values):
                current = next(value for value in values if value.proposal.id == item.proposal.id and value.proposal.version == item.proposal.version)
                if cancelled:
                    current.proposal.state = "discarded" if current.proposal.state == "ready" else "cancelled"
                    current.proposal.reason = "Задача остановлена. Этот вариант нельзя применить."
                elif current.proposal.state == "building":
                    current.proposal.state = "incomplete"
                    current.proposal.reason = current.proposal.reason if current.proposal.reason and current.proposal.reason.startswith("Лимит:") else "Черновик сохранён. Подготовка не завершена; применение недоступно."
                return current
            self.update(project, end)
