"""Attempt-independent application authority shares the canonical publication lock."""

from typing import Literal

from pydantic import Field, model_validator

from .contracts import Id, Revision, Sha256, Wire
from .template_import import AttemptCleanupRecord, LaunchOwner


class DeletedTemplateCleanupV1(Wire):
    capture_hash: Sha256
    owners: dict[str, LaunchOwner]
    records: list[AttemptCleanupRecord]

    @model_validator(mode='after')
    def exact_owners(self):
        from ..template_import import digest
        if (len({record.attempt_id for record in self.records}) != len(self.records)
                or {record.attempt_id for record in self.records} - self.owners.keys()
                or any(record.owner_hash != digest(self.owners[record.attempt_id]) for record in self.records)):
            raise ValueError('deleted cleanup must bind each proof to its captured owner')
        return self

    @property
    def complete(self):
        return len(self.records) == len(self.owners)


class TemplateFinalizationBinding(Wire):
    operation_id: Id
    authorization_id: Id
    finalization_id: Id


class TemplatePublicationAuthorizationV1(Wire):
    schema_version: Literal[1]
    operation_id: Id
    authorization_id: Id
    state: Literal['active', 'cancelled']
    authority_hash: Sha256
    dependency_hash: Sha256
    account_generation: Revision
    deleted_cleanup: DeletedTemplateCleanupV1 | None = Field(default=None, exclude_if=lambda value: value is None)
