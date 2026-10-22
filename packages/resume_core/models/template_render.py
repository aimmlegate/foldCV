"""Captured render input and revision identity are independent of active templates."""

from typing import Literal

from pydantic import Field, model_validator

from .contracts import Id, Revision, Sha256, Wire, _safe_path
from .template_document import RichDocumentV2
from .template_facts import WorkingFactsV2
from ..templates.compiler import canonical, sha256
from ..templates.models import TemplatePackage
from ..templates.store import verify_package


class TemplateSnapshotIdentity(Wire):
    project_id: Id
    project_revision: Revision
    document_revision: Revision
    document_hash: Sha256
    facts_hash: Sha256
    package_hash: Sha256
    presentation_hash: Sha256


class TemplateExportRequestV1(Wire):
    schema_version: Literal[1]
    snapshot: TemplateSnapshotIdentity


class TemplateRenderAsset(Wire):
    id: Id
    path: str
    sha256: Sha256
    size: int = Field(gt=0)

    @model_validator(mode='after')
    def safe_path(self):
        if not _safe_path(self.path):
            raise ValueError('unsafe render asset path')
        return self


class TemplateRendererIdentity(Wire):
    id: Id
    version: Id
    sha256: Sha256


def presentation_value(document, package):
    return {'recipe': package.recipe.model_dump(mode='json', by_alias=True),
        'blocks': {block.id: block.presentation.model_dump(mode='json', by_alias=True) if block.presentation else None
            for block in document.blocks()}}


class CapturedTemplateRenderInputV1(Wire):
    schema_version: Literal[1]
    render_input_version: Literal[1]
    document: RichDocumentV2
    facts: WorkingFactsV2
    document_hash: Sha256
    facts_hash: Sha256
    presentation_hash: Sha256
    package_hash: Sha256
    assets: list[TemplateRenderAsset]
    renderer: TemplateRendererIdentity


class TemplateRenderRequestV1(CapturedTemplateRenderInputV1):
    package: TemplatePackage

    @model_validator(mode='after')
    def identity(self):
        verify_package(self.package)
        from ..templates.presentation import validate_presentation
        validate_presentation(self.document, self.package)
        if (self.document_hash != sha256(canonical(self.document)) or self.facts_hash != sha256(canonical(self.facts))
                or self.package_hash != self.package.package_hash
                or self.presentation_hash != sha256(canonical(presentation_value(self.document, self.package)))
                or self.assets != [TemplateRenderAsset(id=asset.id, path=asset.path, sha256=asset.sha256, size=asset.size)
                    for asset in self.package.assets]):
            raise ValueError('captured render input hash mismatch')
        return self


class TemplateExportCapture(Wire):
    attempt_id: Id
    snapshot: TemplateSnapshotIdentity
    request: CapturedTemplateRenderInputV1

    @model_validator(mode='after')
    def identity(self):
        if (self.snapshot.document_revision != self.request.document.revision or
                (self.snapshot.document_hash, self.snapshot.facts_hash, self.snapshot.presentation_hash, self.snapshot.package_hash) !=
                (self.request.document_hash, self.request.facts_hash, self.request.presentation_hash, self.request.package_hash)):
            raise ValueError('export capture snapshot mismatch')
        return self
