"""Job order and date warnings in Facts (D182): the rows in page order, a card's move by one place in its list, the sort
newest first, and the flags «Стоит не по дате» and «Пересекается с …». A warning never refuses a change."""

from ..fields import inline_groups, set_text
from ..importing.template_builtin_admission import unknown
from ..models.rich_document import FactFieldSpan
from ..models.rich_facts import EmploymentRecord, WorkingPeriod
from ..models.template_document import BoundLink, TemplateSectionBlock
from .template_panel_creation import _recency

_PRECISIONS = ('year', 'month', 'day')


def _jobs(project):
    return {record.id: record for record in project.facts.records if record.kind == 'employment'}


def job_lists(project):
    """(parent id, cards) of each list of job cards: siblings in a row that show one job each in one view. A heading, a
    line or a card of another view ends a list, so a move never crosses a section title or enters a compact list."""
    jobs, found = _jobs(project), []

    def card(block):
        return (isinstance(block, TemplateSectionBlock) and block.props.record_id in jobs
            and block.presentation is not None)

    def visit(parent, items):
        run = []
        for block in items:
            if card(block) and (not run or run[-1].presentation.view_key == block.presentation.view_key):
                run.append(block)
                continue
            if run:
                found.append((parent, run))
            run = [block] if card(block) else []
            if not run:
                visit(block.id, block.children)
        if run:
            found.append((parent, run))
    for region in project.document.regions:
        visit(region.id, region.blocks)
    return found


def job_order(project):
    """The job ids in the page's reading order, then the jobs the page does not show, in record order (J1)."""
    jobs, seen = _jobs(project), {}

    def note(identifier):
        if identifier in jobs:
            seen.setdefault(identifier, None)

    def spans(content):
        for span in content:
            if isinstance(span, FactFieldSpan):
                note(span.record_id)
            elif isinstance(span, BoundLink):
                for value in (span.label_binding, span.url_binding):
                    if value is not None:
                        note(value.record_id)
                spans(span.content)
    for block in project.document.blocks():
        note(getattr(block.props, 'record_id', None))
        for _container, content in inline_groups(block):
            spans(content)
        for value in block.provenance:
            note(getattr(value, 'record_id', None))
    return [*seen, *(identifier for identifier in jobs if identifier not in seen)]


def _flagged(project, lists=None):
    """The jobs whose card has an older dated card as its nearest dated card above it in its list (J4-b)."""
    jobs, found = _jobs(project), set()
    for _parent, cards in job_lists(project) if lists is None else lists:
        last = None
        for block in cards:
            key = _recency(jobs[block.props.record_id])
            if key is None:
                continue
            if last is not None and last < key:
                found.add(block.props.record_id)
            last = key
    return found


def _point(field):
    return field.value if field.status == 'known' and field.value is not None else None


def _bounds(period):
    """(start, end) of a period for an overlap, end None when it is current; None without a start, or without an end that
    is not current. Text Python cannot read as a date has no value, so it gives no warning."""
    start = _point(period.start)
    if start is None:
        return None
    if period.present.value is True:
        return start, None
    end = _point(period.end)
    if end is None or _before(end, start):
        return None
    return start, end


def _before(first, second):
    """Whether one date is before the other, at the coarser precision of the two."""
    depth = min(_PRECISIONS.index(first.precision), _PRECISIONS.index(second.precision)) + 1
    return (first.year, first.month, first.day)[:depth] < (second.year, second.month, second.day)[:depth]


def periods_overlap(first, second):
    """Whether two periods share more than the unit where they touch (J5-a)."""
    one, two = _bounds(first), _bounds(second)
    if one is None or two is None:
        return False
    return (two[1] is None or _before(one[0], two[1])) and (one[1] is None or _before(two[0], one[1]))


def _overlaps(record, others):
    """(other job, its period) for each period of another job that overlaps a period of this one, in the given order."""
    return [(other, period) for other in others if other.id != record.id for period in other.periods
        if any(periods_overlap(own, period) for own in record.periods)]


def job_warnings(project):
    """By job, the plan's move flags and warnings: whether its card can go up or down, «Стоит не по дате» and the jobs
    it overlaps in row order; and whether «Расставить по дате» has something to do."""
    jobs, order = _jobs(project), job_order(project)
    lists = job_lists(project)
    cards = {}
    for _parent, items in lists:
        for index, block in enumerate(items):
            cards.setdefault(block.props.record_id, []).append((index, len(items)))
    flagged = _flagged(project, lists)
    ordered = [jobs[identifier] for identifier in order]
    result = {}
    for identifier in order:
        value = {}
        # A job with one card moves it; one off the page, in a compact list or with two cards has no arrows.
        if len(cards.get(identifier, [])) == 1:
            index, size = cards[identifier][0]
            value['move'] = {'up': index > 0, 'down': index < size - 1}
        if identifier in flagged:
            value['outOfOrder'] = True
        overlaps = list(dict.fromkeys(other.id for other, _period in _overlaps(jobs[identifier], ordered)))
        if overlaps:
            value['overlaps'] = overlaps
        result[identifier] = value
    return result, order, bool(flagged)


