"""Prepare human edits under the existing authenticated writer boundary."""

from .background_store import BackgroundFailure
from .rich_mutations import RichMutationFailure
from .template_address_map import address_map_sha256, build_address_map
from .template_preparation import prepare_edit
from .template_delta import prepared_delta
from .templates.presentation import snapshot_identity
from .models.template_authoring import TemplateEditPreparationV1
from .models.template_writer import WriterPreparedDeltaV2, WriterPreparedEditV2
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

    def rewrite_source(self, project, request):
        """Read the selected text for a rewrite preview; the active writer and exact snapshot are required."""
        from .template_rewrite import rewrite_source
        with self.local_history.guard(project), self.guard(project) as (_directory, state, workspace, _checksum):
            self.require(state, request.proof)
            if request.snapshot != snapshot_identity(workspace):
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            try:
                return rewrite_source(workspace, request)
            except (ValueError, RichMutationFailure):
                raise BackgroundFailure('JOB_SCOPE_INVALID') from None

    def prepare_edit(self, project, request):
        bound = self._bound_preparation(request)
        result, address = self._prepare_edit(project, bound, 'full')
        if bound.preparation_input_wire is None:
            return result
        return WriterPreparedEditV2(schemaVersion=2,
            preparationInputSha256=sha256(bound.preparation_input_wire.encode('utf-8')),
            requestHash=result.request_hash, prepared=result, addressMap=address,
            addressMapSha256=address_map_sha256(address))

    def prepare_edit_delta(self, project, request):
        bound = self._bound_preparation(request)
        result, address = self._prepare_edit(project, bound, 'delta')
        if bound.preparation_input_wire is None:
            return result
        return WriterPreparedDeltaV2(schemaVersion=2,
            preparationInputSha256=sha256(bound.preparation_input_wire.encode('utf-8')),
            requestHash=result.request_hash, delta=result, addressMap=address,
            addressMapSha256=address_map_sha256(address))

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
                    prepared = self.preparations.read(state, workspace, entry)
                    address = (self.preparations.read_address(state, entry)
                        if request.preparation_input_wire is not None else None)
                    return prepared, address
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
                    response = self.view(state, workspace, checksum).response
                    prepared = prepare_edit(response, request.preparation, clipboard=clipboard)
                    # One preparation builds the map from its own exact result; retries reuse it.
                    address = build_address_map(response, request.preparation, prepared)
                    if response_form == 'delta':
                        prepared = prepared_delta(response, prepared)
                except (ValueError, RichMutationFailure):
                    raise BackgroundFailure('JOB_SCOPE_INVALID') from None
                return self.preparations.admit(state, workspace, prepared, address), address
