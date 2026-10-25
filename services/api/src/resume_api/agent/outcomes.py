"""Durable no-op results reuse the origin journal, never model prose or history."""

from packages.resume_core.agent_store import AgentFailure, digest, run_in
from packages.resume_core.models.agent import AgentBatchJournal, AgentPrepareResult, TERMINAL_RUNS
from packages.resume_core.models.assistant_continuation import AssistantRunOutcomeV1

from .approval_journal import origin_journal, journal_for_run


def noop_identity(value):
    checksum = digest([value.proposal.id, value.proposal.version, value.proposal.content_sha256, 'no_change'])
    return 'assistant_no_change_' + checksum[:32], checksum


def record_noop(service, value):
    if not value.no_change:
        return
    key, checksum = noop_identity(value)
    def record(state):
        journal = run_in(state, value.proposal.origin_run_id)[2]
        old = next((item for item in journal.batches if item.key == key), None)
        if old is not None:
            if old.payload_sha256 != checksum or old.batch is not None or old.result.disposition != 'no_change':
                raise AgentFailure('AGENT_IDEMPOTENCY_CONFLICT')
            return
        journal.batches.append(AgentBatchJournal(key=key, payloadSha256=checksum,
            result=AgentPrepareResult(disposition='no_change', batchId=None, affected=[], affectedCount=0,
                preview='Изменений нет. Документ и история не изменены.'), batch=None, receipt=None))
    origin_journal(service, value).update(value.proposal.project_id, record)


def retire_noops(service, project, *, run_id=None):
    for value in service.proposals.list(project):
        if not value.no_change or run_id is not None and value.proposal.origin_run_id != run_id:
            continue
        try:
            store = origin_journal(service, value)
            _, run, journal = run_in(store.load(project), value.proposal.origin_run_id)
        except AgentFailure as error:
            if error.code == 'AGENT_NOT_FOUND':
                continue
            raise
        key, checksum = noop_identity(value)
        if run.state not in TERMINAL_RUNS:
            continue
        proof = next((item for item in journal.batches if item.key == key), None)
        if (proof is None or proof.payload_sha256 != checksum or proof.batch is not None
                or proof.receipt is not None or proof.result.disposition != 'no_change'):
            continue
        service.proposals.remove_noop(project, value.proposal.id, value.proposal.version, checksum)


def outcome(service, project, run_id):
    store = journal_for_run(service, project, run_id)
    _, run, journal = run_in(store.load(project), run_id)
    values = [value for value in service.proposals.list(project) if value.proposal.origin_run_id == run_id]
    state, durable, reason = 'none', False, 'Задача не сохраняла изменения документа.'
    if any(item.receipt is not None and item.receipt.durable for item in journal.batches):
        state, durable, reason = 'applied', True, 'Изменения сохранены по подтверждённой квитанции.'
    elif any(item.receipt is not None and item.receipt.disposition == 'outcome_unknown' for item in journal.batches):
        state, reason = 'outcome_unknown', 'Исходное сохранение проверяется. Не повторяйте применение.'
    elif any(item.key.startswith('assistant_no_change_') and item.result.disposition == 'no_change'
            and item.batch is None for item in journal.batches):
        state, reason = 'no_change', 'Изменений нет. Документ и история не изменены.'
    elif values:
        proposal = max(values, key=lambda value: value.proposal.version).proposal
        state = {'ready': 'draft_ready', 'building': 'incomplete', 'incomplete': 'incomplete',
            'outcome_unknown': 'outcome_unknown', 'applying': 'outcome_unknown', 'applied': 'applied',
            'stale': 'stale'}.get(proposal.state, 'failed')
        durable = state == 'applied'
        reason = proposal.reason or 'Черновик сохранён для просмотра; применение требует отдельного действия.'
    elif run.error is not None:
        state, reason = 'failed', 'Задача не завершена. Сохранённые черновики доступны в обзоре вариантов.'
    if run.state in TERMINAL_RUNS:
        retire_noops(service, project, run_id=run_id)
    return AssistantRunOutcomeV1(runId=run_id, outcome=state, durable=durable, reason=reason)
