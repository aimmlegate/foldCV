"""Read PDF text geometry without assigning resume semantics."""

from dataclasses import dataclass
from bisect import bisect_left
from statistics import median

import pymupdf

from packages.resume_core.models.contracts import SourceStructure


@dataclass(frozen=True)
class Line:
    block: int
    number: int
    text: str
    box: tuple[float, float, float, float]
    size: float
    bold: bool | None
    uncertain: bool


def _gaps(lines, axis):
    intervals = sorted((line.box[axis], line.box[axis + 2]) for line in lines)
    end = intervals[0][1]
    gaps = []
    for start, stop in intervals[1:]:
        if start > end:
            gaps.append((start - end, (start + end) / 2))
        end = max(end, stop)
    return gaps


def _aligned(first, second, scale):
    centers = sorted((line.box[1] + line.box[3]) / 2 for line in second)
    matches = 0
    for line in first:
        center = (line.box[1] + line.box[3]) / 2
        index = bisect_left(centers, center)
        if any(abs(value - center) < scale * .6 for value in centers[max(0, index - 1):index + 1]):
            matches += 1
    return matches / len(first)


def _side_labels(left, right, scale):
    for narrow, wide in ((left, right), (right, left)):
        width = max(line.box[2] - line.box[0] for line in narrow)
        other_width = max(line.box[2] - line.box[0] for line in wide)
        if (width <= 12 * scale and width < other_width * .65 and
                len(wide) >= len(narrow) * 1.5 and _aligned(narrow, wide, scale) >= .8):
            return True
    return False


GUTTER = 1.0     # the least width of a page gutter, in font sizes (a clear gap between columns is 1.5)
CROSS = .05      # the share of a page's lines that may cross the gutter
SIDE = .08       # the least share of a page's lines on each side of it
SIDE_LINES = 5


def _gutter(lines, scale):
    """The widest x run (start, end) that few lines cross and that has many lines on each side, or None."""
    allowed = max(2, int(len(lines) * CROSS))
    need = max(SIDE_LINES, int(len(lines) * SIDE))
    edges = sorted({line.box[0] for line in lines} | {line.box[2] for line in lines})
    runs = []
    for start, end in zip(edges, edges[1:]):
        middle = (start + end) / 2
        if sum(1 for line in lines if line.box[0] < middle < line.box[2]) > allowed:
            continue
        if runs and runs[-1][1] == start:
            runs[-1][1] = end
        else:
            runs.append([start, end])
    best = None
    for start, end in runs:
        left = sum(1 for line in lines if line.box[2] <= start)
        right = sum(1 for line in lines if line.box[0] >= end)
        if end - start >= scale * GUTTER and left >= need and right >= need and (best is None or end - start > best[1] - best[0]):
            best = (start, end)
    return best


def _dense(lines, scale):
    """The share of lines with another line of the same side right under them: high in a column, low in side labels."""
    tops = sorted(line.box[1] for line in lines)
    return sum(1 for top, under in zip(tops, tops[1:]) if under - top <= scale * 1.8) / max(1, len(lines) - 1)


def _page_columns(lines, x, scale):
    """A page with a gutter, split into its columns first. Bands are cut before columns only for a clear gap, so a
    page whose gutter is narrow, or crossed by a title, was read by rows."""
    across = [line for line in lines if line.box[0] < x < line.box[2]]

    def shares_row(line):
        return any(other.box[0] >= x and min(line.box[3], other.box[3]) - max(line.box[1], other.box[1]) > scale * .3
                   for other in lines)

    # A line across the gutter with a right-column line on its row is a left line with a wide box. A line with a row
    # of its own (a spanning title, a footer) cuts the page into bands.
    spanners = sorted((line for line in across if not shares_row(line)), key=lambda line: (line.box[1], line.number))
    rest = [line for line in lines if line not in spanners]
    left = [line for line in rest if line.box[0] < x]
    right = [line for line in rest if line.box[0] >= x]
    narrow = left if max(line.box[2] - line.box[0] for line in left) <= max(line.box[2] - line.box[0] for line in right) else right
    if _side_labels(left, right, scale) and _dense(narrow, scale) < .5:
        return _order_parts(lines, (), False, 1)     # sparse side labels keep their rows
    out, cuts = [], [None] + spanners
    for index, cut in enumerate(cuts):
        if cut is not None:
            out.append((cut, (), False))
        top = cut.box[1] if cut is not None else float('-inf')
        bottom = cuts[index + 1].box[1] if index + 1 < len(cuts) else float('inf')
        band = [line for line in rest if top <= (line.box[1] + line.box[3]) / 2 < bottom]
        one = [line for line in band if line.box[0] < x]
        two = [line for line in band if line.box[0] >= x]
        # Columns whose rows line up both ways may be one table, so their order is uncertain.
        paired = bool(one and two) and _aligned(one, two, scale) >= .8 and _aligned(two, one, scale) >= .8
        if one:
            out += _order_parts(one, (0,), paired, 1)
        if two:
            out += _order_parts(two, (1,), paired, 1)
    return out


