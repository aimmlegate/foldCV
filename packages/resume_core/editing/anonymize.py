"""The anonymized export (D186): a copy of the page for one export only, with the candidate's short name and without
contacts. Facts, the saved document and the editor page do not change; nothing here writes the project. It is an export
variant the user asks for by name, not a filter of the import or the editor (D073 stays)."""

import re

from ..fields import inline_groups
from ..models.rich_document import FactFieldSpan, Hyperlink
from ..models.template_document import BoundLink, FieldOccurrence, PresentedText, TemplateSectionBlock

# A Russian or a Latin patronymic: Сергеевич, Ивановна, Ильинична, Sergeevich, Ivanovna; the Turkic оглы and кызы.
PATRONYMIC = re.compile(r'(?:о|е)вич$|(?:о|е)вна$|ич$|ична$|инична$|оглы$|кызы$|(?:o|e)vich$|(?:o|e)vna$|ichna$|ogly$|kyzy$',
                        re.IGNORECASE)
EMAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
PHONE = re.compile(r'(?<![\w+.])\+?\d[\d\s()\-]{7,}\d(?![\w.])')
URL = re.compile(r'(?:(?:https?://|www\.)[^\s,;()<>]+|(?<![@\w.-])(?:[a-z0-9-]+\.)+(?:com|ru|io|me|dev|org|net|app|pro|info|site|'
                 r'tech|ee|to|so|ai|xyz|su|рф)(?:/[^\s,;()<>]*)?)', re.IGNORECASE)
HANDLE = re.compile(r'(?<![\w@.])@[A-Za-z][\w.]{2,}')
MESSENGERS = re.compile(r'\b(?:telegram|tg|телеграм\w*|whatsapp|ватсап\w*|skype|скайп\w*|signal|viber|вайбер\w*|discord|'
                        r'icq|jabber|wechat|line|messenger)\b', re.IGNORECASE)
LABEL = re.compile(r'\b(?:тел(?:ефон)?|моб(?:ильный)?|phone|mobile|tel|cell|e-?mail|почта|эл\.?\s*почта|mail|telegram|tg|'
                   r'телеграм\w*|whatsapp|ватсап\w*|skype|скайп\w*|signal|viber|вайбер\w*|discord|github|gitlab|bitbucket|'
                   r'linkedin|линкедин|hh|habr|хабр|сайт|site|web|website|blog|блог|portfolio|портфолио|профиль|profile|'
                   r'контакты|contacts?|vk|вконтакте|facebook|instagram|twitter)\b\.?', re.IGNORECASE)
SEPARATORS = re.compile(r'[\s,;:|•·/\\()\[\]—–\-]+')
# The hosts of personal profiles and messengers: code hosts, professional and social networks, job and portfolio sites.
PROFILES = ('github.com', 'gitlab.com', 'bitbucket.org', 'linkedin.com', 'hh.ru', 'career.habr.com', 'habr.com', 'vk.com',
            'facebook.com', 'fb.com', 'instagram.com', 'twitter.com', 'x.com', 't.me', 'telegram.me', 'wa.me', 'whatsapp.com',
            'skype.com', 'viber.com', 'signal.me', 'behance.net', 'dribbble.com', 'medium.com', 'dev.to', 'stackoverflow.com',
            'leetcode.com', 'kaggle.com', 'codepen.io', 'superjob.ru', 'rabota.ru', 'zarplata.ru', 'linktr.ee', 'about.me',
            'ok.ru', 'tiktok.com', 'youtube.com', 'gist.github.com', 'huggingface.co', 'npmjs.com', 'pypi.org/user',
            'getmatch.ru', 'djinni.co', 'upwork.com', 'freelance.ru', 'fl.ru', 'kwork.ru', 'notion.site', 'tilda.ws',
            'carrd.co', 'github.io', 'gitlab.io')
LEFT_OUT = 'Скрываем: телефон, почту, мессенджеры, ссылки на профили.'


def short_name(full):
    """The first name and the first letter of the family name (A3-b): «Иван Петров» and «Петров Иван Сергеевич» give
    «Иван П.». One word stays; another shape gives the first word and the first letter of the last word."""
    words = (full or '').split()
    if not words:
        return ''
    if len(words) == 1:
        return words[0]
    first, family = words[0], words[-1]
    if len(words) == 3 and PATRONYMIC.search(words[2]) and not PATRONYMIC.search(words[1]):
        first, family = words[1], words[0]
    return f'{first} {family[0].upper()}.'


def family_name(full):
    """The family name the short name drops, for the notice of a sentence that names it; '' for one word."""
    words = (full or '').split()
    if len(words) < 2:
        return ''
    if len(words) == 3 and PATRONYMIC.search(words[2]) and not PATRONYMIC.search(words[1]):
        return words[0]
    return words[-1]


