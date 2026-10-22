"""Private v2 canonical candidates reuse the existing intent and receipt owner."""

from typing import Literal

from pydantic import model_validator

from .background import CanonicalCandidateV1
from .template_authority import TemplateFinalizationBinding
from .template_mutations import TemplateMutationV1
from .template_workspace import WorkspaceV7


class TemplateCanonicalCandidateV2(CanonicalCandidateV1):
    schema_version: Literal[2]
    workspace: WorkspaceV7
    manual_mutation: TemplateMutationV1 | None
    inverse: TemplateMutationV1 | None
    template_finalization: TemplateFinalizationBinding | None = None

    @model_validator(mode='after')
    def finalization_owner(self):
        if self.template_finalization is not None and (not self.snapshot_write or self.job_id is not None):
            raise ValueError('template finalization is an application snapshot transaction')
        return self


def decode_canonical_candidate(value):
    if value.get('schemaVersion') == 1:
        return CanonicalCandidateV1.model_validate(value)
    if value.get('schemaVersion') == 2:
        return TemplateCanonicalCandidateV2.model_validate(value)
    raise ValueError('unsupported canonical candidate version')
