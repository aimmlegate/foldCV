"""Native DOCX dimensions and captured-font estimates, without host font lookup."""

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from io import BytesIO
import re

from fontTools.ttLib import TTFont

from .template import RenderFailure


def native_units(value, scale=20, *, positive=False, maximum=2147483647):
    with localcontext(Context(prec=40)):
        number = Decimal(str(value)) * scale
        if not number.is_finite() or number < 0 or number > maximum:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        result = int(number.to_integral_value(rounding=ROUND_HALF_UP))
    if result > maximum or positive and result < 1:
        raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
    return result


def half_points(value):
    with localcontext(Context(prec=40)):
        number = Decimal(str(value)) * 2
        if not number.is_finite() or number != number.to_integral_value() or not 2 <= number <= 3277:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
    return int(number)


@dataclass(frozen=True)
class BodyGeometry:
    width: int
    height: int
    first_top: int
    continuation_top: int
    bottom: int
    left: int
    sidebar_width: int
    gap: int
    main_width: int
    right: int

    @classmethod
    def from_recipe(cls, recipe):
        page = recipe.style.page
        sidebar, main = recipe.layout.regions[1:]
        if sidebar.x + sidebar.width > main.x or page.first_body_top < page.continuation_body_top:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        # Page-size native properties use unsigned short values.
        width = native_units(page.width, positive=True, maximum=65535)
        height = native_units(page.height, positive=True, maximum=65535)
        first = native_units(page.first_body_top)
        continuation = native_units(page.continuation_body_top)
        bottom = native_units(page.body_bottom, positive=True)
        left = native_units(sidebar.x)
        sidebar_width = native_units(sidebar.width, positive=True)
        main_x = native_units(main.x)
        main_width = native_units(main.width, positive=True)
        gap, right = main_x - left - sidebar_width, width - main_x - main_width
        if not 0 <= continuation <= first < bottom < height or gap < 0 or right < 0:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        return cls(width, height, first, continuation, bottom, left, sidebar_width, gap, main_width, right)


class CapturedMetrics:
    def __init__(self):
        self.fonts = {}

    def metrics(self, selection):
        font = selection.font
        if font.sha256 not in self.fonts:
            with TTFont(BytesIO(font.content), lazy=False) as decoded:
                cmap = decoded.getBestCmap()
                advances = decoded['hmtx'].metrics
                self.fonts[font.sha256] = ({point: advances[name][0] / font.units_per_em
                    for point, name in cmap.items()}, decoded['hhea'].ascent / font.units_per_em)
        return self.fonts[font.sha256]

    def ascent(self, style):
        return self.metrics(style.selection)[1] * style.size

    def paragraph_height(self, runs, width, empty_height):
        if width <= 0:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        height, used, line = 0.0, 0.0, 0.0
        previous_cr = False
        for text, style in runs:
            advances, _ascent = self.metrics(style.selection)
            emitted = text[1:] if previous_cr and text.startswith('\n') else text
            previous_cr = text.endswith('\r')
            for token in re.split(r'(\r\n|\r|\n|\t)', emitted):
                if token in {'\r\n', '\r', '\n'}:
                    height += max(line, style.line_height)
                    used, line = 0.0, 0.0
                    continue
                for character in token:
                    advance = (advances[ord(' ')] * 4 if character == '\t'
                        else advances[ord(character)]) * style.size
                    if used and used + advance > width:
                        height += max(line, style.line_height)
                        used, line = 0.0, 0.0
                    used += advance
                    line = max(line, style.line_height)
        return height + max(line, empty_height)