def _host(url):
    value = re.sub(r'^(?:https?://)?(?:www\.)?', '', url.lower())
    return value


def personal_url(url):
    """Whether a link goes to a personal profile or a messenger."""
    value = _host(url)
    return any(value == host or value.startswith(host + '/') or value.startswith(host + '?') or ('.' + host) in value.split('/')[0]
               or value.split('/')[0].endswith('.' + host) for host in PROFILES)


def _contacts(text):
    """(start, end, kind) of each contact in a text: e-mail, phone, personal link, messenger handle."""
    found = []
    for match in EMAIL.finditer(text):
        found.append((match.start(), match.end(), 'почта'))
    taken = lambda start, end: any(start < other_end and other_start < end for other_start, other_end, _kind in found)
    for match in URL.finditer(text):
        if not taken(*match.span()) and personal_url(match.group(0)):
            found.append((match.start(), match.end(), 'ссылка на профиль'))
    for match in PHONE.finditer(text):
        digits = sum(char.isdigit() for char in match.group(0))
        years = [group for group in re.findall(r'\d+', match.group(0)) if len(group) == 4 and group[:2] in {'19', '20'}]
        # A phone has 10 to 15 digits; a year range, a version or a date has fewer, or two years in a row.
        if 10 <= digits <= 15 and len(years) < 2 and not taken(*match.span()):
            found.append((match.start(), match.end(), 'телефон'))
    # A handle is a contact where the text names a messenger or holds another contact; «@Override» in code text stays.
    if MESSENGERS.search(text) or found:
        for match in HANDLE.finditer(text):
            if not taken(*match.span()):
                found.append((match.start(), match.end(), 'мессенджер'))
    return sorted(found)


def contact_only(text):
    """Whether a line holds only contact data with its labels and separators (A4-c)."""
    found = _contacts(text)
    if not found:
        return False
    rest = text
    for start, end, _kind in reversed(found):
        rest = rest[:start] + ' ' + rest[end:]
    rest = LABEL.sub(' ', MESSENGERS.sub(' ', rest))
    return not SEPARATORS.sub('', rest)


