"""What a running import reports beside its saved discoveries: its steps, the recent model activity and whether it went
quiet for longer than any step may. Everything comes from the operation record and the task's own times; the client
shows it as given."""

from __future__ import annotations

from datetime import datetime, timezone

from ..importer.template_pipeline import RETRY_SECONDS

# The CLI streams nothing before its reply, so one call may stay silent for its whole limit; this covers process
# cleanup and the work between calls (task inputs, parsing, saving).
QUIET_GRACE_SECONDS = 60
# Before admission only the capture and the operation's first save run.
STARTING_QUIET_SECONDS = 2 * QUIET_GRACE_SECONDS
EVENTS_SHOWN = 6

OPERATION_TITLES = {'partition_employment': 'Опыт по проектам', 'select_role_branch': 'Тип роли',
    'assign_skills': 'Навыки по группам', 'format_period': 'Периоды работы',
    'preserve_stated_text': 'Исходные формулировки'}
UNTITLED_BLOCK = 'Шапка'
CALLED = {'initial': 'Извлекаем данные', 'review': 'Проверяем результат',
    'primary_repair': 'Исправляем ответ', 'fallback_repair': 'Исправляем ответ резервной моделью',
    'replacement_review': 'Проверяем исправление'}
RETURNED = {'completed': 'Ответ получен', 'timed_out': 'Нет ответа в срок',
    'invalid_payload': 'Ответ в неверном формате', 'refused': 'Модель отказалась отвечать',
    'incomplete': 'Ответ неполный', 'cancelled': 'Остановлено', 'transport_failure': 'Сбой связи с моделью',
    'cleanup_failure': 'Процесс модели не завершился'}


def moment(value):
    """An ISO time as an aware datetime; None for a missing or unreadable value."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def whole_import_seconds(policy):
    """A full run under its captured limits: processing, cleanup, publication and the grace."""
    return policy.processing_seconds + policy.cleanup_seconds + policy.finalization_seconds + QUIET_GRACE_SECONDS


def quiet_limit(phase, policy):
    """The longest silence a healthy import has in this phase."""
    if policy is None or phase == 'starting':
        return STARTING_QUIET_SECONDS
    if phase == 'queued':
        # A whole import (or an assistant turn) may run ahead of this one.
        return whole_import_seconds(policy)
    if phase == 'publication':
        return policy.finalization_seconds + QUIET_GRACE_SECONDS
    return min(policy.processing_seconds, RETRY_SECONDS + policy.cleanup_seconds + QUIET_GRACE_SECONDS)


def phase_of(stage, operation):
    if stage in {'starting', 'queued'}:
        return stage
    return 'publication' if operation is not None and operation.state == 'finalizing' else 'processing'


def step_titles(package):
    definition = package.definition
    locale = definition.template.default_locale
    titles = {block.id: block.view.title.get(locale) or next(iter(block.view.title.values()), '') or UNTITLED_BLOCK
        for block in definition.blocks}
    titles.update({value.id: OPERATION_TITLES.get(value.kind, value.id) for value in definition.operations})
    return titles


def activity(operation, titles):
    """Model calls and returns, then publication, newest first, as short Russian lines; and the latest model event."""
    tasks = {task.id: task.block_id for task in operation.tasks}
    events = []
    for attempt in operation.attempts:
        title = '«' + titles.get(tasks.get(attempt.task_id), attempt.task_id) + '»'
        called = moment(attempt.dispatched_at)
        if called is not None:
            events.append((called, CALLED.get(attempt.slot, CALLED['initial']) + ': ' + title))
        returned = moment(attempt.returned_at)
        if returned is not None:
            events.append((returned, RETURNED.get(attempt.outcome, 'Вызов завершён') + ': ' + title))
    model_at = latest([at for at, _text in events])
    started = moment(operation.finalization.started_at) if operation.finalization is not None else None
    if started is not None:
        events.append((started, 'Собираем документ'))
    events.sort(key=lambda item: item[0], reverse=True)
    return events, model_at


def latest(values):
    known = [value for value in values if value is not None]
    return max(known) if known else None


def import_progress(operation, package, *, stage, now, started_at, queued_at=None, admitted_at=None, queue_moved_at=None):
    """The progress block of one running import task. `now` is the service's wall clock; `admitted_at` is when this run
    got the inference permit and `queue_moved_at` when any import last took or returned it."""
    phase = phase_of(stage, operation)
    policy = operation.capture.policy if operation is not None else None
    titles = step_titles(package) if package is not None else {}
    events, model_at = activity(operation, titles) if operation is not None else ([], None)
    if phase == 'queued':
        anchor = latest([moment(queued_at), moment(queue_moved_at), moment(started_at)])
    else:
        records = []
        if operation is not None:
            for attempt in operation.attempts:
                records += [attempt.reserved_at, attempt.dispatched_at, attempt.returned_at]
            records += [value.completed_at for value in operation.receipts]
            records += [value.captured_at for value in operation.task_inputs]
            records += [value.verified_at for value in operation.cleanup_records]
            records += [value.authorized_at for value in operation.authorizations]
            records += [operation.last_observed_at]
        anchor = latest([model_at, *[at for at, _text in events[:1]], moment(started_at), moment(admitted_at),
            *[moment(value) for value in records]])
    quiet = max(0.0, (now - anchor).total_seconds()) if anchor is not None else 0.0
    limit = quiet_limit(phase, policy)
    admitted = moment(admitted_at)
    overdue = (phase in {'processing', 'publication'} and policy is not None and admitted is not None
        and (now - admitted).total_seconds() > whole_import_seconds(policy))
    done, total, current = 0, 0, []
    if operation is not None:
        finished = {value.task_id for value in operation.task_results}
        captured = {value.task_id for value in operation.task_inputs}
        busy = {attempt.task_id for attempt in operation.attempts if attempt.state in {'reserved', 'dispatch_started'}}
        total, done = len(operation.tasks), sum(task.id in finished for task in operation.tasks)
        current = [titles.get(task.block_id, task.block_id) for task in operation.tasks
            if task.id not in finished and (task.id in busy or task.id in captured)]
    return {'phase': phase, 'done': done, 'total': total, 'current': current,
        'events': [{'at': at.isoformat(), 'text': text} for at, text in events[:EVENTS_SHOWN]],
        'lastEventAt': anchor.isoformat() if anchor is not None else None,
        'lastModelAt': model_at.isoformat() if model_at is not None else None,
        'quietSeconds': round(quiet, 3), 'quietLimitSeconds': limit, 'stalled': quiet > limit or overdue}
