"""Resolve authored font faces using only exact captured static font assets."""

from dataclasses import dataclass

from ..templates.store import verify_package
from .captured_assets import CapturedFont,decode_font
from .template import RenderFailure


@dataclass(frozen=True)
class FontRequest:
    base_token: str
    bold: bool | None = None
    italic: bool | None = None
    mark_bold: bool = False
    mark_italic: bool = False


@dataclass(frozen=True)
class FontSelection:
    font: CapturedFont
    weight: int
    italic: bool


class CapturedFontResolver:
    def __init__(self,package):
        verify_package(package)
        self.tokens=dict(package.recipe.style.fonts)
        self.assets={asset.id:asset.model_copy(deep=True) for asset in package.assets}
        self.declarations={asset.id:asset.model_copy(deep=True) for asset in package.definition.assets}
        self.decoded={}
        self.failures={}
        self.selected_faces={}

    def _decode(self,identifier):
        if identifier in self.failures:raise RenderFailure(self.failures[identifier])
        if identifier not in self.decoded:
            if identifier not in self.assets or identifier not in self.declarations:
                raise RenderFailure('FONT_UNAVAILABLE')
            try:self.decoded[identifier]=decode_font(self.assets[identifier],self.declarations[identifier])
            except RenderFailure as error:
                self.failures[identifier]=error.code
                raise
        return self.decoded[identifier]

    def select(self,request):
        identifier=self.tokens.get(request.base_token)
        if identifier is None:raise RenderFailure('FONT_UNAVAILABLE')
        base=self._decode(identifier)
        weight=base.weight if request.bold is None else 700 if request.bold else 400
        italic=base.italic if request.italic is None else request.italic
        # Bold never thins a heavier style such as Black.
        if request.mark_bold:weight=max(weight,700)
        if request.mark_italic:italic=True
        selected=base
        if (weight,italic)!=(base.weight,base.italic):
            matches={}
            for candidate in sorted(set(self.tokens.values())):
                try:font=self._decode(candidate)
                except RenderFailure:continue
                if (font.typographic_family.casefold(),font.weight,font.italic)==(
                        base.typographic_family.casefold(),weight,italic):
                    matches.setdefault(font.sha256,font)
            if not matches:raise RenderFailure('FONT_UNAVAILABLE')
            if len(matches)!=1:raise RenderFailure('FONT_MISMATCH')
            selected=next(iter(matches.values()))
        face=(selected.family.casefold(),selected.bold,selected.italic)
        if face in self.selected_faces and self.selected_faces[face]!=selected.sha256:
            raise RenderFailure('FONT_MISMATCH')
        self.selected_faces[face]=selected.sha256
        return FontSelection(selected,weight,italic)