def _without(text, found):
    """The text without the found parts, its separators tidied."""
    for start, end, _kind in reversed(found):
        text = text[:start] + text[end:]
    text = re.sub(r'\s*([,;:|•·])\s*(?=[,;:|•·]|$)', '', text)
    text = re.sub(r'\(\s*\)|\[\s*\]', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+([,.;:!?])', r'\1', text)
    return text.strip(' ,;|•·') if text.strip() else ''


def _quote(text, start=0, end=None, size=60):
    end = len(text) if end is None else end
    left = max(0, start - (size - (end - start)) // 2)
    piece = text[left:left + size].strip()
    return ('…' if left > 0 else '') + piece + ('…' if left + size < len(text) else '')


def _span_text(span):
    if isinstance(span, (Hyperlink, BoundLink)):
        return ''.join(getattr(child, 'text', '') for child in span.content)
    return getattr(span, 'text', '')


def _url(span):
    return getattr(span, 'url', None) or getattr(span, 'href', None) or ''


def _line_text(content):
    return ''.join(_span_text(span) for span in content)


def _links_only(content):
    """A line of the candidate's own links: links, and literal separators between them."""
    links = [span for span in content if isinstance(span, (Hyperlink, BoundLink))]
    rest = ''.join(_span_text(span) for span in content if not isinstance(span, (Hyperlink, BoundLink)))
    return bool(links) and not SEPARATORS.sub('', LABEL.sub('', rest))


def _subtree(block):
    yield block
    for child in block.children:
        yield from _subtree(child)


def _tops(document, match):
    found = []

    def visit(items):
        for block in items:
            if match(block):
                found.append(block)
            else:
                visit(block.children)
    for region in document.regions:
        visit(region.blocks)
    return found


def _candidate(project):
    record = next((value for value in project.facts.records if value.kind == 'candidate'), None)
    return record.name.raw_text if record is not None else ''


def default_name(project):
    """The dialog's start value: the name the user confirmed for the present full name, else the proposal (A3-c)."""
    full = _candidate(project)
    kept = project.anonymized_name
    if kept is not None and kept.full_name == full:
        return kept.name
    return short_name(full)


def anonymized(project, name):
    """(document copy, notices) of the anonymized export: `name` in each place of the candidate's name field (empty:
    that line goes), contacts out, the blocks of the candidate's own links out whole. The project is not changed; the
    hidden store (D185) is neither read nor changed, so a hidden block stays hidden."""
    document = project.document.model_copy(deep=True)
    full = _candidate(project)
    family = family_name(full)
    candidate_ids = {record.id for record in project.facts.records if record.kind == 'candidate'}
    jobs = {record.id for record in project.facts.records if record.kind == 'employment'}
    notices, removed = [], set()

    def name_span(span):
        return isinstance(span, FactFieldSpan) and span.record_id in candidate_ids and getattr(span, 'field_key', None) == 'name'

    def in_job(path):
        return any(isinstance(block, TemplateSectionBlock) and block.props.record_id in jobs for block in path)

    def visit(block, path):
        for _container, content in inline_groups(block):
            text = _line_text(content)
            if not text.strip():
                continue
            names = [span for span in content if name_span(span)]
            if names:
                for span in names:
                    span.text = name
                if not name and not _line_text(content).strip():
                    removed.add(block.id)
                    return
            links = [span for span in content if isinstance(span, (Hyperlink, BoundLink))]
            personal = [span for span in links if personal_url(_url(span)) or _contacts(_span_text(span))]
            if contact_only(text) or (personal and not SEPARATORS.sub('', LABEL.sub('', ''.join(
                    _span_text(span) for span in content if span not in personal)))):
                removed.add(block.id)
                return
            kept = []
            for span in content:
                if span in personal:
                    notices.append({'kind': 'contact', 'quote': _quote(text)})
                    continue
                if isinstance(span, (Hyperlink, BoundLink)) and not in_job(path):
                    # A link that is no profile and stands outside a job: its text stays, its address goes (A4-e).
                    notices.append({'kind': 'link', 'quote': _quote(_span_text(span))})
                    kept.append(PresentedText(type='text', text=_span_text(span), styles={}, presentation=getattr(
                        span, 'presentation', None) or block.presentation))
                    continue
                if isinstance(span, (PresentedText, FieldOccurrence)) and not name_span(span):
                    found = _contacts(span.text)
                    if found:
                        notices.append({'kind': 'contact', 'quote': _quote(span.text, found[0][0], found[0][1])})
                        span.text = _without(span.text, found)
                        if not span.text:
                            continue
                    if family and re.search(r'(?<!\w)' + re.escape(family) + r'(?!\w)', span.text):
                        notices.append({'kind': 'family', 'quote': _quote(span.text)})
                kept.append(span)
            content[:] = kept
        for child in list(block.children):
            visit(child, [*path, block])

    # A4-b first: a block of the candidate's own links goes whole, heading included: each content line of its view holds
    # only links or only contact data. The page header (the candidate's name) is never one.
    views = {}
    for block in _tops(document, lambda value: value.presentation is not None and value.presentation.view_key):
        views.setdefault(block.presentation.view_key, []).append(block)
    whole = set()
    for view, tops in views.items():
        lines = [value for top in tops for value in _subtree(top) if value.type != 'heading'
                 and any(_line_text(content).strip() for _container, content in inline_groups(value))]
        if lines and all(any(_links_only(content) or contact_only(_line_text(content)) for _container, content
                             in inline_groups(value)) for value in lines) and not any(
                name_span(span) for value in lines for _container, content in inline_groups(value) for span in content):
            whole.update(top.id for top in tops)
    removed |= whole
    for region in document.regions:
        for block in list(region.blocks):
            if block.id not in whole:
                visit(block, [])
    for region in document.regions:
        region.blocks = _pruned(region.blocks, removed)
    return document, notices


def _pruned(items, removed):
    kept = []
    for block in items:
        if block.id in removed:
            continue
        block.children = _pruned(block.children, removed)
        kept.append(block)
    return kept


def page_changes(before, after):
    """For the print copy (A5-c): the top blocks the anonymized copy left out, and the plain text of each block whose
    text changed."""
    from .dependencies import placements
    old = {block.id: block for block in before.blocks()}
    new = {block.id: block for block in after.blocks()}
    parents = placements(before)
    # Only the top block of a removed subtree: its parent stays on the anonymized page (or is a region).
    removed = [identifier for identifier in old if identifier not in new and (parents[identifier][0] in new
               or parents[identifier][0] not in old)]
    texts = {}
    for identifier, block in new.items():
        groups = [(_line_text(content)) for _container, content in inline_groups(block)]
        previous = [(_line_text(content)) for _container, content in inline_groups(old[identifier])]
        if groups != previous:
            texts[identifier] = '\n'.join(groups)
    return removed, texts


def preview(project, name=None):
    """What the dialog shows and the print copy needs: the name, the line of what is left out, the places to check, and
    the page changes."""
    value = default_name(project) if name is None else ' '.join(name.split())
    document, notices = anonymized(project, value)
    removed, texts = page_changes(project.document, document)
    unique, seen = [], set()
    for notice in notices:
        key = (notice['kind'], notice['quote'])
        if key not in seen:
            seen.add(key)
            unique.append(notice)
    return {'schemaVersion': 1, 'name': value, 'proposal': short_name(_candidate(project)), 'leftOut': LEFT_OUT,
            'notices': unique, 'removed': removed, 'texts': texts}
