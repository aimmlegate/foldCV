"""A period read from its wording in a CV. Month stems in Russian and English; no model call."""

import re

MONTHS = {1: ('январ', 'янв', 'jan'), 2: ('феврал', 'фев', 'feb'), 3: ('март', 'мар', 'mar'), 4: ('апрел', 'апр', 'apr'),
    5: ('май', 'мая', 'may'), 6: ('июн', 'jun'), 7: ('июл', 'jul'), 8: ('август', 'авг', 'aug'),
    9: ('сентябр', 'сен', 'sep'), 10: ('октябр', 'окт', 'oct'), 11: ('ноябр', 'ноя', 'nov'), 12: ('декабр', 'дек', 'dec')}
PRESENT = re.compile(r'настоящ|(?<!\w)н\.\s?вр?\b|(?<!\w)н\s?/\s?в\b|наст\.|сих\s+пор|сей\s+день|наши\s+дни|сейчас|текущ|'
    r'present|now|current|today|ongoing', re.IGNORECASE)
DATE = re.compile(r'(?P<name>[^\W\d_]{3,})\.?\s*(?P<named>(?:19|20)\d{2})(?!\d)|'
    r'(?<![\d.])(?P<month>0?[1-9]|1[0-2])\s*[./-]\s*(?P<numbered>(?:19|20)\d{2})(?!\d)|'
    r'(?<![\d.])(?P<first>(?:19|20)\d{2})[-./](?P<later>0[1-9]|1[0-2])(?![\d.])|'
    r'(?<![\d.])(?P<year>(?:19|20)\d{2})(?!\d)')
DASHES = '‐‑‒–—―-'
# A range left open at the end of its line: a dash or a word for «to», then at most the month of its end.
OPEN = re.compile(r'(?:[' + DASHES + r']|\b(?:по|до|to|till|until))\s*(?P<month>[^\W\d_]{3,}\.?)?\s*$', re.IGNORECASE)
LEAD = re.compile(r'^[\s' + DASHES + r']*(?:(?:по|до|to|till|until)\s+)?', re.IGNORECASE)
YEAR_FIRST = re.compile(r'(?:19|20)\d{2}(?!\d)')


def _month(name):
    folded = name.casefold()
    return next((number for number, stems in MONTHS.items() if any(folded.startswith(stem) for stem in stems)), None)


def _date(year, month):
    # As the templates ask the model to write it (D135): MM.YYYY, or YYYY when the source states only the year.
    return {'raw': f'{month:02d}.{year}' if month else str(year), 'year': year, 'month': month}


def parse_period(text):
    """The template's period object read from a period's wording, or None when no date reads from it: the first date
    starts it, a later one ends it, and a word for now after the start makes it ongoing."""
    dates = []
    for found in DATE.finditer(text):
        if found['named']:
            dates.append((found.start(), _date(int(found['named']), _month(found['name']))))
        elif found['numbered']:
            dates.append((found.start(), _date(int(found['numbered']), int(found['month']))))
        elif found['first']:
            dates.append((found.start(), _date(int(found['first']), int(found['later']))))
        else:
            dates.append((found.start(), _date(int(found['year']), None)))
    if not dates:
        return None
    start, ongoing = dates[0][1], PRESENT.search(text[dates[0][0]:]) is not None
    end = None if ongoing or len(dates) < 2 else dates[1][1]
    if end is not None and (end['year'], end['month'] or 0) < (start['year'], start['month'] or 0):
        return None
    return {'raw': ' '.join(text.split()), 'start': start, 'end': end, 'ongoing': ongoing}


def wraps(first, second):
    """Whether two lines state one period: the first leaves its range open at its end («март 2025 —», «июнь 2022 —
    февраль») and the second starts with what ends it (a date, a year, a word for now). A narrow column wraps a
    period so; read apart, its end is lost."""
    opened, found = parse_period(first), OPEN.search(first)
    if opened is None or opened['end'] is not None or opened['ongoing'] or found is None:
        return False
    rest = LEAD.sub('', second, count=1)
    if found['month']:
        if _month(found['month']) is None or not YEAR_FIRST.match(rest):
            return False
    else:
        date = DATE.match(rest)
        if (date is None or date['named'] and _month(date['name']) is None) and not PRESENT.match(rest):
            return False
    # Two dates on the second line are a period of its own.
    if len(list(DATE.finditer(second))) > 1:
        return False
    whole = parse_period(first + ' ' + second)
    return whole is not None and (whole['end'] is not None or whole['ongoing'])
