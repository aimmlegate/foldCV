"""Structural patches for exact retained canonical values."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import Sha256, Wire


class PatchSet(Wire):
    kind: Literal['set']
    pointer: str = Field(min_length=1)
    value_wire: str


class PatchInsert(Wire):
    kind: Literal['insert']
    pointer: str = Field(min_length=1)
    value_wire: str


class PatchRemove(Wire):
    kind: Literal['remove']
    pointer: str = Field(min_length=1)


class PatchSpliceText(Wire):
    kind: Literal['splice_text']
    pointer: str = Field(min_length=1)
    before_text_hash: Sha256
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str

    @model_validator(mode='after')
    def ordered(self):
        if self.start > self.end:
            raise ValueError('reversed text splice')
        return self


CanonicalPatchStep = Annotated[PatchSet | PatchInsert | PatchRemove | PatchSpliceText,
    Field(discriminator='kind')]


class CanonicalPatchV1(Wire):
    schema_version: Literal[1]
    steps: list[CanonicalPatchStep] = Field(max_length=1000)
