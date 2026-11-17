"""Checks of a map by code: signs that an entry holds more than one project or that the map took a
period from the wrong line. No model call. Each finding is {check, entry, line}; none changes the map.

period          the entry holds a line that is only a period and is not its own period
label-twice     the entry holds the same label twice («Стек:» … «Стек:»)
heading-inside  a bold or heading line that is no sub-heading word stands after a list item of the entry
title-inside    a short plain line with no end mark stands after a list item, and a list item follows
list-restart    any plain line stands after a list item, and a list item follows (the weakest sign)
A plain line that only continues the line above it (a wrapped list item) is no sign: see `continues`."""

import re

from .scheme import BULLET, LABEL_ONLY, LABELLED, SUBHEADS
from packages.resume_core.template_source_cleanup import without_form

STRONG = ('period', 'label-twice', 'heading-inside')
MARKER_ONLY = re.compile(r'^[\s\u200b]*[●•◦▪■○·*–—-][\s\u200b]*$')


def cues(data):
    """Per line ref: its unit's layout cues (bold, a list item, a heading)."""
    units = {unit.id: unit for unit in data.source.units}
    found = {}
    for line in data.lines:
        unit = units.get(line.span.unit_id) or units.get(line.span.unit_id.split('/')[-1])
        structure = unit.structure if unit is not None else None
        text = ' '.join(line.text.split())
        found[line.ref] = {
            'bold': bool(structure and structure.bold), 'heading': bool(structure and structure.heading_level),
            'item': bool(BULLET.match(text) or (structure and structure.list_level is not None)),
            'marker': bool(MARKER_ONLY.match(text))}
    # A PDF may give a list marker a line of its own: the line under it is the item.
    refs = [line.ref for line in data.lines]
    for above, ref in zip(refs, refs[1:]):
        if found[above]['marker']:
            found[above]['item'] = found[ref]['item'] = True
    return found


def label_of(text):
    """The label a line opens with, folded; None when it opens with none."""
    text = ' '.join(without_form(text).split())
    match = LABELLED.match(text)
    return match.group(0)[:-1].strip().casefold() if match else None


def subhead(text):
    return ' '.join(without_form(text).split()).rstrip(':').strip().casefold() in SUBHEADS


def continues(above, text):
    """A wrapped line: the line above has no end mark and this one opens with a small letter, a digit or a mark."""
    above, text = above.rstrip(), text.lstrip()
    return bool(above) and not above.endswith(('.', ';', ':', '!', '?')) and bool(text) and not text[0].isupper()


def findings(importer, value):
    data, cue = importer.data, cues(importer.data)
    out = []
    for number, entry in enumerate(value['entries']):
        lines = entry['lines']
        own_period = (entry['header'].get('period') or {}).get('line')
        for ref in lines:
            if ref != own_period and importer.period_only(ref):
                out.append({'check': 'period', 'entry': number, 'line': ref})
        seen = {}
        for ref in lines:
            label = label_of(data.text(ref))
            if label is None:
                continue
            if label in seen:
                out.append({'check': 'label-twice', 'entry': number, 'line': ref})
            seen[label] = ref
        listed = False
        for position, ref in enumerate(lines):
            text = data.text(ref)
            if cue[ref]['item']:
                listed = True
                continue
            if not listed or LABEL_ONLY.match(' '.join(without_form(text).split())) or label_of(text) or subhead(text):
                continue
            if not (cue[ref]['bold'] or cue[ref]['heading']) and continues(data.text(lines[position - 1]), text):
                continue
            later_item = any(cue[other]['item'] for other in lines[position + 1:])
            if cue[ref]['bold'] or cue[ref]['heading']:
                out.append({'check': 'heading-inside', 'entry': number, 'line': ref})
            elif later_item and len(text) <= 60 and not text.endswith(('.', ';', ':', '!', '?', ',')) \
                    and text[:1].isupper() and len(text.split()) <= 6:
                out.append({'check': 'title-inside', 'entry': number, 'line': ref})
            elif later_item:
                out.append({'check': 'list-restart', 'entry': number, 'line': ref})
    return out


def flagged(found, strong_only=False):
    """The entries a check names, by check."""
    result = {}
    for item in found:
        if strong_only and item['check'] not in STRONG:
            continue
        result.setdefault(item['check'], set()).add(item['entry'])
    return result
