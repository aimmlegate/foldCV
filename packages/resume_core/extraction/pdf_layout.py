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


def _order(lines, path=(), uncertain=False, depth=0):
    if len(lines) < 2 or depth >= 32:
        return [(line, path, uncertain or depth >= 32)
                for line in sorted(lines, key=lambda item: (item.box[1], item.box[0], item.number))]
    scale = median(line.size for line in lines)
    horizontal = max(_gaps(lines, 1), default=(0, 0))
    # Split well-separated bands before columns, so spanning titles stay in place.
    if horizontal[0] >= scale * 1.5:
        top = [line for line in lines if line.box[1] < horizontal[1]]
        bottom = [line for line in lines if line.box[1] >= horizontal[1]]
        return (_order(top, path, uncertain, depth + 1) +
                _order(bottom, path, uncertain, depth + 1))
    vertical = max(_gaps(lines, 0), default=(0, 0))
    if vertical[0] >= scale * 1.5:
        left = [line for line in lines if line.box[0] < vertical[1]]
        right = [line for line in lines if line.box[0] >= vertical[1]]
        if _side_labels(left, right, scale):
            # Sparse side labels can belong to rows; expose coordinates rather than bind them.
            return [(line, path + (0 if line.box[0] < vertical[1] else 1,), True)
                    for line in sorted(lines, key=lambda item: (item.box[1], item.box[0], item.number))]
        paired = _aligned(left, right, scale) >= .8 and _aligned(right, left, scale) >= .8
        return (_order(left, path + (0,), uncertain or paired, depth + 1) +
                _order(right, path + (1,), uncertain or paired, depth + 1))
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
