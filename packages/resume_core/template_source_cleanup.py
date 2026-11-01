"""What the no-rewrite mode still changes in source wording: list punctuation and the candidate's contacts."""

import re


# A symbol marker needs a space or a letter after it, so "-5% затрат" keeps its sign.
_MARKER = re.compile(r'^\s*(?:[-–—―•·∙◦▪▫●○■□*‣⁃►▸✓✔]+(?:\s+|(?=[^\W\d_]))|\d{1,3}[.)]\s+)')
_ABBREVIATION = re.compile(r'(?:^|[\s(])(?:и\s+т\.\s?[дп]|т\.\s?[дпе]|и\s+др|и\s+пр|см|гг?|etc|inc|ltd|llc|corp|co)\.$', re.I)

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


def list_item_text(text):
    """A list item without its source marker and closing punctuation; the template draws its own bullets."""
    lines = [_MARKER.sub('', line) for line in text.split('\n')]
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
    listed = any(token.isdecimal() for token in pointer.strip('/').split('/')[1:])
    return list_item_text(cleaned) if listed and cleaned.strip() else cleaned
