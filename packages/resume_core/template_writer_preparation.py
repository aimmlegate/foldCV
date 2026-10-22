"""Prepare human edits under the existing authenticated writer boundary."""

from .background_store import BackgroundFailure
from .rich_mutations import RichMutationFailure
from .template_preparation import prepare_edit
from .template_delta import prepare_text_delta
from .templates.presentation import snapshot_identity
from .models.template_authoring import TemplateEditPreparationV1
from .models.template_writer import WriterPreparedDeltaV2
from .project_store import strict_json
from .templates.compiler import canonical, sha256


class TemplateWriterPreparation:
    def capture_clipboard(self, project, request):
        with self.local_history.guard(project), self.guard(project) as (_directory, state, workspace, _checksum):
            self.require(state, request.proof, recovery=True, expired=True)
            self.clipboards.workspace_guard(state, workspace)
            entry = self.clipboards.find(state, request)
            if entry is not None:
                return self.clipboards.read(state, entry).capture.model_copy(deep=True)
            self.require(state, request.proof)
            if request.snapshot != snapshot_identity(workspace):
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            try:
                return self.clipboards.admit(state, workspace, request)
            except (ValueError, RichMutationFailure):
                raise BackgroundFailure('JOB_SCOPE_INVALID') from None

    def release_clipboard(self, project, request):
        from .models.template_writer import WriterClipboardReleaseResultV2
        with self.local_history.guard(project), self.guard(project) as (_directory, state, workspace, _checksum):
            self.require(state, request.proof, recovery=True, expired=True)
            self.clipboards.workspace_guard(state, workspace)
            self.clipboards.release(state, request.clipboard_capture_id)
            return WriterClipboardReleaseResultV2(schemaVersion=2, clipboardCaptureId=request.clipboard_capture_id, released=True)

    def prepare_edit(self, project, request):
        return self._prepare_edit(project, self._bound_preparation(request), 'full')

    def prepare_edit_delta(self, project, request):
        bound = self._bound_preparation(request)
        result = self._prepare_edit(project, bound, 'delta')
        if bound.preparation_input_wire is None:
            return result
        return WriterPreparedDeltaV2(schemaVersion=2,
            preparationInputSha256=sha256(bound.preparation_input_wire.encode('utf-8')),
            requestHash=result.request_hash, delta=result)

    @staticmethod
    def _bound_preparation(request):
        bound = request.model_copy(deep=True)
        if bound.preparation_input_wire is None:
            return bound
        try:
            raw = bound.preparation_input_wire.encode('utf-8')
            if len(raw) > 1024 * 1024:
                raise ValueError('preparation input exceeds bound')
            value = strict_json(raw)
            canonical(value)
            prepared = TemplateEditPreparationV1.model_validate(value)
            if canonical(prepared) != canonical(bound.preparation):
                raise ValueError('preparation input differs from envelope')
            bound.preparation = prepared
            return bound
        except (ValueError, TypeError, RecursionError):
            raise BackgroundFailure('JOB_SCOPE_INVALID') from None

    def _prepare_edit(self, project, request, response_form):
        with self.local_history.guard(project):
            with self.guard(project) as (_directory, state, workspace, checksum):
                self.require(state, request.proof, recovery=True, expired=True)
                if workspace.schema_version != 7 or workspace.project is None:
                    raise BackgroundFailure('JOB_SCOPE_INVALID')
                entry = self.preparations.find(state, request.preparation, response_form=response_form)
                if entry is not None:
                    return self.preparations.read(state, workspace, entry)
                self.require(state, request.proof)
                identifier = request.preparation.client_mutation_id
                if (any(value.client_mutation_id == identifier for value in workspace.mutation_replay)
                        or any(value.client_mutation_id == identifier for value in state.manual_intents)):
                    raise BackgroundFailure('REQUEST_EXPIRED')
                if request.preparation.client_mutation_id.startswith(('background_', 'agent_', 'inverse_', 'history_')):
                    raise BackgroundFailure('JOB_SCOPE_INVALID')
                if request.preparation.snapshot != snapshot_identity(workspace):
                    raise BackgroundFailure('DEPENDENCY_CHANGED')
                from .models.template_authoring import PasteBlocks, PasteInline
                operation = request.preparation.operations[0]
                clipboard = (self.clipboards.read_for_paste(state, workspace, operation.source.clipboard_capture_id)
                    if isinstance(operation, (PasteInline, PasteBlocks)) and operation.source.kind == 'same_project' else None)
                try:
                    factory = prepare_text_delta if response_form == 'delta' else prepare_edit
                    prepared = factory(self.view(state, workspace, checksum).response,
                        request.preparation, request.proof, clipboard=clipboard)
                except (ValueError, RichMutationFailure):
                    raise BackgroundFailure('JOB_SCOPE_INVALID') from None
                return self.preparations.admit(state, workspace, prepared)
