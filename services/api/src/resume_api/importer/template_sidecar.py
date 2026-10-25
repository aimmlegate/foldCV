"""Operation-only steps of a running template import are saved in one sidecar file, not the whole project (S7e).

A processing step (task input, reservation, dispatch, return, parse, review, admission, finish, fallback) replaces
`imports/<operation>.json` in the project folder atomically: the operation and the facts after the step and the
project revision they extend. The whole project is saved through the publisher at start, admission, publication and
every other template write; each such save folds the sidecar in first. A reader overlays the sidecar while its
revision is the project's; an older sidecar must already be folded into the project, otherwise the import is fenced.
"""

import json
import os
import re

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.template_facts import WorkingFactsV2
from packages.resume_core.models.template_import import ImportOperation
from packages.resume_core.project_limits import PROJECT_CEILING_BYTES as WORKSPACE_CEILING_BYTES

NAME = re.compile(r'[A-Za-z0-9_-]{1,128}')
# How far an attempt has come; a folded project never keeps an attempt behind its sidecar.
PROGRESS = {'reserved': 0, 'dispatch_started': 1, 'outcome_unknown': 2, 'returned': 2, 'reconciled': 3, 'released': 3}


def _private_directory(path):
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or not path.is_dir() or path.stat().st_uid != os.getuid():
        raise BackgroundFailure('JOB_STORE_UNAVAILABLE')
    os.chmod(path, 0o700)


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class OperationSidecar:
    def __init__(self, publisher):
        self.publisher = publisher

    @property
    def store(self):
        return self.publisher.canonical

    def path(self, project, operation_id):
        if NAME.fullmatch(operation_id) is None:
            raise BackgroundFailure('JOB_STORE_UNAVAILABLE')
        return self.store.project_directory(project) / 'imports' / (operation_id + '.json')

    def write(self, project, revision, operation, facts):
        """Atomically replace the sidecar with the operation and facts after one step on the given project revision."""
        target = self.path(project, operation.id)
        _private_directory(target.parent)
        raw = json.dumps({'schemaVersion': 1, 'projectRevision': revision, 'operation': operation.model_dump(mode='json', by_alias=True),
            'facts': facts.model_dump(mode='json', by_alias=True)}, ensure_ascii=False, separators=(',', ':')).encode()
        if len(raw) > WORKSPACE_CEILING_BYTES:
            raise BackgroundFailure('JOB_STORAGE_FULL')
        temporary = target.with_name(target.name + '.tmp')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            _fsync_directory(target.parent)
        except OSError:
            raise BackgroundFailure('OUTCOME_UNKNOWN') from None

    def read(self, project, operation_id):
        """(project revision, operation, facts) of the sidecar, or None when the import has none."""
        target = self.path(project, operation_id)
        try:
            descriptor = os.open(target, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        except FileNotFoundError:
            return None
        except OSError:
            raise BackgroundFailure('JOB_STORE_UNAVAILABLE') from None
        with os.fdopen(descriptor, 'rb') as stream:
            status = os.fstat(stream.fileno())
            if status.st_nlink != 1 or status.st_uid != os.getuid() or status.st_mode & 0o077:
                raise BackgroundFailure('JOB_STORE_UNAVAILABLE')
            raw = stream.read(WORKSPACE_CEILING_BYTES + 1)
        try:
            value = json.loads(raw)
            if (len(raw) > WORKSPACE_CEILING_BYTES or set(value) != {'schemaVersion', 'projectRevision', 'operation', 'facts'}
                    or value['schemaVersion'] != 1):
                raise ValueError('sidecar shape')
            operation, facts = ImportOperation.model_validate(value['operation']), WorkingFactsV2.model_validate(value["facts"])
        except ValueError:
            raise BackgroundFailure('JOB_STORE_CORRUPT') from None
        if operation.id != operation_id or type(value['projectRevision']) is not int:
            raise BackgroundFailure('JOB_STORE_CORRUPT')
        return value['projectRevision'], operation, facts

    def key(self, project, operation_id):
        """The identity of a sidecar file, or None without one; every write replaces the file."""
        try:
            status = os.stat(self.path(project, operation_id), follow_symlinks=False)
        except FileNotFoundError:
            return None
        return (status.st_ino, status.st_size, status.st_mtime_ns, status.st_ctime_ns)

    def keys(self, project, workspace):
        data = workspace.project or workspace.pre_draft
        return tuple(self.key(project, value.id) for value in data.template_operations) if data is not None else ()

    def discard(self, project, operation_id):
        target = self.path(project, operation_id)
        try:
            target.unlink()
            _fsync_directory(target.parent)
        except FileNotFoundError:
            pass

    def overlay(self, project, revision, operation):
        """The operation and facts a reader must use: the sidecar's while it extends this project revision, else the
        project's operation and no facts.

        A sidecar on an older revision must be folded already: every attempt it holds is in the project at least as
        far; otherwise a project save lost import steps and the outcome is unknown.
        """
        stored = self.read(project, operation.id)
        if stored is None:
            return operation, None
        base, sidecar, facts = stored
        if base == revision:
            return sidecar, facts
        if base > revision:
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        folded = {attempt.id: attempt for attempt in operation.attempts}
        if any(attempt.id not in folded or PROGRESS[folded[attempt.id].state] < PROGRESS[attempt.state]
                for attempt in sidecar.attempts):
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        return operation, None
