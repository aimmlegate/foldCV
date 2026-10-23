"""Template tasks run through the selected content provider; ownership and cleanup evidence stay explicit."""

import contextvars
import uuid

from packages.resume_core.models.template_import import LaunchOwner
from packages.resume_core.template_import import CleanupProof, digest
from ..lifecycle import OperationFiles
from ..providers.content import ContentFailure


# The running job's inference permit; set by the template job runtime around one pipeline run.
JOB_PERMIT = contextvars.ContextVar('template_job_permit', default=None)


class ProviderTemplateTransport:
    """One provider process per attempt; a verified terminal return is the only cleanup proof.

    After a restart nothing in memory proves an old process ended, so reconcile reports no proof and the
    attempt stays fenced until durable evidence exists.
    """

    def __init__(self, provider_factory, temp_root, *, incarnation=None):
        self.provider_factory, self.temp_root = provider_factory, temp_root
        self.incarnation = incarnation or 'transport-' + uuid.uuid4().hex

    def reserve_owner(self, _operation, _task, _policy):
        return LaunchOwner(reservationId='reservation-' + uuid.uuid4().hex, incarnationId=self.incarnation, generation=1,
            leaseId='lease-' + uuid.uuid4().hex, processStartWitness=None, transportSessionId=None, transportTurnId=None, pid=None)

    def generate(self, request, cancel):
        try:
            selected = self.provider_factory()
        except Exception as error:
            raise ContentFailure(getattr(error, 'code', 'CONNECTION_REQUIRED')) from None
        if selected is None:
            raise ContentFailure('CONNECTION_REQUIRED')
        provider, model = selected
        if model != request.policy.model:
            raise ContentFailure('MODEL_DENIED')
        files = OperationFiles(self.temp_root)
        permit, owned = JOB_PERMIT.get(), getattr(provider, 'generate_owned', None)
        try:
            with files.open():
                # A job already holds the inference slot; the provider runs under that permit, as fixed jobs do.
                if permit is not None and owned is not None:
                    return owned(request, files, cancel, permit)
                return provider.generate(request, files, cancel)
        except ContentFailure as error:
            if error.code == 'BUSY' and error.dispatch_witness is None:
                # Admission refused before any process started: nothing was dispatched.
                raise ContentFailure('BUSY', cleanup_verified=True, dispatch_witness={'neverDispatched': True}) from None
            raise
        except Exception:
            # An unexpected provider error still ends the owned process scope; report what cleanup actually proved.
            raise ContentFailure('PROCESS_FAILED', logical_attempts=1,
                cleanup_verified=not files.cleanup_failed and files.process is None) from None

    def prove_return(self, attempt, frame):
        if not frame.cleanup_verified:
            return None
        witness = frame.dispatch_witness
        return CleanupProof(attempt.id, digest(attempt.owner), digest({'owner': attempt.owner, 'witness': witness}),
            'provider-owned-terminal', bool(witness and witness.get('neverDispatched') is True))

    def reconcile(self, _attempt):
        return None