def _move_steps(parent, items, order):
    """move_block steps that put the given blocks of a sibling list in this order, each block moved at most once."""
    steps, current = [], [block.id for block in items]
    positions = {block.id: index for index, block in enumerate(items)}
    start = min(positions[block.id] for block in order)
    for offset, block in enumerate(order):
        index = start + offset
        if current[index] != block.id:
            steps.append({'kind': 'move_block', 'blockId': block.id, 'beforeRevision': block.revision, 'parentId': parent,
                'afterId': current[index - 1] if index else None})
            current.remove(block.id)
            current.insert(index, block.id)
    return steps, current


def _siblings(document, parent):
    from .mutations import parent_items
    return parent_items(document, parent)[0]


def _reorder(project, plans):
    """(candidate project, steps) for new card orders: (parent id, cards, new order) each."""
    candidate, steps = project.model_copy(deep=True), []
    for parent, _cards, order in plans:
        items = _siblings(project.document, parent)
        moves, ids = _move_steps(parent, items, order)
        steps += moves
        target = _siblings(candidate.document, parent)
        by_id = {block.id: block for block in target}
        target[:] = [by_id[identifier] for identifier in ids]
    return candidate, steps


def move_job(project, command):
    """(candidate, steps) of one job card's move by one place in its list (J3); refused only where the plan offers none."""
    direction = command.values.get('direction')
    found = [(parent, cards, index) for parent, cards in job_lists(project) for index, block in enumerate(cards)
        if block.props.record_id == command.record_id]
    if command.record_id not in _jobs(project) or direction not in {'up', 'down'} or len(found) != 1:
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    parent, cards, index = found[0]
    other = index - 1 if direction == 'up' else index + 1
    if not 0 <= other < len(cards):
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    order = list(cards)
    order[index], order[other] = order[other], order[index]
    return _reorder(project, [(parent, cards, order)])


def sort_jobs(project):
    """(candidate, steps) that sort each list's cards newest first, stable; cards with no known date go last in their order
    (J4-d). None when every list is in order already."""
    jobs, plans = _jobs(project), []
    for parent, cards in job_lists(project):
        dated = [block for block in cards if _recency(jobs[block.props.record_id]) is not None]
        dated.sort(key=lambda block: _recency(jobs[block.props.record_id]), reverse=True)
        order = dated + [block for block in cards if _recency(jobs[block.props.record_id]) is None]
        if [block.id for block in order] != [block.id for block in cards]:
            plans.append((parent, cards, order))
    if not plans:
        return None
    return _reorder(project, plans)


def _form_record(project, record_id, values):
    """A copy of the job with the form's period values, or a new job of one period for an add; nothing is saved."""
    if record_id is None:
        if not set(values) <= {'start', 'end', 'present'}:
            raise ValueError('DATE_CHECK_INVALID')
        period = WorkingPeriod(id='form-period', revision=1, start=unknown(), end=unknown(),
            present={**unknown(), 'value': False, 'status': 'known'}, evidence=[])
        record = EmploymentRecord(id='form-job', kind='employment', revision=1, origin='user', evidence=[],
            employer=unknown(), role=unknown(), periods=[period])
        values = {'period:form-period:' + key: value for key, value in values.items()}
    else:
        original = _jobs(project).get(record_id)
        if original is None:
            raise ValueError('DATE_CHECK_INVALID')
        record = original.model_copy(deep=True)
    keys = {'period:' + period.id + ':' + name for period in record.periods for name in ('start', 'end', 'present')}
    if not set(values) <= keys:
        raise ValueError('DATE_CHECK_INVALID')
    for key, value in values.items():
        set_text(record, key, value)
    return record


def check_dates(project, record_id, values):
    """The warnings the date dialog's values would give, before Save (J6): the other jobs' periods they overlap and the
    periods whose end is before their start. It reads the project and writes nothing."""
    from .template_panel_lines import period_text
    record = _form_record(project, record_id, values)
    jobs = _jobs(project)
    warnings = []
    for period in record.periods:
        start, end = _point(period.start), _point(period.end)
        if period.present.value is not True and start is not None and end is not None and _before(end, start):
            warnings.append({'kind': 'reversed', 'periodId': None if record_id is None else period.id})
    for other, period in _overlaps(record, [jobs[identifier] for identifier in job_order(project)]):
        warnings.append({'kind': 'overlap', 'recordId': other.id, 'period': period_text(period, project.template_package)})
    return {'schemaVersion': 1, 'warnings': warnings}
