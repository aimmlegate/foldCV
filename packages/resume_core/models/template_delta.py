"""Compact prepared results preserve server ownership of authoring semantics."""

from typing import Literal

from pydantic import Field, model_validator

from .canonical_patch import CanonicalPatchStep
from .contracts import Id, Sha256, Wire, _unique
from .rich_mutations import ActionCapture
from .template_mutations import TemplateMutationV1
from .template_render import TemplateSnapshotIdentity
from ..rich_api import RichGenerationState
from ..rich_identity import ResumeIdentity
from ..templates.models import AuthoredPresentation


class PresentationPatchV1(Wire):
    before_hash: Sha256
    after_hash: Sha256
    set: dict[Id, AuthoredPresentation]
    remove: list[Id]

    @model_validator(mode='after')
    def distinct(self):
        _unique(self.remove, 'removed presentation')
        if self.set.keys() & self.remove:
            raise ValueError('presentation patch both sets and removes a block')
        return self


class TemplatePreparedEditDeltaV1(Wire):
    schema_version: Literal[1]
    client_mutation_id: Id
    base_snapshot: TemplateSnapshotIdentity
    base_workspace_sha256: Sha256
    result_snapshot: TemplateSnapshotIdentity
    result_workspace_sha256: Sha256
    capture: ActionCapture
    request_hash: Sha256
    created_ids: dict[str, dict[str, Id]]
    mutation_wire: str | None
    workspace_patch: list[CanonicalPatchStep] = Field(max_length=1000)
    presentation_patch: PresentationPatchV1
    result_identity: ResumeIdentity | None
    result_generation: RichGenerationState | None

    @model_validator(mode='after')
    def identity(self):
        if (self.base_snapshot.project_id != self.result_snapshot.project_id
                or self.base_snapshot.package_hash != self.result_snapshot.package_hash):
            raise ValueError('prepared delta changes project or captured package')
        _unique([identifier for slots in self.created_ids.values() for identifier in slots.values()], 'allocated ID')
        if self.mutation_wire is None:
            if (self.workspace_patch or self.presentation_patch.set or self.presentation_patch.remove
                    or self.presentation_patch.before_hash != self.presentation_patch.after_hash
                    or self.base_snapshot != self.result_snapshot
                    or self.base_workspace_sha256 != self.result_workspace_sha256 or any(self.created_ids.values())):
                raise ValueError('no-op delta changes authored state or allocates identities')
        else:
            mutation = TemplateMutationV1.model_validate_json(self.mutation_wire)
            if (mutation.model_dump_json(by_alias=True) != self.mutation_wire
                    or mutation.client_mutation_id != self.client_mutation_id or mutation.capture != self.capture
                    or mutation.project_id != self.base_snapshot.project_id or mutation.history.kind != 'edit'
                    or self.result_snapshot.project_revision <= self.base_snapshot.project_revision
                    or self.result_snapshot.document_revision <= self.base_snapshot.document_revision):
                raise ValueError('prepared delta mutation identity differs')
        return self