def _by_rows(ordered):
    """A line on the row of the line before it, wholly to its left and of the same column, goes before it: a list
    marker drawn a little lower than its text line sorted after it."""
    out = list(ordered)
    for index in range(1, len(out)):
        (line, path, _), (before, before_path, _) = out[index], out[index - 1]
        middle = (line.box[1] + line.box[3]) / 2
        if path == before_path and before.box[1] <= middle <= before.box[3] and line.box[2] <= before.box[0]:
            out[index - 1], out[index] = out[index], out[index - 1]
    return out


def _order(lines):
    """The lines of one page in reading order, each with its column path and whether its order is uncertain."""
    if len(lines) < 2:
        return _order_parts(lines)
    scale = median(line.size for line in lines)
    found = _gutter(lines, scale)
    return _by_rows(_page_columns(lines, (found[0] + found[1]) / 2, scale) if found else _order_parts(lines))


def _order_parts(lines, path=(), uncertain=False, depth=0):
    if len(lines) < 2 or depth >= 32:
        return [(line, path, uncertain or depth >= 32)
                for line in sorted(lines, key=lambda item: (item.box[1], item.box[0], item.number))]
    scale = median(line.size for line in lines)
    horizontal = max(_gaps(lines, 1), default=(0, 0))
    # Split well-separated bands before columns, so spanning titles stay in place.
    if horizontal[0] >= scale * 1.5:
        top = [line for line in lines if line.box[1] < horizontal[1]]
        bottom = [line for line in lines if line.box[1] >= horizontal[1]]
        return (_order_parts(top, path, uncertain, depth + 1) +
                _order_parts(bottom, path, uncertain, depth + 1))
    vertical = max(_gaps(lines, 0), default=(0, 0))
    if vertical[0] >= scale * 1.5:
        left = [line for line in lines if line.box[0] < vertical[1]]
        right = [line for line in lines if line.box[0] >= vertical[1]]
        if _side_labels(left, right, scale):
            # Sparse side labels can belong to rows; expose coordinates rather than bind them.
            return [(line, path + (0 if line.box[0] < vertical[1] else 1,), True)
                    for line in sorted(lines, key=lambda item: (item.box[1], item.box[0], item.number))]
        paired = _aligned(left, right, scale) >= .8 and _aligned(right, left, scale) >= .8
        return (_order_parts(left, path + (0,), uncertain or paired, depth + 1) +
                _order_parts(right, path + (1,), uncertain or paired, depth + 1))
    ordered = sorted(lines, key=lambda line: (line.box[1], line.box[0], line.number))
    for previous, current in zip(ordered, ordered[1:]):
        if current.box[1] < previous.box[3] - scale * .4:
            uncertain = True
    return [(line, path, uncertain) for line in ordered]


def page_blocks(page):
    """Yield exact text fragments in inferred order, with their visual cues."""
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    raw = page.get_text("dict", flags=flags, sort=False)
    lines = []
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            spans = line["spans"]
            text = "".join(span["text"] for span in spans) + "\n"
            visible = [span for span in spans if span["text"].strip()] or spans
            if not visible:
                continue
            weights = [(max(1, len(span["text"])), span) for span in visible]
            size = sum(weight * span["size"] for weight, span in weights) / sum(w for w, _ in weights)
            bold = {bool(span["flags"] & 16) for span in visible}
            lines.append(Line(block["number"], len(lines), text, tuple(line["bbox"]), max(size, .1),
                              next(iter(bold)) if len(bold) == 1 else None,
                              tuple(line.get("dir", (1, 0))) != (1.0, 0.0)))
    if not lines:
        return
    ordered = _order(lines)
    fragments = []
    for line, path, uncertain in ordered:
        if fragments:
            previous, previous_path, previous_uncertain = fragments[-1]
            last = previous[-1]
            if (path == previous_path and uncertain == previous_uncertain and
                    line.block == last.block and line.number == last.number + 1 and
                    line.bold == last.bold and abs(line.size - last.size) < .5):
                previous.append(line)
                continue
        fragments.append(([line], path, uncertain))
    paths = sorted({path for _, path, _ in fragments if path})
    previous_box, previous_path, group = None, None, 0
    for fragment, path, uncertain in fragments:
        box = [min(line.box[0] for line in fragment), min(line.box[1] for line in fragment),
               max(line.box[2] for line in fragment), max(line.box[3] for line in fragment)]
        scale = median(line.size for line in fragment)
        gap = box[1] - previous_box[3] if previous_box is not None and path == previous_path else None
        if gap is None or gap > scale * 1.2:
            group += 1
        structure = SourceStructure(bounds=[round(value, 2) for value in box],
            column=paths.index(path) + 1 if path else None, group=group,
            gap_before=round(gap, 2) if gap is not None else None,
            font_size=round(scale, 2), bold=fragment[0].bold,
            layout_uncertain=uncertain or any(line.uncertain for line in fragment))
        yield "".join(line.text for line in fragment), fragment[0].block, structure
        previous_box, previous_path = box, path
