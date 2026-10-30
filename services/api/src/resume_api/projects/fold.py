"""Fold an import sidecar into the commit that shares its revision (plan 2.7).

A checkpoint that already carried the sidecar forward is left as it is. A document edit at that
revision keeps its document and takes the sidecar's operation and facts. The sidecar file is removed
after the workspace file is written; a failed removal does not fail the commit.
"""

from __future__ import annotations

import logging

from packages.resume_core.models.template_import import ImportOperation
from packages.resume_core.project_repository import RepositoryFailure, read_history_file
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.template_import import retain_operation

from ..importer.template_sidecar import PROGRESS, OperationSidecar

LOG = logging.getLogger(__name__)


def sidecar_store(directory):
    return OperationSidecar(directory)


def register_import_fold(repository):
    if getattr(repository, '_import_fold', False):
        return
    repository.fold_hooks.append(fold_sidecar)
    repository.committed_hooks.append(discard_sidecars)
    repository._import_fold = True


def fold_sidecar(session, after):
    """The workspace to write. A sidecar at this revision is folded; an older one is discarded or fences."""
    session._discard_sidecars = []
    folder = session.directory / 'imports'
    if not folder.is_dir():
        return after
    store = sidecar_store(session.directory)
    current, older = [], []
    try:
        for path in sorted(folder.iterdir()):
            if not path.is_file() or not path.name.endswith('.json') or path.name.endswith('.tmp'):
                continue
            stored = store.read(session.project_id, path.name[:-5])
            if stored is None:
                continue
            base, operation, facts = stored
            if base == session.revision:
                current.append((operation, facts))
            elif base > session.revision:
                raise RepositoryFailure('OUTCOME_UNKNOWN')
            else:
                older.append((operation, facts))
    except Exception:
        # Sidecar read failures share the RepositoryFailure class; every one of them is an unknown outcome here.
        raise RepositoryFailure('OUTCOME_UNKNOWN') from None
    if len(current) > 1:
        raise RepositoryFailure('OUTCOME_UNKNOWN')
    discard = []
    for operation, _facts in older:
        if ahead(session, operation):
            raise RepositoryFailure('OUTCOME_UNKNOWN')
        discard.append(operation.id)
    if not current:
        session._discard_sidecars = discard
        return after
    operation, facts = current[0]
    after_ops = _operations(session, after)
    committed_ops = _operations(session, session.workspace)
    after_op = next((item for item in after_ops if item.id == operation.id), None)
    committed_op = next((item for item in committed_ops if item.id == operation.id), None)
    if committed_op is None and after_op is None:
        raise RepositoryFailure('OUTCOME_UNKNOWN')
    # A later step already carries the sidecar. A manual edit still has the committed operation: it keeps its
    # document and takes the sidecar, including a sidecar that changed only the facts.
    manual = after_op is not None and committed_op is not None and after_op == committed_op
    carried = after_op is not None and ((after_op != operation and _forward(operation, after_op))
        or (after_op == operation and (_same_facts(after, facts) or not manual)))
    if carried:
        discard.append(operation.id)
        session._discard_sidecars = discard
        return after
    if after_op is not None and committed_op is not None and after_op != committed_op and not _forward(operation, after_op):
        raise RepositoryFailure('OUTCOME_UNKNOWN')
    copied = after.model_copy(deep=True)
    target = copied.project or copied.pre_draft
    committed_owner = session.workspace.project or session.workspace.pre_draft
    if target.facts != committed_owner.facts and facts != committed_owner.facts and target.facts != facts:
        # The same details as the repository's own conflict (RevisionConflictV1).
        raise RepositoryFailure('REVISION_CONFLICT', revision=session.revision,
            appliedClientMutationIds=list(session.replays))
    base_ops = after_ops or committed_ops
    if any(item.id == operation.id for item in base_ops):
        target.template_operations = [operation if item.id == operation.id else item for item in base_ops]
    else:
        target.template_operations = [*base_ops, operation]
    if target.facts == committed_owner.facts:
        target.facts = facts
    discard.append(operation.id)
    session._discard_sidecars = discard
    return copied


def discard_sidecars(session):
    identifiers = getattr(session, '_discard_sidecars', None) or []
    session._discard_sidecars = []
    if not identifiers:
        return
    store = sidecar_store(session.directory)
    for identifier in identifiers:
        try:
            store.discard(session.project_id, identifier)
        except Exception:
            LOG.exception('sidecar discard failed')


def _operations(session, workspace):
    owner = workspace.project or workspace.pre_draft
    if owner is None:
        return []
    if owner.template_operations:
        return list(owner.template_operations)
    loaded = []
    for ref in getattr(owner, 'import_history', []):
        loaded.append(ImportOperation.model_validate_json(read_history_file(session.directory, ref.sha256)))
    return loaded


def _same_facts(workspace, facts):
    owner = workspace.project or workspace.pre_draft
    return owner is not None and owner.facts == facts


def _forward(before, after):
    if before == after:
        return True
    try:
        retain_operation(before, after)
    except ProjectStoreFailure:
        return False
    return True


def ahead(session, sidecar):
    """A sidecar whose attempts are further along than the saved project is a fenced import."""
    committed = next((item for item in _operations(session, session.workspace) if item.id == sidecar.id), None)
    if committed is None:
        return True
    saved = {attempt.id: attempt for attempt in committed.attempts}
    return any(attempt.id not in saved or PROGRESS[saved[attempt.id].state] < PROGRESS[attempt.state]
        for attempt in sidecar.attempts)
