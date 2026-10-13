"""Recognize explicit calendar dates in source wording without guessing precision."""

import calendar
import re

from .models.contracts import PartialDate


MONTHS = (
    ("январь", "января", "янв", "january", "jan"),
    ("февраль", "февраля", "фев", "февр", "february", "feb"),
    ("март", "марта", "мар", "march", "mar"),
    ("апрель", "апреля", "апр", "april", "apr"),
    ("май", "мая", "may"),
    ("июнь", "июня", "июн", "june", "jun"),
    ("июль", "июля", "июл", "july", "jul"),
    ("август", "августа", "авг", "august", "aug"),
    ("сентябрь", "сентября", "сент", "сен", "september", "sep", "sept"),
    ("октябрь", "октября", "окт", "october", "oct"),
    ("ноябрь", "ноября", "ноя", "нояб", "november", "nov"),
    ("декабрь", "декабря", "дек", "december", "dec"),
)
MONTH_NUMBER = {name: index for index, names in enumerate(MONTHS, 1) for name in names}
MONTH_PATTERN = "|".join(re.escape(name) for name in sorted(MONTH_NUMBER, key=len, reverse=True))
NAMED_DATE = re.compile(rf"(?<![\w.\d])(?:(?P<day>[0-9]{{1,2}})\s+)?(?P<month>{MONTH_PATTERN})\.?\s+(?P<year>[0-9]{{4}})(?![\w.\d])", re.I)


def observed_named_date(value: PartialDate, text: str) -> bool:
    for match in NAMED_DATE.finditer(text):
        year = int(match["year"])
        month = MONTH_NUMBER[match["month"].casefold()]
        day = int(match["day"]) if match["day"] else None
        if year < 1 or day is not None and not 1 <= day <= calendar.monthrange(year, month)[1]:
            continue
        if (value.year, value.month, value.day) == (year, month, day):
            return True
    return False
