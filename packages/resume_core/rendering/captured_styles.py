"""Resolve authored presentation and actual glyph availability from captured fonts."""

from dataclasses import dataclass, replace
from decimal import Context,Decimal,localcontext
from io import BytesIO
import math
import unicodedata

from fontTools.ttLib import TTFont

from .captured_fonts import CapturedFontResolver,FontRequest,FontSelection
from .template import RenderFailure


@dataclass(frozen=True)
class RunStyle:
    selection: FontSelection
    size: float
    line_height: float
    color: str
    background: str | None
    underline: bool
    strike: bool
    chip: bool = False
    gap: float = 0


def scaled_line_height(height, size, base_size):
    with localcontext(Context(prec=40)):
        result = float(Decimal(str(height)) * Decimal(str(size)) / Decimal(str(base_size)))
    if not math.isfinite(result) or result <= 0:
        raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
    return result


def resize_run(style, size):
    return replace(style, size=size, line_height=scaled_line_height(style.line_height, size, style.size))


def authored_spans(block):
    """Each text span with its link; a link child without its own presentation inherits the link's."""
    for span in block.content:
        if span.type not in {'bound_link', 'link'}:
            yield span, None
            continue
        for child in span.content:
            inherited = child.presentation is None and span.presentation is not None
            yield (child.model_copy(update={'presentation': span.presentation}) if inherited else child), span


class CapturedStyleResolver:
    def __init__(self,package):
        self.fonts=CapturedFontResolver(package)
        self.package_hash=package.package_hash
        self.style=package.recipe.style.model_copy(deep=True)
        self.views={key:view.model_copy(deep=True) for key,view in package.recipe.views.items()}
        self.glyphs={}

    def _reference(self,ref):
        if (ref is None or ref.package_hash!=self.package_hash or ref.view_key not in self.views
                or ref.style_token not in self.style.text or ref.node_index is not None
                and not 0<=ref.node_index<len(self.views[ref.view_key].nodes)
                or ref.overrides.font is not None and ref.overrides.font not in self.style.fonts):
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        return self.style.text[ref.style_token]

    def _run(self,block,ref,marks=None):
        style=self._reference(ref);overrides=ref.overrides
        if marks is not None and marks.code:raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        selected=self.fonts.select(FontRequest(overrides.font or style.font,bold=overrides.bold,
            italic=overrides.italic,mark_bold=bool(marks and marks.bold),mark_italic=bool(marks and marks.italic)))
        size=overrides.size if overrides.size is not None else style.size
        height=scaled_line_height(style.line_height,size,style.size)
        inline_color=marks.text_color if marks else 'default'
        paragraph_color=getattr(block.props,'text_color','default')
        color=(inline_color if inline_color!='default' else overrides.color if overrides.color is not None
            else paragraph_color if paragraph_color!='default' else self.style.colors[style.color])
        inline_background=marks.background_color if marks else 'default'
        paragraph_background=getattr(block.props,'background_color','default')
        background=(inline_background if inline_background!='default'
            else paragraph_background if paragraph_background!='default' else None)
        return RunStyle(selected,size,height,color,background,
            bool(marks and marks.underline),bool(marks and marks.strike))

    def run(self,block,span):
        if span.type not in {'text','fact_field','manual_scope'}:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        self._reference(block.presentation)
        result=self._run(block,span.presentation if span.presentation is not None else block.presentation,span.styles)
        self.validate_text(result.selection,span.text)
        return result

    def paragraph(self,block):
        if not isinstance(block.content,list) or any(span.type not in {'text','fact_field','manual_scope','bound_link','link'}
                for span in block.content):
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        self._reference(block.presentation)
        runs=[self.run(block,span) for span,_link in authored_spans(block) if span.text]
        height=max(run.line_height for run in runs) if runs else self._run(block,block.presentation).line_height
        alignment=(block.presentation.overrides.alignment if block.presentation.overrides.alignment is not None
            else block.props.alignment)
        return height,alignment

    def validate_text(self,selection,text):
        font=selection.font
        if font.sha256 not in self.glyphs:
            with TTFont(BytesIO(font.content),lazy=True) as decoded:
                order={name:index for index,name in enumerate(decoded.getGlyphOrder())}
                self.glyphs[font.sha256]={point for point,name in decoded.getBestCmap().items()
                    if name!='.notdef' and order.get(name,0)>0}
        for character in text:
            if character in '\n\r\t':continue
            category=unicodedata.category(character)
            if category.startswith('M') or category in {'Cf','Cc','Cs'}:
                raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
            if ord(character) not in self.glyphs[font.sha256]:raise RenderFailure('FONT_UNAVAILABLE')
