"""Public failures of project operations: a catalog code, an HTTP status and optional reply fields."""

from fastapi import Request
from fastapi.responses import JSONResponse


class ProjectFailure(Exception):
    def __init__(self, code, status=409, **details):
        self.code, self.status, self.details = code, status, details
        super().__init__(code)


STATUS = {'PROJECT_NOT_FOUND': 404, 'PROJECT_HISTORY_MISSING': 404, 'JOB_NOT_FOUND': 404, 'SOURCE_NOT_FOUND': 404, 'PROJECT_DELETED': 410,
    'PROJECT_TOO_LARGE': 413, 'V7_INPUT_REJECTED': 422, 'INVALID_REQUEST': 422, 'PROJECT_UNSAFE_STORAGE': 503,
    'PROJECT_LOAD_FAILED': 503, 'PROJECT_SAVE_FAILED': 503}


def failure_response(code, status, details=None, stage='project'):
    body = {'error': {'code': code, 'retryable': False, 'stage': stage}, **(details or {})}
    return JSONResponse(body, status_code=status, headers={'Cache-Control': 'no-store'})


def mount_errors(app):
    from packages.resume_core.project_repository import RepositoryFailure
    from packages.resume_core.project_tasks import TaskFailure

    @app.exception_handler(ProjectFailure)
    async def project_failure(_request: Request, error: ProjectFailure):
        return failure_response(error.code, error.status, error.details)

    @app.exception_handler(RepositoryFailure)
    async def repository_failure(_request: Request, error: RepositoryFailure):
        return failure_response(error.code, STATUS.get(error.code, 409), error.details)

    @app.exception_handler(TaskFailure)
    async def task_failure(_request: Request, error: TaskFailure):
        return failure_response(error.code, STATUS.get(error.code, 409), stage='task')
