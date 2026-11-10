"""What the no-rewrite mode still changes in source wording: the form a source gives a claim (list markers, field
labels, closing punctuation) and the candidate's contacts. The words of the claim stay."""

import re


# A symbol marker needs a space or a letter after it, so "-5% затрат" keeps its sign.
_MARKER = re.compile(r'^\s*(?:[-–—―•·∙◦▪▫●○■□*‣⁃►▸✓✔]+(?:\s+|(?=[^\W\d_]))|\d{1,3}[.)]\s+)')
# A source names the kind of a claim before it ("Результат: …", "Суть проекта: …"); the template has its own field
# for that kind, so the label is form, not wording. Only known labels with a colon count: "Этап 1: анализ" stays.
_LABELS = (r'задачи|задача|обязанности|функции|результаты?|достижения?|итоги?|суть проекта|описание проекта|описание|'
    r'проект|проблема|решение|средства|инструменты|основные технологии|технологии|стек технологий|стек|роль|участие|'
    r'цель|tasks?|responsibilities|duties|results?|achievements?|outcomes?|project|description|summary|problem|'
    r'solution|tools|technologies|tech stack|stack|role|goal')
_LABEL = re.compile(rf'^\s*(?:{_LABELS})\s*:\s*', re.I)
# A dotted abbreviation keeps its last dot: "и т.д.", "к.т.н.", "M.Sc.", "etc.".
_ABBREVIATION = re.compile(r'(?:^|[\s(])(?:и\s+т\.\s?[дп]|т\.\s?[дпе]|и\s+др|и\s+пр|см|гг?|etc|inc|ltd|llc|corp|co)\.$'
    r'|(?:^|[\s(])(?:[^\W\d_]{1,2}\.){2,}$', re.I)

_EMAIL = r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+'
_PHONE = r'(?<![\w.,/-])(?:\+\s?\d[\d\s().\-–]{8,}\d|[78][\s(\-]*\d{3}[\s)\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2})(?![\w/])'
# A named service alone is ordinary text; only a link to a person's profile is a contact.
_PROFILE = (r'(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|wa\.me|linkedin\.com|vk\.com|vk\.ru|facebook\.com|fb\.com|'
    r'instagram\.com|hh\.ru|hh\.kz|career\.habr\.com)/[^\s,;)]+')
_MESSENGERS = r'(?:telegram|телеграмм?|tg|тг|skype|скайп|whatsapp|ватсап|вотсап|viber|вайбер)'
_MESSENGER = rf'\b{_MESSENGERS}\b(?:\s*:\s*@?[\w.+-]+|\s+@[\w.+-]+)'
_CONTACT = re.compile('|'.join((_EMAIL, _PROFILE, _PHONE, _MESSENGER)), re.I)
_LABELS = (r'(?:контакты|контактные\s+данные|связь|contacts?|телефон|тел\.?|моб(?:ильный|\.)?|phone|mobile|cell|'
    r'e-?mail|почта|эл\.\s*почта|электронная\s+почта)')
_DANGLING = re.compile(rf'(?:^|(?<=[\s(,;]))(?:{_LABELS}|{_MESSENGERS})\s*[:\-–—]?\s*(?=$|[,;|/)])', re.I)
_SEPARATORS = re.compile(r'\s*([,;|/])(?:\s*[,;|/])+')
_EDGE = ' \t,;|/:-–—'


def without_form(text):
    """The lines of the text without their list markers and field labels; a line of nothing but a label goes too.
    A marker may follow a label ("Задачи: - разработка") and a label a marker ("- Результат: …")."""
    lines = []
    for line in text.split('\n'):
        previous = None
        while previous != line:
            previous, line = line, _LABEL.sub('', _MARKER.sub('', line))
        if line.strip() or not lines:
            lines.append(line)
    while len(lines) > 1 and not lines[0].strip():
        lines.pop(0)
    result = '\n'.join(lines)
    return result if result.strip() else text


def listed(pointer):
    """Whether a pointer names an item of a list (`/0/tasks/1/value`, `/items/1`) rather than a text field."""
    return any(token.isdecimal() for token in pointer.strip('/').split('/')[1:])


def list_item_text(text):
    """A list item without its source marker and closing punctuation; the template draws its own bullets and closing
    marks (D152)."""
    lines = without_form(text).split('\n')
    last = lines[-1].rstrip()
    if not last.endswith(('...', '…')) and not _ABBREVIATION.search(last):
        last = last.rstrip(' .;,')
    lines[-1] = last
    result = '\n'.join(lines)
    return result if result.strip() else text


def without_contacts(text):
    """Text without phones, mail, messengers and profile links; a line left with only its label goes too."""
    kept = []
    for line in text.split('\n'):
        cleaned = _CONTACT.sub('', line)
        if cleaned == line:
            kept.append(line)
            continue
        cleaned = _SEPARATORS.sub(r'\1 ', _DANGLING.sub('', cleaned)).strip(_EDGE)
        if any(character.isalnum() for character in cleaned):
            kept.append(cleaned)
    return '\n'.join(kept)


def clean_source_wording(text, pointer):
    """Source wording as the resume shows it; `pointer` tells a list item from a text field."""
    cleaned = without_contacts(text)
    if not cleaned.strip():
        return cleaned
    return list_item_text(cleaned) if listed(pointer) else without_form(cleaned)
