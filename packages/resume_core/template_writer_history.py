"""Verified writer commands derive local replay from retained committed changes."""

from .background_history import digest_bytes
from .background_store import BackgroundFailure
from .models.background import WriterCommitBindingV1
from .template_local_history import TemplateLocalHistory
from .templates.compiler import canonical, sha256


class TemplateWriterHistory:
    def save_template(self, project, request, *, originals=None, artifacts=None, images=None):
        if request.mutation.history.kind != 'edit':
            raise BackgroundFailure('JOB_SCOPE_INVALID')
        registry = self.local_history
        with registry.guard(project):
            with self.guard(project) as (directory, state, workspace, _checksum):
                self.require(state, request.proof, recovery=True, expired=True)
                self.preparations.save_guard(state, workspace, request)
                registry.reconcile(self, state, workspace, directory)
            context = {}
            def authorize(state, workspace, directory):
                writer = self.require(state, request.proof)
                self.preparations.save_guard(state, workspace, request)
                if ((request.canonical_revision, request.canonical_sha256) !=
                        (writer.acknowledged_revision, writer.acknowledged_sha256)
                        or request.mutation.project_id != project or request.mutation.capture.session_id != writer.session_id):
                    raise BackgroundFailure('WRITER_UNKNOWN')
                opening = registry.reconcile(self, state, workspace, directory) or registry.opening(state, create=True)
                registry.observe(opening, state)
                context['opening'] = opening
                actual = request.model_copy(update={'canonical_revision': workspace.project_revision,
                    'canonical_sha256': digest_bytes(workspace)}, deep=True)
                self.advance(state, workspace, digest_bytes(workspace), actual)
                self.write(directory, state)
                return WriterCommitBindingV1(epoch=writer.epoch, incarnation=writer.incarnation,
                    actionCursor=writer.acknowledged_cursor, touchGeneration=writer.touch_generation)
            def prepared(before, after, candidate, state):
                registry.prepare_edit(context['opening'], request.mutation, before, after, candidate, state)
                self.preparations.prepare_commit(self, state, before, after, candidate, request, context['opening'])
            try:
                _workspace, replayed = self.coordinator.manual(project, request.mutation, authorize=authorize,
                    prepared=prepared, originals=originals, artifacts=artifacts, images=images)
            except BaseException:
                registry.rollback_unpublished(self, request.mutation)
                self.preparations.rollback_commit_unpublished(self, request.mutation)
                raise
            self.observer('before_local_history_receipt', project)
            with self.guard(project) as (directory, state, workspace, checksum):
                self.require(state, request.proof, recovery=True, expired=True)
                opening = registry.reconcile(self, state, workspace, directory)
                self.preparations.committed(state, workspace, request.mutation)
                if request.response_mode == 'prepared_delta':
                    return self.preparations.compact_response(state, workspace, checksum, request, replayed)
                view = self.mutation_view(state, workspace, checksum, request.mutation, replayed)
                return view.model_copy(update={'local_history_ack': self._history_ack(opening, request.mutation.action_id)}, deep=True)

    @staticmethod
    def _history_ack(opening, action_id):
        from .models.template_writer import LocalHistoryAckV2
        value = TemplateLocalHistory.ack(opening, action_id)
        return LocalHistoryAckV2.model_validate(value) if value is not None else None

    def local_history_command(self, project, request, *, originals=None, artifacts=None, images=None):
        registry = self.local_history
        logical_hash = sha256(canonical(request))
        with registry.guard(project):
            with self.guard(project) as (directory, state, workspace, checksum):
                self.require(state, request.proof, recovery=True, expired=True)
                if workspace.schema_version != 7:
                    raise BackgroundFailure('JOB_SCOPE_INVALID')
                self.preparations.reject_registered(state, request.client_mutation_id)
                opening = registry.reconcile(self, state, workspace, directory)
                if opening is None:
                    raise BackgroundFailure('REQUEST_EXPIRED')
                known = opening.commands.get(request.client_mutation_id)
                if known is not None:
                    if known[0] != logical_hash:
                        raise BackgroundFailure('JOB_IDEMPOTENCY_CONFLICT')
                    view = self.mutation_view(state, workspace, checksum, known[1], True)
                    return view.model_copy(update={'local_history_ack': self._history_ack(opening, known[2])}, deep=True)
                self.require(state, request.proof)
                if (request.canonical_revision, request.canonical_sha256) != (workspace.project_revision, checksum):
                    raise BackgroundFailure('DEPENDENCY_CHANGED')
                registry.observe(opening, state)
                try:
                    mutation = registry.derive(opening, workspace, request)
                except ValueError:
                    raise BackgroundFailure('DEPENDENCY_CHANGED') from None
            def authorize(state, before, directory):
                writer = self.require(state, request.proof)
                if (request.canonical_revision, request.canonical_sha256) != (before.project_revision, digest_bytes(before)):
                    raise BackgroundFailure('DEPENDENCY_CHANGED')
                registry.observe(opening, state)
                registry.action(opening, request)
                self.advance(state, before, digest_bytes(before), request)
                self.write(directory, state)
                return WriterCommitBindingV1(epoch=writer.epoch, incarnation=writer.incarnation,
                    actionCursor=writer.acknowledged_cursor, touchGeneration=writer.touch_generation)
            def authority(_state, before, _directory):
                expected = registry.derive(opening, before, request)
                if canonical(expected) != canonical(mutation):
                    raise BackgroundFailure('DEPENDENCY_CHANGED')
                return registry.authorization(before, mutation)
            def prepared(before, after, candidate, state):
                registry.prepare_replay(opening, request, mutation, before, after, candidate, state)
            try:
                self.coordinator.manual(project, mutation, authorize=authorize, history_authority=authority,
                    prepared=prepared, originals=originals, artifacts=artifacts, images=images)
            except BaseException:
                registry.rollback_unpublished(self, mutation)
                raise
            self.observer('before_local_history_receipt', project)
            with self.guard(project) as (directory, state, workspace, checksum):
                self.require(state, request.proof, recovery=True, expired=True)
                opening = registry.reconcile(self, state, workspace, directory)
                if opening is None or request.client_mutation_id not in opening.commands:
                    raise BackgroundFailure('REQUEST_EXPIRED')
                view = self.mutation_view(state, workspace, checksum, mutation, False)
                return view.model_copy(update={'local_history_ack': self._history_ack(opening, request.origin_action_id)}, deep=True)
