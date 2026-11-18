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


# A name: a word with a capital letter that does not open a sentence, or with a capital inside (PostgreSQL).
NAME = re.compile(r"[^\W\d_][\w.+#-]*")
OPENS = re.compile(r'(?:^|[.!?:;]\s+|\n\s*|[«"(]\s*)$')


def names(text):
    """The words of a text that read as names, folded: a capital letter not at the start of a sentence, or inside the
    word."""
    found = set()
    for match in NAME.finditer(text):
        word = match.group().rstrip('.-')
        inner = any(char.isupper() for char in word[1:])
        if inner or word[:1].isupper() and not OPENS.search(text[:match.start()]):
            found.add(word.casefold())
    return found


CYRILLIC_WORD = re.compile(r'[а-яё]+')


def unknown_names(text, known):
    """The names of a text that the known words do not hold; known holds folded words. A name joined of known words
    («Python-разработчик») is known, and so is a Russian name in another case («в Томском» for «Томский»): it shares
    its stem with a known word. A name in Latin letters is known only as it is written."""
    def held(part):
        if part in known:
            return True
        stem = part[:max(3, len(part) - 3)]
        return bool(CYRILLIC_WORD.fullmatch(part)) and any(word.startswith(stem) for word in known)
    return sorted(name for name in names(text) if not all(held(part) for part in name.split('-') if part))
