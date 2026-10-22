"""Application finalization has bounded persistence authority and no worker permit."""

from .background_store import BackgroundFailure
from .models.template_import import FinalizationCandidate
from .template_import import authorization, digest, expiry, identity, instant


def owner(workspace):
    return workspace.project or workspace.pre_draft


def finalization_hashes(operation, project):
    return {'operationId': operation.id, 'sourceHash': digest(operation.capture.source_hashes),
        'dependencyHash': operation.capture.dependency_hash, 'authorityHash': operation.capture.authority_hash,
        'packageHash': project.template_package.package_hash, 'documentHash': digest(project.document),
        'factsHash': digest(project.facts), 'issuesHash': digest(project.import_issues),
        'coverageHash': digest(project.import_coverage)}


def capture_finalization(operation, project, now, *, id_factory=identity):
    current = authorization(operation)
    if any(task.state not in {'accepted', 'empty', 'source_fallback'} for task in operation.tasks):
        raise BackgroundFailure('JOB_SCOPE_INVALID')
    if any(attempt.cleanup.state != 'verified' for attempt in operation.attempts):
        raise BackgroundFailure('CLEANUP_FAILED')
    values = finalization_hashes(operation, project)
    if operation.finalization is not None:
        previous = operation.finalization
        if previous.candidate_hash != digest(values) or previous.authorization_id != current.id:
            raise BackgroundFailure('DEPENDENCY_CHANGED')
        return previous.model_copy(deep=True)
    if project.template_package.package_hash != operation.capture.package_hash:
        raise BackgroundFailure('DEPENDENCY_CHANGED')
    return FinalizationCandidate(id=id_factory('finalization'), authorizationId=current.id, **values,
        candidateHash=digest(values), startedAt=now, expiresAt=expiry(now, operation.capture.policy.finalization_seconds))


def validate_finalization(binding, before, after, now):
    before_operation = next((operation for operation in owner(before).template_operations if operation.id == binding.operation_id), None)
    after_operation = next((operation for operation in owner(after).template_operations if operation.id == binding.operation_id), None)
    if before_operation is None or after_operation is None or after.project is None:
        raise BackgroundFailure('JOB_SCOPE_INVALID')
    if before_operation.state == 'cancelled' or not before_operation.authorizations or before_operation.authorizations[-1].state != 'active':
        raise BackgroundFailure('CANCELLED')
    candidate = before_operation.finalization
    if (candidate is None or candidate.id != binding.finalization_id or candidate.authorization_id != binding.authorization_id
            or before_operation.authorizations[-1].id != binding.authorization_id or after_operation.finalization != candidate
            or before_operation.capture != after_operation.capture):
        raise BackgroundFailure('DEPENDENCY_CHANGED')
    if instant(now) >= instant(candidate.expires_at):
        raise BackgroundFailure('REQUEST_EXPIRED')
    if any(attempt.cleanup.state != 'verified' for attempt in before_operation.attempts):
        raise BackgroundFailure('CLEANUP_FAILED')
    if digest(finalization_hashes(before_operation, after.project)) != candidate.candidate_hash:
        raise BackgroundFailure('DEPENDENCY_CHANGED')
    if ({source.id: source.byte_sha256 for source in owner(before).sources} != before_operation.capture.source_hashes
            or owner(before).template_package.package_hash != candidate.package_hash):
        raise BackgroundFailure('DEPENDENCY_CHANGED')
