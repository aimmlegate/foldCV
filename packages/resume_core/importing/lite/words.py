"""The words of a source line that a document must show, for the check that no text is lost."""

import re

from packages.resume_core.importing.template_map import parse_period
from packages.resume_core.template_source_cleanup import without_contacts, without_form

# Numbers split at their dots and commas: the document writes a date as 04.2023, the source as «Апрель 2023».
WORD = re.compile(r'[^\W\d_]{3,}|\d+', re.U)
# A date line's duration («(1 год 6 месяцев)») is date form, as its month names are.
DURATION = re.compile(r'\(\s*\d[^)]*\)|\b\d+(?:[.,]\d+)?\s*(?:год[а-я]*|лет|месяц[а-я]*|мес\.?|years?|yrs?|months?|mos?)\b', re.I)
MONTH_OR_NOW = re.compile(r'^(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр|янв|фев|мар|апр|'
                          r'авг|сен|окт|ноя|дек|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|настоящ|наст|время|сейчас|'
                          r'текущ|present|now|current|today|ongoing|till|until)', re.I)
# A field label before a value is form: «Стек проекта: …».
LABEL = re.compile(r'^\s*[^\W\d_][^:\n]{0,28}:\s*')


def words(text):
    return set(WORD.findall(' '.join(str(text).split()).casefold().replace('ё', 'е')))


def line_words(text):
    content = LABEL.sub('', without_contacts(without_form(text)), count=1)
    if parse_period(content) is not None:
        content = DURATION.sub(' ', content)
        return {word for word in words(content) if not MONTH_OR_NOW.match(word)}
    return words(content)
