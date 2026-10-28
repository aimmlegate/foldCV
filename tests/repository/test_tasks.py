"""The in-memory task registry behind GET /tasks: stages, elapsed time from an injected clock, one import per project."""

import pytest

from packages.resume_core import project_tasks
from packages.resume_core.project_tasks import TaskFailure, TaskRegistry


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def registry():
    clock = Clock()
    return TaskRegistry(clock=clock, wall=lambda: '2026-10-27T10:00:00+00:00'), clock


def test_a_task_reports_stage_detail_and_elapsed_time(tmp_path):
    tasks, clock = registry()
    task = tasks.start('project-a', 'import', stage='read_source')
    clock.now = 112.5
    tasks.update(task.id, stage='extract_facts', detail={'facts': 3})
    status = tasks.list('project-a')[0]
    assert status == {'id': task.id, 'projectId': 'project-a', 'kind': 'import', 'state': 'running', 'stage': 'extract_facts',
        'startedAt': '2026-10-27T10:00:00+00:00', 'elapsed': 12.5, 'detail': {'facts': 3}, 'error': None}
    tasks.finish(task.id, 'failed', error='QUOTA_EXHAUSTED')
    clock.now = 500.0
    assert tasks.list('project-a')[0]['elapsed'] == 12.5 and tasks.list('project-a')[0]['error'] == 'QUOTA_EXHAUSTED'


def test_one_running_import_per_project_and_finished_tasks_stay_final():
    tasks, _clock = registry()
    first = tasks.start('project-a', 'import')
    with pytest.raises(TaskFailure) as refused:
        tasks.start('project-a', 'import')
    assert refused.value.code == 'REQUEST_IN_PROGRESS'
    tasks.start('project-b', 'import')
    tasks.start('project-a', 'export')
    tasks.finish(first.id, 'cancelled')
    tasks.update(first.id, stage='late')
    tasks.finish(first.id, 'succeeded')
    assert tasks.list('project-a')[0]['state'] == 'cancelled' and tasks.list('project-a')[0]['stage'] is None
    assert tasks.start('project-a', 'import').state == 'running'


def test_cancel_sets_the_task_event_and_unknown_ids_are_refused():
    tasks, _clock = registry()
    task = tasks.start('project-a', 'rewrite')
    tasks.cancel(task.id)
    assert task.cancel.is_set()
    with pytest.raises(TaskFailure) as refused:
        tasks.update('missing', stage='x')
    assert refused.value.code == 'JOB_NOT_FOUND'


def test_no_task_starts_on_a_project_that_is_being_deleted():
    tasks, _clock = registry()
    with tasks.closed('project-a'):
        with tasks.closed('project-a'):
            pass
        with pytest.raises(TaskFailure) as refused:
            tasks.start('project-a', 'export', exclusive=False)
        assert refused.value.code == 'REQUEST_IN_PROGRESS'
        tasks.start('project-b', 'export')
    assert tasks.start('project-a', 'export').state == 'running'


def test_finished_tasks_are_bounded_and_forgotten_with_their_project(monkeypatch):
    monkeypatch.setattr(project_tasks, 'FINISHED_KEPT', 2)
    tasks, clock = registry()
    for index in range(4):
        clock.now += 1
        tasks.finish(tasks.start('project-a', 'export', exclusive=False).id, 'succeeded')
    running = tasks.start('project-a', 'import')
    assert [status['id'] for status in tasks.list('project-a')] == ['export_3', 'export_4', running.id]
    tasks.forget('project-a')
    assert [status['id'] for status in tasks.list()] == [running.id]
