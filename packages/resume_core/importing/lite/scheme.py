"""One lite import of a CV.

Calls: one map call, then side by side one call per side block that has lines and one per map entry; the role
branch's blocks start when identity answers; one narrow question for each entry a code check names; one call that
writes the blocks the CV has no text for. A block or an entry that gave no reply is asked once more. No review, no
repair of a value. Code: the map's checks (parse_map), the lines no entry
holds placed, long text copied and joined, every short value found by exact match in its own lines, periods and years
read, every ref and value checked, a value that fails dropped with a note, every uncited content line of an entry
added to it as one more plain bullet, and every line whose words no field took kept as «other». The result is each
block's content with the source spans of every value."""

from concurrent.futures import ThreadPoolExecutor
import re
import time

from . import custom as C
from . import prompts as P
from .lines import CV
from .tech import named_in, source_spelling
from packages.resume_core.technologies import resolve_technology
from .words import line_words, unknown_names, words

from packages.resume_core.importing.template_import import ACCOUNT_STOP
from packages.resume_core.importing.template_map import parse_map, parse_period, uncovered
from packages.resume_core.template_source_cleanup import without_form

SIDE = ['identity', 'focus', 'education', 'courses', 'location', 'languages', 'opensource', 'portfolio']
BRANCH = {'technical': ['programming', 'data_and_tools', 'infrastructure'], 'skills_and_tools': ['key_skills', 'role_tools']}
SKILLS_FAMILIES = {'system_analyst', 'business_analyst', 'tester', 'designer'}
BULLET = re.compile('^(?:[•●○◦▪▫■□►▸‣⁃∙·*✓✔➢❖][\\s​‌‍⁠﻿]*|[-–]\\s+)')
LABELLED = re.compile(r'^[^\W\d_][^:\n]{0,28}:')
DASHES = re.compile('[-‐-―]')
QUOTES = re.compile('["«»“”„\']')
YEAR = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)')
# A line that is only a label («Обязанности:») is form, as the gate's own label pattern reads it.
LABEL_ONLY = re.compile(r'^[^\W\d_][^:\n]{0,60}:$')
# The scheme's parts, all on. They stay named so that a part can be told apart in the code below: no map repair
# call (code places the lines no entry holds); the fixes by code (page lines, employer details, a header-only piece,
# an entry's own period, a part-copied line, «other»); and what shapes a request (the narrow question, the map rule
# for a line with two header values, focus lines given to the technology lists).
NO_REPAIR = FIXES = L3 = True
# Sub-heading words of one entry: a line of these alone opens a list, with or without a colon.
SUBHEADS = {'обязанности', 'достижения', 'задачи', 'результаты', 'результат', 'стек', 'технологии', 'роль', 'команда',
            'описание', 'функции', 'responsibilities', 'achievements', 'results', 'tasks', 'duties', 'stack',
            'tech stack', 'technologies', 'role', 'team', 'description', 'key results', 'highlights'}
ABBREVIATIONS = {'inc', 'ltd', 'corp', 'co', 'llc', 'гг', 'др', 'пр', 'т.д', 'т.п', 'etc', 'jr', 'sr'}
ZONE_GAP = 6   # header lines of one job stand at most this many lines apart
OWN_LINES = ('identity', 'education', 'courses', 'location', 'languages', 'opensource', 'portfolio')
# A written block (prompts.WRITE): a number in it must stand in the CV, and it is a few sentences, not a page.
NUMBER = re.compile(r'\d+')
WRITTEN_LIMIT, WRITTEN_ITEM, WRITTEN_LINES = 1500, 400, 10
# A word of letters of two alphabets («инженerов») is a slip of the model's pen unless the CV writes it so.
LETTERS = re.compile(r'[^\W\d_]+')
CYRILLIC, LATIN = re.compile(r'[а-яё]'), re.compile(r'[a-z]')
NAME_WORD = re.compile(r"[^\W\d_][\w.+#-]*")
TECHNOLOGY_LISTS = ('programming', 'data_and_tools', 'infrastructure', 'role_tools')
OWN_PERIOD = 3  # an entry's own period line stands among its first lines
SEPARATORS = ' \t,;:|·•/–—-'
# A call that gave no reply is asked once more, unless the account, a cancel or the deadline stopped it. The map and a
# written block have their own second call.
ASKED_AGAIN = ('fill', 'entry')
NO_SECOND_CALL = ACCOUNT_STOP | {'CANCELLED', 'DEADLINE_EXCEEDED', 'IMPORT_CALL_CAP'}
POOL = 8       # calls the scheme runs at once
LONG_RUN = 15  # this many lines in a row that no entry holds: the map is asked for once more
COLUMN_MIX = 5  # this many lines of another column in one entry, in no side block: the map is asked for once more
OWN_ENTRY = 4  # this many lines in a row after a job's header, in no entry, are an entry the map missed
DURATION = re.compile(r'\(\s*\d[^)]*\)|\b\d+(?:[.,]\d+)?\s*(?:год[а-я]*|лет|месяц[а-я]*|мес\.?|years?|yrs?|months?|mos?)\b', re.I)
# A stated length in years: a number of one or two digits (so no calendar year) and a year unit.
YEARS = re.compile(r'(?<![\w.,])(\d{1,2})(?:[.,](\d))?\s*\+?\s*(лет|года|год|г\.?|years?|yrs?)(?![\w])', re.I)
# Where one list item of a line ends: a semicolon, a bar, a bullet, or a comma that is no decimal comma («1,5 года»).
ITEMS = re.compile(r'[;|•]|,(?!\d)')
DATE_WORD = re.compile(r'^(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр|янв|фев|мар|апр|'
                       r'авг|сен|окт|ноя|дек|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|настоящ|наст|время|сейчас|'
                       r'текущ|present|now|current|today|ongoing|till|состоянию)', re.I)


def pointer(*tokens):
    return ''.join('/' + str(token) for token in tokens)


def years(text, russian=None):
    """A length in years in its one form: (the number, the form) or None. The unit follows the number as its language
    asks («1 год», «2 года», «5 лет», «1,5 года»; «1 year», «3 years»); every other word is left out. russian: the
    language of the form; None keeps the language of the unit as written."""
    found = YEARS.search(str(text or ''))
    if found is None:
        return None
    whole, part, unit = int(found.group(1)), found.group(2), found.group(3).casefold()
    if unit[0] == 'y' if russian is None else not russian:
        number = str(whole) + ('.' + part if part else '')
        return number, number + (' year' if number == '1' else ' years')
    number = str(whole) + (',' + part if part else '')
    if part:
        return number, number + ' года'
    word = 'год' if whole % 10 == 1 and whole % 100 != 11 else 'года' if whole % 10 in (2, 3, 4) and whole % 100 not in (12, 13, 14) else 'лет'
    return number, number + ' ' + word


def same_tool(name):
    """One key for the spellings of one tool: its catalog entry, else its letters and digits alone (Win Forms, WinForms)."""
    resolved = resolve_technology(name)
    return resolved.canonical_id or ''.join(char.casefold() for char in name if char.isalnum() or char in '+#') or name.casefold()


def within(target, text):
    """Where a folded value stands in a folded text as whole words (never a part of a longer word: Java is not in
    JavaScript); -1 when it does not."""
    found = re.search(r'(?<![^\W_])' + re.escape(target) + r'(?![^\W_])', text) if target else None
    return found.start() if found else -1


def fold(text):
    """As the gate folds: case, spacing, dash and quote forms aside."""
    text = QUOTES.sub('"', DASHES.sub('-', str(text).casefold().replace('ё', 'е')))
    return ' '.join(text.split())


def written_check(text, refs, lines, limit=WRITTEN_LIMIT):
    """Why code does not keep a text a model wrote from these lines (their texts), as (the problem's name, the words it
    is about, the sentence for the model); (None, [], None) when it keeps it. The text names lines to rest on, is no
    page, and states no number and no name the lines do not state and no word of two alphabets they do not have. The
    import and the editor's «Написать заново по резюме» both use it."""
    stated = {number for line in lines for number in NUMBER.findall(line)}
    foreign = sorted(set(NUMBER.findall(text)) - stated)
    known = {word.casefold() for line in lines for word in LETTERS.findall(line)}
    mixed = [word for word in LETTERS.findall(text) if CYRILLIC.search(word.casefold()) and LATIN.search(word.casefold())
             and word.casefold() not in known]
    # A name (an employer, a product, a technology, a level such as Senior) must be one the lines write.
    stated_names = {word.casefold() for line in lines for word in NAME_WORD.findall(line)} | known
    unknown = unknown_names(text, stated_names)
    return (('no text', [], None) if not text
        else ('no lines', [], 'it named no line of these lines to rest on.') if not refs
        else ('too long', [], 'it was too long.') if len(text) > limit
        else ('a number the CV lacks', foreign, 'it states a number the lines do not state: ' + ', '.join(foreign) + '.') if foreign
        else ('a word of two alphabets', mixed, 'a word in it mixes two alphabets: ' + ', '.join('«' + word + '»' for word in mixed)
              + '. Each word is written in one alphabet.') if mixed
        else ('a name the CV lacks', list(unknown), 'it names what the lines do not name: ' + ', '.join(unknown) + '.') if unknown
        else (None, [], None))


class Import:
    def __init__(self, sources, caller, *, envelope=True, form='text', writing=None, blocks=None, custom=None):
        """caller.call(kind, block, prompt, schema) -> (payload or None, row); envelope: whether the caller's replies
        come inside {"payload": ...} (the request's example then shows it). writing: {block: instructions}, the
        template's own rules for a block the import may write when the CV has no text for it; none, none is written.
        blocks: the ids of the template's blocks; a block the template lacks is not asked for, and its content does
        not count as shown. None: every block the scheme knows. custom: {block: {holds, schema, instructions}}, the
        template's own blocks (custom.py): mapped and read beside the scheme's."""
        self.caller, self.envelope, self.form, self.writing = caller, envelope, form, dict(writing or {})
        self.blocks = None if blocks is None else set(blocks)
        self.custom = dict(custom or {})
        self.mapped = [(block, spec['holds']) for block, spec in self.custom.items()]
        self.data = CV(sources)
        self.lines = self.data.lines
        # The résumé is written in the language most of the CV's letters are of; a value with a form takes its words.
        letters = ''.join(line.text for line in self.lines).casefold()
        self.russian = len(CYRILLIC.findall(letters)) >= len(LATIN.findall(letters))
        self.notes = {'invalid': [], 'dropped': [], 'leftover': [], 'respelled': 0, 'map': {}}
        self.table, self.failed = {}, set()
        self.labels = set()  # label-only lines: hidden, still shown to their entry's call
        self.other = []      # text no field took: {owner, kind, refs}; kept for the facts, not shown
        self.written = {}    # blocks the CV has no text for, written from its lines: {block: [pointer]}
        self.lack = {}       # of a line kept as «other» that its block shows in part: the words it does not show
        self.stage = None    # called with a short stage name as the import goes on
        self.live = None     # the blocks that show content in this document, once the branch is known

    # ----------------------------------------------------------------------------------------------------- helpers

    def wanted(self, block):
        return self.blocks is None or block in self.blocks

    def text(self, ref):
        return self.data.text(ref)

    def spans(self, refs):
        return [self.data.span(ref) for ref in refs]

    def ordered(self, refs):
        return sorted(set(refs), key=self.data.order.__getitem__)

    def joins(self, upper, lower):
        """A line goes on into the next one when it has not ended its sentence and the next is no new item or label."""
        upper, lower = self.text(upper), self.text(lower)
        return (not upper.endswith(('.', '!', '?', ';', ':')) and not BULLET.match(lower) and not LABELLED.match(lower)
                and lower[:1].islower())

    def items(self, refs):
        """The list items of lines in CV order: a line joins the one before when the layout broke one item."""
        groups = []
        for ref in self.ordered(refs):
            if groups and self.data.order[ref] == self.data.order[groups[-1][-1]] + 1 and self.joins(groups[-1][-1], ref):
                groups[-1].append(ref)
            else:
                groups.append([ref])
        return groups

    def copy(self, refs):
        """The text of lines as one value: markers and labels of the form left out, the lines joined by spaces."""
        parts = [without_form(self.text(ref)).strip() for ref in refs]
        # A line of a lone list glyph (a PDF sets it apart from its text) holds no words.
        return ' '.join(part for part in parts if any(char.isalnum() for char in part)).strip() or None

    def locate(self, value, scope):
        """The fewest consecutive lines of scope (its own order) that state the value word for word; [] when none does."""
        target = fold(value)
        if not target:
            return []
        refs = self.ordered(scope)
        best = None
        for start in range(len(refs)):
            joined = ''
            # With the fixes a value may run over 12 lines: a narrow sidebar breaks a name into a word a line.
            for end in range(start, min(len(refs), start + (12 if FIXES else 8))):
                # Lines next to each other among the block's own lines: a two-column layout sets other lines between.
                joined = (joined + ' ' + fold(BULLET.sub('', self.text(refs[end]), count=1))).strip()
                if within(target, joined) >= 0 or within(target, fold(self.text(refs[end]))) >= 0:
                    if best is None or end - start < len(best) - 1:
                        best = refs[start:end + 1]
                    break
        if best and len(best) > 1:
            # Keep only the lines the value reaches into.
            while len(best) > 1 and within(target, ' '.join(fold(BULLET.sub('', self.text(ref), count=1)) for ref in best[1:])) >= 0:
                best = best[1:]
            while len(best) > 1 and within(target, ' '.join(fold(BULLET.sub('', self.text(ref), count=1)) for ref in best[:-1])) >= 0:
                best = best[:-1]
        return best or []

    def source_text(self, value, refs):
        """The value as its lines write it (their dash, quote and case forms), found by the folded match."""
        joined = ' '.join(' '.join(BULLET.sub('', self.text(ref), count=1).split()) for ref in refs)
        folded = QUOTES.sub('"', DASHES.sub('-', joined.casefold().replace('ё', 'е')))
        target = fold(value)
        at = within(target, folded)
        if len(folded) != len(joined) or at < 0:
            return ' '.join(str(value).split())
        return joined[at:at + len(target)]

    def short(self, block, path, value, scope, evidence, cited=None):
        """A short value copied from the lines: kept with its lines when they state it word for word, else dropped."""
        if value is None or not str(value).strip():
            return None
        found = self.locate(value, scope)
        if not found:
            self.notes['dropped'].append({'block': block, 'pointer': path, 'why': 'not word for word'})
            return None
        evidence[path] = self.spans(found)
        if cited is not None:
            cited.update(found)
        text = self.source_text(value, found)
        if L3 and text.endswith('.') and not text.endswith('..'):
            # The dot that ends the line's sentence is no part of a short value («Frontend Developer.»).
            last = re.split(r'[\s,;(]', text[:-1])[-1].casefold()
            if len(last) >= 3 and last not in ABBREVIATIONS and '.' not in last:
                text = text[:-1].rstrip()
        return text

    def ranged(self, block, path, value, scope, evidence, cited=None):
        """A long value given as a line range: the range must be in order and inside scope; code copies the lines."""
        if value is None:
            return None
        order = self.data.order
        first, last = self.snap(value.get('first'), 'first'), self.snap(value.get('last'), 'last')
        inside = set(scope)
        if first not in order or last not in order or order[last] < order[first]:
            self.notes['dropped'].append({'block': block, 'pointer': path, 'why': 'range not offered or backwards'})
            return None
        refs = [line.ref for line in self.lines[order[first]:order[last] + 1]]
        if not set(refs) <= inside:
            self.notes['dropped'].append({'block': block, 'pointer': path, 'why': 'range outside its lines'})
            return None
        refs = [ref for ref in refs if ref not in self.hidden]
        text = self.copy(refs)
        if not text:
            return None
        evidence[path] = self.spans(refs)
        if cited is not None:
            cited.update(refs)
        return text

    def long(self, block, path, value, scope, evidence, cited=None):
        if self.form == 'ranges':
            return self.ranged(block, path, value, scope, evidence, cited)
        if value is None or not str(value).strip():
            return None
        found = self.locate(value, scope)
        if not found:
            self.notes['dropped'].append({'block': block, 'pointer': path, 'why': 'not word for word'})
            return None
        evidence[path] = self.spans(found)
        if cited is not None:
            cited.update(found)
        # The copied text stands; its lines are cited (a value may hold less than its lines, never other words).
        return without_form(self.source_text(value, found)).strip() or None

    def technology(self, block, path, name, scope, evidence, cited=None):
        texts = [self.text(ref) for ref in scope]
        if not name or not name.strip():
            return None
        if not named_in(name, texts):
            spelled = source_spelling(name, texts)
            if spelled is None:
                self.notes['dropped'].append({'block': block, 'pointer': path, 'why': 'technology not named by its lines'})
                return None
            self.notes['respelled'] += 1
            name = spelled
        found = [ref for ref in scope if named_in(name, [self.text(ref)])] or self.locate(name, scope)
        evidence[path] = self.spans(found[:3] or list(scope)[:1])
        if cited is not None:
            cited.update(found)
        return ' '.join(name.split())

    # ----------------------------------------------------------------------------------------------------------- map

    def snap(self, ref, inward):
        """A range end that names no listed line (a ref skipped in the list names a whole unit) moves inward to the
        nearest listed line: a first end to the next one, a last end to the one before."""
        if not isinstance(ref, str) or ref in self.data.order or not ref[1:].isdecimal():
            return ref
        number = int(ref[1:])
        numbers = sorted(int(line.ref[1:]) for line in self.lines)
        found = [n for n in numbers if n >= number] if inward == 'first' else [n for n in numbers if n <= number]
        self.notes['map'].setdefault('snapped', 0)
        self.notes['map']['snapped'] += 1
        if not found:
            return ref
        return 'S' + str(found[0] if inward == 'first' else found[-1])

    def snapped(self, value):
        first, last = self.snap(value.get('first'), 'first'), self.snap(value.get('last'), 'last')
        order = self.data.order
        if first in order and last in order and order[first] > order[last]:
            return None
        return {**value, 'first': first, 'last': last}

    def apart(self, entries):
        """Entries in CV order that share no line: an entry that starts inside the one before starts after it (map
        rule: the lines between first and last belong to no other entry); an entry left with no line is dropped."""
        order, refs = self.data.order, [line.ref for line in self.lines]
        out = []
        for entry in entries:
            first, last = entry.get('first'), entry.get('last')
            if out and first in order and last in order and out[-1]['last'] in order \
                    and order[first] <= order[out[-1]['last']]:
                start = order[out[-1]['last']] + 1
                self.notes['map']['apart'] = self.notes['map'].get('apart', 0) + 1
                if start > order[last]:
                    continue
                entry = {**entry, 'first': refs[start]}
            out.append(entry)
        return out

    def read_map(self, payload):
        payload = {**payload,
                   'blocks': [{**block, 'ranges': [r for r in map(self.snapped, block.get('ranges') or []) if r]}
                              for block in payload.get('blocks') or []],
                   # In CV order, whatever order the reply lists them in: apart() reads them so.
                   'entries': self.apart(sorted((r for r in map(self.snapped, payload.get('entries') or []) if r),
                                                key=lambda entry: self.data.order.get(entry.get('first'), len(self.lines)))),
                   'hidden': [r for r in map(self.snapped, payload.get('hidden') or []) if r]}
        payload['blocks'] = [block for block in payload['blocks'] if block['ranges']]
        reply = {
            'blocks': payload.get('blocks') or [],
            'entries': [{'block': entry.get('block'), 'title': entry.get('title') or '', 'first': entry.get('first'),
                         'last': entry.get('last'), 'employer': entry.get('employer'), 'jobTitle': entry.get('job_title'),
                         'period': entry.get('period')} for entry in payload.get('entries') or []],
            'hidden': payload.get('hidden') or []}
        request = {'blocks': [{'block': name} for name, _ in [*P.MAP_BLOCKS, *self.mapped]],
                   'entryBlocks': [{'block': name} for name in P.ENTRY_BLOCKS]}
        value = parse_map(reply, self.data.offered, self.data.sources, request)
        # A line with content of a block is never hidden (map rule): a line the map both places and hides stays placed.
        placed = {ref for refs in value['blocks'].values() for ref in refs}
        kept = [ref for ref in value['hidden'] if ref not in placed]
        if len(kept) != len(value['hidden']):
            self.notes['map']['unhidden'] = len(value['hidden']) - len(kept)
            value = {**value, 'hidden': kept}
            value['uncovered'] = uncovered(value)
        # A line that is only a label («Обязанности:») is a heading: hidden by code (map rule: headings are hidden).
        heads = {header['line'] for entry in value['entries'] for header in entry['header'].values() if header}
        def label(text):
            text = ' '.join(without_form(text).split())
            return LABEL_ONLY.match(text) or (L3 and text.rstrip(':').strip().casefold() in SUBHEADS)
        labels = [line.ref for line in self.lines if line.ref not in heads and line.ref not in set(value['hidden'])
                  and label(line.text)]
        if labels:
            self.notes['map']['labels'] = len(labels)
            value = {**value, 'hidden': sorted({*value['hidden'], *labels}, key=self.data.order.get)}
            value['uncovered'] = uncovered(value)
        self.labels = set(labels)
        return value

    def period_only(self, ref):
        """A line that states a period and nothing else (its duration and date words aside)."""
        text = self.text(ref)
        if parse_period(text) is None:
            return False
        rest = re.findall(r'[^\W\d_]{3,}', DURATION.sub(' ', text).casefold())
        return not [word for word in rest if not DATE_WORD.match(word)]

    def place(self, value):
        """Without the repair call: a line of projects that no entry holds is an employer detail when it lies among a
        job's header lines (not shown, counted), else it joins the entry after a header or the entry before it; a run
        of OWN_ENTRY lines after a header is that job's own entry, the one the map missed."""
        order = self.data.order
        entries = [{**entry, 'lines': list(entry['lines'])} for entry in value['entries']]

        def zone(entry):
            at = [order[header['line']] for header in entry['header'].values() if header]
            return (min(at), max(at)) if at else None
        zones = sorted({zone(entry) for entry in entries} - {None})
        hidden = set(value['hidden'])
        left = self.ordered(ref for refs in value['uncovered'].values() for ref in refs)
        details = [ref for ref in left if any(first <= order[ref] <= last for first, last in zones)]
        inside = []
        if FIXES:
            # A line among a job's header lines is not hidden by its position alone (a stack line stands there too):
            # it joins the entry, and the entry's reply tells a detail from content (take_entry).
            inside, details = details, []
        runs = []
        for ref in left:
            if ref in details or ref in inside:
                continue
            between = [line.ref for line in self.lines[order[runs[-1][-1]] + 1:order[ref]]] if runs else None
            if runs and all(other in hidden for other in between):
                runs[-1].append(ref)
            else:
                runs.append([ref])
        placed = {'details': len(details), 'detailRefs': details, 'joined': 0, 'added': 0, 'longestRun': max(map(len, runs), default=0)}
        for ref in inside:
            target = next(entry for entry in entries if zone(entry) and zone(entry)[0] <= order[ref] <= zone(entry)[1])
            target['lines'] = self.ordered([*target['lines'], ref])
            placed['joined'] += 1
        for run in runs:
            first, last = order[run[0]], order[run[-1]]
            before = max((entry for entry in entries if order[entry['lines'][-1]] < first),
                         key=lambda entry: order[entry['lines'][-1]], default=None)
            after = min((entry for entry in entries if order[entry['lines'][0]] > last),
                        key=lambda entry: order[entry['lines'][0]], default=None)
            edge = order[before['lines'][-1]] if before else -1
            headed = any(edge < end < first for _start, end in zones)
            if headed and after is not None and len(run) >= OWN_ENTRY and zone(after) is not None and zone(after)[1] < first:
                employer = (after['header'].get('employer') or {}).get('value')
                entries.insert(entries.index(after), {**after, 'title': employer or after['title'], 'lines': list(run)})
                placed['added'] += 1
                continue
            target = after if headed and after is not None else before if before is not None else after
            if target is None:
                continue
            target['lines'] = self.ordered([*target['lines'], *run])
            placed['joined'] += len(run)
        # Checks by code (notes only): an entry that holds a period line other than its own period.
        placed['periodInside'] = sum(
            1 for entry in entries
            if any(self.period_only(ref) and ref != (entry['header'].get('period') or {}).get('line') for ref in entry['lines']))
        value = {**value, 'entries': entries, 'hidden': self.ordered({*hidden, *details})}
        value['uncovered'] = uncovered(value)
        self.notes['map']['placed'] = placed
        return value

    def page_lines(self):
        """Lines that repeat at the top or the bottom of several pages (a name header, a contact footer): every one
        but one at the top of the first page, which may be the CV's own name line."""
        units = {unit.id: unit for unit in self.data.source.units}
        pages = {}
        for line in self.lines:
            unit = units.get(line.span.unit_id)
            if unit is None or unit.location.kind != 'page' or unit.structure is None or not unit.structure.bounds:
                return set()
            pages.setdefault(unit.location.index, []).append((unit.structure.bounds[1], self.data.order[line.ref], line.ref))
        if len(pages) < 2:
            return set()
        first_page = {ref for _y, _order, ref in pages[min(pages)]}
        at_edge = {}
        for lines in pages.values():
            lines.sort()
            for side, part in (('top', lines[:2]), ('bottom', lines[-2:])):
                for _y, _order, ref in part:
                    key = (side, re.sub(r'\d+', '#', fold(self.text(ref))))
                    if len(key[1]) >= 5:
                        at_edge.setdefault(key, []).append(ref)
        found = set()
        for (side, _text), refs in at_edge.items():
            if len(refs) >= 2:
                found.update(ref for ref in refs if not (side == 'top' and ref in first_page))
        return found

    def without(self, value, page):
        """The page lines the map never saw: hidden, in no entry."""
        if not page:
            return value
        value = {**value, 'hidden': self.ordered({*value['hidden'], *page}),
                 'entries': [{**entry, 'lines': [ref for ref in entry['lines'] if ref not in page]} for entry in value['entries']],
                 'unused': [ref for ref in value['unused'] if ref not in page]}
        value['entries'] = [entry for entry in value['entries'] if entry['lines']]
        value['uncovered'] = uncovered(value)
        self.notes['map']['pageBefore'] = len(page)
        self.page = self.ordered(page)
        return value

    def near_blocks(self, value):
        """A run of lines the map gave to no block joins the blocks of the line right before it, when that line is of
        the same column: a list the map cut short (a sidebar's skills, a section's last lines)."""
        order, hidden = self.data.order, set(value['hidden'])
        units = {unit.id: unit for unit in self.data.source.units}

        def column(ref):
            unit = units.get(self.data.by_ref[ref].span.unit_id)
            return unit.structure.column if unit is not None and unit.structure is not None else None
        blocks = {block: list(refs) for block, refs in value['blocks'].items()}
        of = {}
        for block, refs in blocks.items():
            for ref in refs:
                of.setdefault(ref, []).append(block)
        joined = 0
        for line in self.lines:
            ref = line.ref
            if ref in hidden or ref in of or order[ref] == 0:
                continue
            before = self.lines[order[ref] - 1].ref
            if before in hidden or before not in of or column(before) != column(ref):
                continue
            of[ref] = list(of[before])
            for block in of[ref]:
                blocks[block].append(ref)
            joined += 1
        if not joined:
            return value
        value = {**value, 'blocks': {block: self.ordered(refs) for block, refs in blocks.items()},
                 'unused': [ref for ref in value['unused'] if ref not in of]}
        value['uncovered'] = uncovered(value)
        self.notes['map']['nearBlocks'] = joined
        return value

    def columns_of(self):
        units = {unit.id: unit for unit in self.data.source.units}

        def column(ref):
            unit = units.get(self.data.by_ref[ref].span.unit_id)
            return unit.structure.column if unit is not None and unit.structure is not None else None
        return column

    def away(self, value, sided=None):
        """Per entry: its lines of another column than most of its lines (only those of `sided` when given)."""
        column = self.columns_of()
        found = []
        for entry in value['entries']:
            own = [column(ref) for ref in entry['lines'] if (sided is None or ref not in sided) and column(ref) is not None]
            main = max(set(own), key=own.count) if own else None
            found.append({ref for ref in entry['lines'] if main is not None and column(ref) not in (None, main)
                          and (sided is None or ref in sided)})
        return found

    def clean(self, value):
        """Before the narrow question: side lines of another column leave the entry (see tidy, 2a)."""
        heads = {header['line'] for entry in value['entries'] for header in entry['header'].values() if header}
        sided = {ref for block in OWN_LINES for ref in value['blocks'].get(block, [])} - heads
        out = self.away(value, sided)
        self.notes['map']['sideLines'] = sum(map(len, out))
        entries = [{**entry, 'lines': [ref for ref in entry['lines'] if ref not in gone]} for entry, gone in zip(value['entries'], out)]
        value = {**value, 'entries': [entry for entry in entries if entry['lines']]}
        value['uncovered'] = uncovered(value)
        return value

    def split(self, value):
        """The narrow question: for each entry a code check names, one call asks where further entries start inside
        its lines; the entry is cut there. A piece keeps the entry's header; tidy() then gives it its own period."""
        from . import checks as map_checks
        found = map_checks.findings(self, value)
        cases = {}
        for item in found:
            cases.setdefault(item['entry'], {}).setdefault(item['line'], []).append(item['check'])
        jobs = {number: {'lines': value['entries'][number]['lines'], 'signs': signs} for number, signs in cases.items()
                if len(value['entries'][number]['lines']) >= 2}
        done = {'asked': len(jobs), 'cut': 0, 'pieces': 0, 'strong': sum(
            any(check in map_checks.STRONG for checks in case['signs'].values() for check in checks) for case in jobs.values())}
        self.notes['map']['split'] = done
        if not jobs:
            return value
        pool = ThreadPoolExecutor(POOL)
        try:
            futures = {number: pool.submit(self.call, 'split', 'projects.' + str(number),
                                           P.split_request([self.data.by_ref[ref] for ref in case['lines']], case['signs']),
                                           P.split_schema(case['lines'][1:])) for number, case in jobs.items()}
            replies = {number: future.result() for number, future in futures.items()}
        finally:
            # A failure here leaves no call running behind the import.
            pool.shutdown(wait=True, cancel_futures=True)
        cue, order = map_checks.cues(self.data), self.data.order
        done['refused'] = 0

        def stands(ref, case):
            """A cut is taken only where code saw a sign: at the sign's line or up to two lines above it (a title
            above its period), or after the first of two equal labels; never at a list item."""
            if cue[ref]['item'] or cue[ref]['marker']:
                return False
            for sign, checks in case['signs'].items():
                if 0 <= order[sign] - order[ref] <= 2:
                    return True
                if 'label-twice' in checks:
                    label = map_checks.label_of(self.text(sign))
                    first = next((other for other in case['lines'] if map_checks.label_of(self.text(other)) == label), sign)
                    if order[first] < order[ref] <= order[sign]:
                        return True
            return False
        entries = []
        for number, entry in enumerate(value['entries']):
            reply = replies.get(number)
            named = [ref for ref in (reply or {}).get('starts') or [] if ref in entry['lines'][1:]]
            starts = [ref for ref in named if stands(ref, jobs[number])]
            done['refused'] += len(named) - len(starts)
            if not starts:
                entries.append(entry)
                continue
            marks = sorted({self.data.order[ref] for ref in starts})
            pieces, current = [], []
            for ref in entry['lines']:
                if self.data.order[ref] in marks and current:
                    pieces.append(current)
                    current = []
                current.append(ref)
            pieces.append(current)
            done['cut'] += 1
            done['pieces'] += len(pieces) - 1
            for index, piece in enumerate(pieces):
                entries.append({**entry, 'lines': piece, 'header': dict(entry['header']),
                                'title': entry['title'] if index == 0 else self.text(piece[0])})
        value = {**value, 'entries': entries}
        value['uncovered'] = uncovered(value)
        return value

    def tidy(self, value):
        """Fixes of the map by code, each counted in the notes. No call."""
        order = self.data.order
        entries = [{**entry, 'lines': list(entry['lines']), 'header': dict(entry['header'])} for entry in value['entries']]
        hidden = set(value['hidden'])
        done = {}
        heads = {header['line'] for entry in entries for header in entry['header'].values() if header}
        # 1. Repeated page lines are hidden, wherever the map put them.
        pages = {ref for ref in self.page_lines() if ref not in heads and ref not in hidden}
        done['pageBefore'] = len(getattr(self, 'page', []))
        # 2. Employer details the map left out of every entry (place() found them among a job's header lines): kept
        #    as «other». Those the map put into an entry are told apart later, by what the entry's reply cites.
        self.details = list((self.notes['map'].get('placed') or {}).get('detailRefs') or [])
        done.update(pageLines=len(pages), pageRefs=self.ordered(pages | set(getattr(self, 'page', []))))
        # 2a. A line the map also gave to a side block that shares no line with a job (education, courses, languages,
        #     location, identity, links) is not the entry's: on a page with a sidebar an entry's range runs over it.
        #     Only a line of another column than the entry's own lines: a study project may stand in both blocks.
        sided = {ref for block in OWN_LINES for ref in value['blocks'].get(block, [])} - heads
        units = {unit.id: unit for unit in self.data.source.units}

        def column(ref):
            unit = units.get(self.data.by_ref[ref].span.unit_id)
            return unit.structure.column if unit is not None and unit.structure is not None else None
        done['sideLines'] = self.notes['map'].get('sideLines', 0)
        for entry in entries:
            own = [column(ref) for ref in entry['lines'] if ref not in sided and column(ref) is not None]
            if not own:
                continue
            main = max(set(own), key=own.count)
            away = {ref for ref in entry['lines'] if ref in sided and column(ref) not in (None, main)}
            done['sideLines'] += len(away)
            entry['lines'] = [ref for ref in entry['lines'] if ref not in away]
        out = pages
        if out:
            hidden |= out
            for entry in entries:
                entry['lines'] = [ref for ref in entry['lines'] if ref not in out]
        # 3. An entry's own period: one period-only line among its first lines that is not its header's period.
        done['ownPeriod'] = 0
        for entry in entries:
            period = (entry['header'].get('period') or {}).get('line')
            shown = [ref for ref in entry['lines'] if ref not in hidden]
            own = [ref for ref in shown if ref != period and self.period_only(ref)]
            # Only a period line under the header's one: a project's own period follows its job's whole period.
            if len(own) == 1 and own[0] in shown[:OWN_PERIOD] and parse_period(self.text(own[0])) is not None \
                    and (period is None or order[own[0]] > order[period]):
                entry['header']['period'] = {'value': self.text(own[0]), 'line': own[0]}
                done['ownPeriod'] += 1
        # 4. The job title cut off an employer value that holds the whole «employer, title» line.
        done['employerCut'] = 0
        for entry in entries:
            employer, title = entry['header'].get('employer'), entry['header'].get('jobTitle')
            if not employer or not title or employer['line'] != title['line']:
                continue
            at = fold(employer['value']).find(fold(title['value']))
            if at <= 0 or len(fold(employer['value'])) != len(employer['value'].strip()):
                continue
            text = employer['value'].strip()
            cut = (text[:at] + text[at + len(fold(title['value'])):]).strip(SEPARATORS)
            if cut:
                entry['header']['employer'] = {**employer, 'value': cut}
                done['employerCut'] += 1
        done['sameHeader'] = sum(1 for entry in entries if entry['header'].get('employer') and entry['header'].get('jobTitle')
                                 and fold(entry['header']['employer']['value']) == fold(entry['header']['jobTitle']['value']))
        # 5. A piece of header lines only, when its job has another entry, is no entry.
        heads = {header['line'] for entry in entries for header in entry['header'].values() if header}
        kept = []
        for entry in entries:
            content = [ref for ref in entry['lines'] if ref not in hidden and ref not in heads and not self.period_only(ref)]
            job = tuple((entry['header'].get(name) or {}).get('line') for name in ('employer', 'period'))
            shared = any(other is not entry and job != (None, None) and job == tuple(
                (other['header'].get(name) or {}).get('line') for name in ('employer', 'period')) for other in entries)
            if not content and (shared or not entry['lines']):
                done['headerOnly'] = done.get('headerOnly', 0) + 1
                continue
            kept.append(entry)
        value = {**value, 'entries': kept, 'hidden': self.ordered(hidden)}
        value['uncovered'] = uncovered(value)
        self.notes['map']['tidy'] = done
        return value

    def out_of_entries(self, value):
        held = {ref for entry in value['entries'] for ref in entry['lines']}
        return len([ref for ref in value['blocks'].get('projects', []) if ref not in held and ref not in set(value['hidden'])])

    def map_once(self):
        """One map call, read and completed: (the map or None, a problem or None). Problems code can see: no reply, a
        reply the checks refuse, lines of projects with no entry at all, a long run of lines no entry holds."""
        page = self.page_lines() if L3 else set()
        lines = [line for line in self.lines if line.ref not in page]
        payload = self.call('map', 'map', P.map_request(lines, parts=True, extra=self.mapped) if L3
                            else P.map_request(self.lines, extra=self.mapped), P.map_schema(self.mapped))
        if payload is None:
            return None, 'no map'
        try:
            value = self.read_map(payload)
        except ValueError as error:
            return None, str(error)[:80]
        if L3:
            value = self.near_blocks(self.without(value, page))
        self.notes['map'].update(entries=len(value['entries']), uncovered=sum(map(len, value['uncovered'].values())),
                                 hidden=len(value['hidden']), unused=len(value['unused']))
        if value['uncovered']:
            value = self.place(value)
        if FIXES and not L3:
            value = self.tidy(value)        # in L3 after the narrow question (run)
        if not value['entries'] and self.out_of_entries(value) >= 3:
            return value, 'no entries'
        if (self.notes['map'].get('placed') or {}).get('longestRun', 0) >= LONG_RUN:
            return value, 'long run'
        if L3:
            # An entry that holds many lines of another column which the map gave to no side block: the map took a
            # sidebar for a job's text. Asked for once more.
            sided = {ref for block in OWN_LINES for ref in value['blocks'].get(block, [])} | set(value['hidden'])
            mixed = max((len(gone - sided) for gone in self.away(value)), default=0)
            self.notes['map']['columnMix'] = mixed
            if mixed >= COLUMN_MIX:
                return value, 'column mix'
        return value, None

    # ------------------------------------------------------------------------------------------------- side blocks

    def take_block(self, block, reply):
        scope = self.block_lines(block)
        evidence = {}
        if block == 'identity':
            name = self.short(block, '/name', reply.get('name'), scope, evidence)
            profession = self.short(block, '/profession', reply.get('profession'), scope, evidence)
            family = reply.get('role_family')
            if family not in {'system_analyst', 'business_analyst', 'tester', 'designer', 'other', None}:
                self.notes['dropped'].append({'block': block, 'pointer': '/role_family/family', 'why': 'not an enum value'})
                family = None
            if family is not None:
                evidence['/role_family/family'] = evidence.get('/profession') or self.spans(scope[:2])
            self.table[block] = ({'name': name, 'profession': profession, 'role_family': {'family': family}}, evidence)
            return family
        if block == 'location':
            content = {key: self.short(block, '/' + key, reply.get(key), scope, evidence) for key in ('city', 'country', 'timezone')}
            self.table[block] = (content, evidence)
            return None
        items = []
        for item in reply.get('items') or []:
            index = len(items)
            if block == 'focus':
                technology = self.technology(block, pointer('items', index, 'technology'), item.get('technology'), scope, evidence)
                if technology is None:
                    continue
                experience = self.experience(block, pointer('items', index, 'experience'), technology, item.get('experience'),
                                             scope, evidence)
                value = {'technology': technology, 'experience': experience}
                value = {key: part for key, part in value.items()}
                items.append(value)
                # The adapter reads focus as a list.
            elif block == 'education':
                institution = self.short(block, pointer(index, 'institution'), item.get('institution'), scope, evidence)
                value = {'institution': institution,
                         'graduation_year': self.date(block, pointer(index, 'graduation_year'), item.get('year'), scope, evidence),
                         'place': None, 'specialization': self.short(block, pointer(index, 'specialization'),
                                                                     item.get('specialization'), scope, evidence),
                         'degree': self.short(block, pointer(index, 'degree'), item.get('degree'), scope, evidence)}
                city = self.short(block, pointer(index, 'place', 'city'), item.get('city'), scope, evidence)
                if city:
                    value['place'] = {'city': city}
                if not any(value[key] for key in ('institution', 'specialization', 'degree')):
                    continue
                items.append(value)
            elif block == 'courses':
                value = {'school': self.short(block, pointer(index, 'school'), item.get('school'), scope, evidence),
                         'title': self.short(block, pointer(index, 'title'), item.get('title'), scope, evidence),
                         'year': self.date(block, pointer(index, 'year'), item.get('year'), scope, evidence)}
                if not value['title'] and not value['school']:
                    continue
                items.append(value)
            elif block == 'languages':
                value = {'name': self.short(block, pointer(index, 'name'), item.get('name'), scope, evidence),
                         'level': self.short(block, pointer(index, 'level'), item.get('level'), scope, evidence), 'note': None}
                comment = self.short(block, pointer(index, 'note', 'comment'), item.get('comment'), scope, evidence)
                if comment:
                    value['note'] = {'comment': comment}
                if not value['name']:
                    continue
                items.append(value)
            elif block in ('opensource', 'portfolio'):
                value = {'name': self.short(block, pointer(index, 'name'), item.get('name'), scope, evidence),
                         'url': self.short(block, pointer(index, 'url'), item.get('url'), scope, evidence)}
                if not value['name'] and not value['url']:
                    continue
                items.append(value)
            elif block == 'key_skills':
                value = self.short(block, pointer('items', index), item, scope, evidence)
                if value:
                    items.append(value)
            else:  # technology lists
                value = self.technology(block, pointer('items', index), item, scope, evidence)
                # The same tool once, whatever its spelling (Postgres and PostgreSQL): the first one stands.
                if value and same_tool(value) not in {same_tool(other) for other in items}:
                    items.append(value)
                elif value:
                    evidence.pop(pointer('items', index), None)
        if block == 'focus':
            # The template's focus is a list of {technology, experience}; evidence by list position.
            moved = {path.replace('/items/', '/', 1) if path.startswith('/items/') else path: spans
                     for path, spans in evidence.items()}
            self.table[block] = (items, moved)
        elif block in ('education', 'courses', 'languages', 'opensource', 'portfolio'):
            self.table[block] = (items, evidence)
        else:
            self.table[block] = ({'items': items}, evidence)
        return None

    def experience(self, block, path, technology, text, scope, evidence):
        """A technology's stated length of work in its one form, in the résumé's language («5 лет» for «около 5 лет»
        and for «5 years» in a Russian CV). The number must stand with a year unit in the line that names this
        technology (or alone on the line under it); the length of another technology is never taken."""
        if text is None or not str(text).strip():
            return None
        asked = years(text)
        number = asked[0].replace(',', '.') if asked else None
        refs = list(scope)
        for index, ref in enumerate(refs if number else ()):
            line = self.text(ref)
            # The length stands in the list item that names the technology («Python — 5 лет, Docker — 2 года»).
            item = next((part for part in ITEMS.split(line) if named_in(technology, [part])), None)
            if item is None:
                continue
            stated = YEARS.search(item)
            if stated is not None:
                form, cited = years(stated.group(), self.russian), [ref]
            elif not YEARS.search(line) and index + 1 < len(refs) and YEARS.fullmatch(self.text(refs[index + 1]).strip(SEPARATORS + '()')):
                # A narrow column sets the length on the line under the name.
                form, cited = years(self.text(refs[index + 1]), self.russian), [ref, refs[index + 1]]
            else:
                continue
            if form[0].replace(',', '.') == number:
                evidence[path] = self.spans(cited)
                return form[1]
        self.notes['dropped'].append({'block': block, 'pointer': path, 'why': 'no stated length in years'})
        return None

    def take_custom(self, block, reply):
        """A block of the template's own: the reply copied into the block's shape. A text is kept when the block's
        lines state it word for word, a date when its text has a year, a number when the lines state it; a closed
        choice and a yes or no are taken as given. A list item with nothing kept is left out."""
        schema, scope, evidence = self.custom[block]['schema'], self.block_lines(block), {}
        numbers = {number for ref in scope for number in NUMBER.findall(self.text(ref))}

        def take(node, value, path):
            node = C.resolved(schema, node)
            types = C.kinds(node)
            if C.is_date(node):
                return self.date(block, pointer(*path), value, scope, evidence)
            if 'array' in types:
                kept = []
                for item in value if isinstance(value, list) else []:
                    here = [*path, len(kept)]
                    got = take(node.get('items') or {}, item, here)
                    if C.blank(got):
                        for key in [key for key in evidence if key == pointer(*here) or key.startswith(pointer(*here) + '/')]:
                            del evidence[key]
                        continue
                    kept.append(got)
                return kept
            if 'object' in types:
                got = {key: take(part, value.get(key) if isinstance(value, dict) else None, [*path, key])
                       for key, part in (node.get('properties') or {}).items()}
                return None if 'null' in types and C.blank(got) else got
            if 'enum' in node:
                return value if value in node['enum'] else None
            if types & {'integer', 'number'}:
                stated = isinstance(value, (int, float)) and not isinstance(value, bool) and str(value).split('.')[0] in numbers
                return value if stated else None
            if 'boolean' in types:
                return value if isinstance(value, bool) else None
            return self.short(block, pointer(*path), value, scope, evidence)
        listed = 'array' in C.kinds(C.resolved(schema, schema))
        content = take(schema, (reply or {}).get('items') if listed else reply, [])
        if not C.blank(content):
            self.table[block] = (content, evidence)

    def date(self, block, path, text, scope, evidence):
        """A year or date: the model copies its text, code reads the year (and a month when the text names one)."""
        if text is None or not str(text).strip():
            return None
        found = self.locate(text, scope)
        parsed = parse_period(str(text))
        if not found or parsed is None or not YEAR.search(str(text)):
            self.notes['dropped'].append({'block': block, 'pointer': path, 'why': 'no year in a stated date'})
            return None
        evidence[path] = self.spans(found)
        start = parsed['start']
        return {'raw': ' '.join(str(text).split()), 'year': start['year'], 'month': start['month']}

    def block_lines(self, block):
        refs = self.map['blocks'].get(block, [])
        if L3 and block in TECHNOLOGY_LISTS:
            # A skills line serves focus and the technology lists (map rule): code gives it to them all.
            refs = self.ordered([*refs, *self.map['blocks'].get('focus', [])])
        return [ref for ref in refs if ref not in self.hidden]

    # ----------------------------------------------------------------------------------------------------- entries

    def take_entry(self, index, reply):
        entry = self.map['entries'][index]
        header = entry['header']
        header_lines = {value['line'] for value in header.values() if value}
        own = [ref for ref in entry['lines'] if ref not in self.hidden]
        if L3:
            # A line that ends with a colon is shown to the entry's call and may hold content («Shop on Node.js:»):
            # a value may be found in it and cite it. Left uncited it stays a heading.
            own = [ref for ref in entry['lines'] if ref not in self.hidden or ref in self.labels]
        scope = self.ordered([*own, *header_lines])
        evidence, cited = {}, set()
        base = ('E',)
        employer = (header.get('employer') or {}).get('value')
        value = {'company': employer, 'project': None, 'period': {'raw': None, 'start': None, 'end': None, 'ongoing': None},
                 'technologies': [], 'role': None, 'role_details': None, 'tasks': [], 'results': []}
        if employer:
            evidence[pointer(*base, 'company')] = self.spans([header['employer']['line']])
        period = header.get('period')
        if period:
            parsed = parse_period(period['value'])
            if parsed is None:
                self.notes['dropped'].append({'block': 'projects', 'pointer': 'period', 'why': 'period does not parse'})
            else:
                value['period'] = parsed
                evidence[pointer(*base, 'period')] = self.spans([period['line']])
        project = reply.get('project') or {}
        name = self.short('projects', 'name', project.get('name'), scope, evidence)
        if name and employer and fold(name).strip(' "') == fold(employer).strip(' "'):
            name = None  # a name that only repeats the employer names no project (as the product does)
        if name:
            evidence[pointer(*base, 'project', 'name')] = evidence.pop('name')
            cited.update(self.locate(name, scope))
        else:
            evidence.pop('name', None)
        description = self.long('projects', pointer(*base, 'project', 'description'), project.get('description'), own,
                                evidence, cited)
        if name or description:
            value['project'] = {'name': name, 'description': description}
        role = self.short('projects', pointer(*base, 'role'), reply.get('role'), scope, evidence, cited)
        if role is None and header.get('jobTitle'):
            role = header['jobTitle']['value']
            evidence[pointer(*base, 'role')] = self.spans([header['jobTitle']['line']])
        value['role'] = role
        details = reply.get('role_details') or {}
        scope_text = self.long('projects', pointer(*base, 'role_details', 'scope'), details.get('scope'), own, evidence, cited)
        involvement = self.long('projects', pointer(*base, 'role_details', 'involvement'), details.get('involvement'), own,
                                evidence, cited)
        if scope_text or involvement:
            value['role_details'] = {'scope': scope_text, 'involvement': involvement}
        seen = set()
        for name in reply.get('technologies') or []:
            path = pointer(*base, 'technologies', len(value['technologies']), 'display')
            display = self.technology('projects', path, name, own, evidence, cited)
            if display is None:
                continue
            if same_tool(display) in seen:
                evidence.pop(path, None)
                continue
            seen.add(same_tool(display))
            value['technologies'].append({'display': display})
        for key in ('tasks', 'results'):
            for item in reply.get(key) or []:
                path = pointer(*base, key, len(value[key]), 'value')
                text = self.long('projects', path, item, own, evidence, cited)
                if text:
                    value[key].append({'value': text})
        if FIXES:
            cited -= self.whole(index, value, evidence, cited - header_lines)
        # Rule 5: every content line of the entry that no value cites goes in as one more plain bullet.
        left = [ref for ref in own if ref not in cited and ref not in header_lines and ref not in self.labels
                and any(char.isalnum() for char in without_form(self.text(ref)))
                and not LABEL_ONLY.match(' '.join(without_form(self.text(ref)).split()))]
        if FIXES:
            # A line no value cites that stands between this entry's header lines is an employer detail (city,
            # industry, site): kept as «other», not shown as a bullet.
            marks = sorted(self.data.order[ref] for ref in header_lines)
            zone = [(upper, lower) for upper, lower in zip(marks, marks[1:]) if 1 < lower - upper <= ZONE_GAP + 1]
            between = [ref for ref in left if any(upper < self.data.order[ref] < lower for upper, lower in zone)]
            if between:
                self.details = [*getattr(self, 'details', []), *between]
                self.notes['map'].setdefault('tidy', {})['details'] = self.notes['map'].get('tidy', {}).get('details', 0) + len(between)
                left = [ref for ref in left if ref not in between]
                entry['lines'] = [ref for ref in entry['lines'] if ref not in between]
                self.hidden.update(between)
        for group in self.items(left):
            text = self.copy(group)
            if not text:
                continue
            path = pointer(*base, 'tasks', len(value['tasks']), 'value')
            value['tasks'].append({'value': text})
            evidence[path] = self.spans(group)
            self.notes['leftover'].append({'entry': index, 'lines': len(group), 'refs': group})
        entry['value'], entry['evidence'] = value, evidence

    def whole(self, index, value, evidence, cited):
        """A line a value copied in part: a long value is made the whole text of its lines; a line that still has
        words no value shows is given back (rule 5 adds it as a plain bullet). Returns the lines given back."""

        def shown():
            texts = [value.get('company'), value.get('role'), *((value.get('project') or {}).values()),
                     *((value.get('role_details') or {}).values()), *(item['display'] for item in value['technologies']),
                     *(item['value'] for key in ('tasks', 'results') for item in value[key]),
                     (value.get('period') or {}).get('raw')]
            return set().union(*(words(text) for text in texts if text))

        def missing(have):
            return [ref for ref in self.ordered(cited) if line_words(self.text(ref)) - have]

        long_paths = {}
        for key in ('tasks', 'results'):
            for number, item in enumerate(value[key]):
                long_paths[pointer('E', key, number, 'value')] = (item, 'value')
        if value.get('project'):
            long_paths[pointer('E', 'project', 'description')] = (value['project'], 'description')
        if value.get('role_details'):
            for name in ('scope', 'involvement'):
                long_paths[pointer('E', 'role_details', name)] = (value['role_details'], name)
        by_unit = {}
        for ref in self.data.by_ref:
            span = self.data.span(ref)
            by_unit[(span['unitId'] if 'unitId' in span else span['unit_id'], span['start'])] = ref
        have, extended = shown(), 0
        for ref in missing(have):
            for path, (holder, name) in long_paths.items():
                refs = [by_unit.get((span.get('unitId', span.get('unit_id')), span['start'])) for span in evidence.get(path) or []]
                if ref not in refs or None in refs or not holder.get(name):
                    continue
                full = self.copy(refs)
                if full and words(holder[name]) <= words(full):
                    holder[name] = full
                    extended += 1
                    break
        back = set(missing(shown()))
        if L3:
            # A stack line whose technologies were taken and that has a few more words stays cited: no bullet repeats
            # it; keep_other() keeps it as «other». A sentence that only names a technology («… на Kafka») is no stack
            # line: most of its words are shown nowhere, and it is given back.
            wide = {by_unit.get((span.get('unitId', span.get('unit_id')), span['start']))
                    for path, spans in evidence.items() if '/technologies/' not in path for span in spans}
            have = shown()
            stack = {ref for ref in back - wide
                     if len(line_words(self.text(ref)) - have) <= len(line_words(self.text(ref)) & have)}
            back -= stack
        if extended or back:
            self.notes.setdefault('partial', []).append({'entry': index, 'extended': extended, 'back': len(back)})
        return back

    # --------------------------------------------------------------------------------------------- summary, highlights

    def from_map(self):
        summary = self.block_lines('summary')
        if summary:
            text = self.copy(summary)
            if text:
                self.table['summary'] = ({'text': text}, {'/text': self.spans(summary)})
        highlights = self.block_lines('career_highlights')
        if highlights:
            items, evidence = [], {}
            for group in self.items(highlights):
                text = self.copy(group)
                if text:
                    evidence[pointer('items', len(items))] = self.spans(group)
                    items.append(text)
            if items:
                self.table['career_highlights'] = ({'items': items}, evidence)

    def written_problem(self, text, refs, limit=WRITTEN_LIMIT):
        """Why code does not keep a text the model wrote, as (the note's name, the words for the model); (None, None)
        when it keeps it (written_check, against every line of the CV)."""
        problem, _words, told = written_check(text, refs, [line.text for line in self.lines], limit)
        return problem, told

    def cited(self, refs):
        return self.ordered([ref for ref in (refs or [])[:WRITTEN_LINES] if ref in self.data.by_ref and ref not in self.hidden])

    def take_written(self, block, reply):
        """A block the CV has no text for, written by the model from the CV's lines; what code keeps of it
        (written_problem). A text block that is refused gives the reason in words for the model (the caller asks once
        more); a kept block, an empty one and a list block give None: a list item code refuses is left out alone."""
        reply = reply if isinstance(reply, dict) else {}
        if P.WRITE[block]['shape'] == 'items':
            items, evidence = [], {}
            for item in reply.get('items') or []:
                text, refs = ' '.join(str(item.get('text') or '').split()), self.cited(item.get('lines'))
                problem, _told = self.written_problem(text, refs, WRITTEN_ITEM)
                if problem:
                    self.notes['invalid'].append({'kind': 'write', 'block': block, 'problem': problem})
                    continue
                evidence[pointer('items', len(items))] = self.spans(refs)
                items.append(text)
            if items:
                self.table[block] = ({'items': items}, evidence)
                self.written[block] = [pointer('items', '*')]
            return None
        text, refs = ' '.join(str(reply.get('text') or '').split()), self.cited(reply.get('lines'))
        problem, told = self.written_problem(text, refs)
        if problem:
            self.notes['invalid'].append({'kind': 'write', 'block': block, 'problem': problem})
            return told
        self.table[block] = ({'text': text}, {pointer('text'): self.spans(refs)})
        self.written[block] = [pointer('text')]
        return None

    def keep_other(self):
        """Every line the map did not hide whose words its own block or entry does not show is kept as «other»:
        employer details, words of a side line no field took, a line in no block."""

        def strings(value, key=None):
            if isinstance(value, dict):
                for name, part in value.items():
                    if key == 'period' and name == 'raw':
                        continue        # the period's raw text is not shown, its dates are
                    yield from strings(part, name)
            elif isinstance(value, (list, tuple)):
                for part in value:
                    yield from strings(part, key)
            elif value is not None and not isinstance(value, bool):
                yield str(value)

        # Only the blocks this document has and this role's branch fills show anything: a template without Focus shows
        # none of its content, and a block of the other branch is never filled.
        live = self.live = {block for block in [*SIDE, *BRANCH[self.branch], 'summary', 'career_highlights', *self.custom]
                            if self.wanted(block)}
        shown = {block: set().union(*(words(text) for text in strings(payload)))
                 for block, (payload, _evidence) in self.table.items() if block != 'projects' and block in live}
        # The same content as text: a line too short to have a counted word («UX») is looked for in it whole.
        said = {block: fold(' '.join(strings(payload))) for block, (payload, _evidence) in self.table.items()
                if block != 'projects' and block in live}
        entry_of, number = {}, 0
        for entry in self.map['entries']:
            if entry.get('value') is None:
                continue
            have = set().union(*(words(text) for text in strings(entry['value'])))
            text = fold(' '.join(strings(entry['value'])))
            for ref in [*entry['lines'], *(header['line'] for header in entry['header'].values() if header)]:
                entry_of.setdefault(ref, []).append((number, have, text))
            number += 1
        found = []
        heads, number = [], 0
        for entry in self.map['entries']:
            if entry.get('value') is not None:
                heads += [(header['line'], number) for header in entry['header'].values() if header]
                number += 1
        for ref in getattr(self, 'details', []):
            # The details of a job go to the first entry whose header line stands nearest.
            near = min(heads, key=lambda item: (abs(self.data.order[item[0]] - self.data.order[ref]), item[1]), default=None)
            found.append((ref, 'projects.' + str(near[1]) if near else 'projects', 'employer details'))
        blocks = self.map['blocks']
        for line in self.lines:
            ref = line.ref
            if ref in self.hidden:
                continue
            owners = [block for block, refs in blocks.items() if ref in refs and block != 'projects']
            if L3 and 'focus' in owners:
                owners += [block for block in TECHNOLOGY_LISTS if block not in owners]   # as block_lines gives them
            owners = [block for block in owners if block in live]
            have = set().union(*(shown.get(block, set()) for block in owners), *(item[1] for item in entry_of.get(ref, [])))
            need = line_words(self.text(ref))
            if not need:
                # No counted word: the line is shown when its own text stands in the content of its block or entry.
                own = fold(without_form(self.text(ref)))
                if not any(char.isalnum() for char in own) or any(within(own, text) >= 0 for text in
                        [*(said.get(block, '') for block in owners), *(item[2] for item in entry_of.get(ref, []))]):
                    continue
            elif not need - have:
                continue
            if need & have:
                self.lack[ref] = sorted(need - have)
            if ref in entry_of:
                found.append((ref, 'projects.' + str(entry_of[ref][0][0]), 'no field'))
            elif owners or ref in blocks.get('projects', []):
                found.append((ref, owners[0] if owners else 'projects', 'no field'))
            else:
                found.append((ref, None, 'in no block'))
        for ref, owner, kind in sorted(found, key=lambda item: self.data.order[item[0]]):
            last = self.other[-1] if self.other else None
            if last and last['owner'] == owner and last['kind'] == kind \
                    and self.data.order[last['refs'][-1]] + 1 == self.data.order[ref]:
                last['refs'].append(ref)
            else:
                self.other.append({'owner': owner, 'kind': kind, 'refs': [ref]})

    def assemble(self):
        items, evidence = [], {}
        for entry in self.map['entries']:
            value = entry.get('value')
            if value is None:
                continue
            index = len(items)
            for path, spans in entry['evidence'].items():
                evidence[path.replace('/E/', '/' + str(index) + '/', 1)] = spans
            items.append(value)
        if items:
            self.table['projects'] = (items, evidence)

    # ------------------------------------------------------------------------------------------------------------ run

    def call(self, kind, block, prompt, schema):
        payload, row = self.caller.call(kind, block, prompt, schema)
        if payload is None and kind in ASKED_AGAIN and row.get('errorCode') not in NO_SECOND_CALL:
            self.notes['askedAgain'] = self.notes.get('askedAgain', 0) + 1
            payload, row = self.caller.call(kind, block, prompt, schema)
        if payload is None:
            self.notes['invalid'].append({'kind': kind, 'block': block, 'problem': row.get('errorCode') or 'no reply'})
        return payload

    def tell(self, stage):
        if self.stage is not None:
            self.stage(stage)

    def run(self):
        started = time.monotonic()
        token = P.ENVELOPE.set(self.envelope)
        self.map, self.hidden = None, set()
        try:
            self.tell('map')
            value, problem = self.map_once()
            if NO_REPAIR and problem:
                # Without the repair call a map that code finds unusable is asked for once more; the better one stands.
                first, first_notes = value, self.notes['map']
                first_labels, first_page = set(self.labels), list(getattr(self, 'page', []))
                self.notes['map'] = {}
                value, again = self.map_once()
                worse = lambda old, new: (first_notes.get('columnMix', 0) <= self.notes['map'].get('columnMix', 0)
                                          if 'column mix' in (problem, again) else self.out_of_entries(old) <= self.out_of_entries(new))
                if value is None or (first is not None and again and (again in ('no entries', 'no map') or worse(first, value))):
                    value, again, self.notes['map'] = first, problem, first_notes
                    self.labels, self.page = first_labels, first_page
                self.notes['map']['retry'] = {'first': problem, 'second': again}
                problem = again if value is None or again in ('no entries', 'no map') else None
            if value is None or problem:
                self.notes['invalid'].append({'kind': 'map', 'problem': problem or 'no map'})
                return self.finish(started, 'failed')
            if L3:
                self.tell('entries')
                value = self.tidy(self.split(self.clean(value)))
            self.map, self.hidden = value, set(value['hidden'])
            self.from_map()
            self.tell('blocks')
            pool = ThreadPoolExecutor(POOL)
            try:
                self.fill(value, pool)
            finally:
                # A failure here leaves no call running behind the import.
                pool.shutdown(wait=True, cancel_futures=True)
            self.assemble()
            if FIXES:
                self.keep_other()
            return self.finish(started, 'succeeded')
        finally:
            P.ENVELOPE.reset(token)

    def fill(self, value, pool):
        """The calls for the blocks and the entries, side by side, and what code takes of each reply."""
        jobs = {}
        for block in SIDE:
            # Identity is always read: its role family chooses the branch of the technology blocks.
            if self.block_lines(block) and (self.wanted(block) or block == 'identity'):
                lines = [line for line in self.lines if line.ref in set(self.block_lines(block))]
                jobs[block] = pool.submit(self.call, 'fill', block, P.block_request(block, lines), P.block_schema(block))
        for block, spec in self.custom.items():
            if self.block_lines(block) and self.wanted(block):
                lines = [line for line in self.lines if line.ref in set(self.block_lines(block))]
                jobs[block] = pool.submit(self.call, 'fill', block, P.custom_request(spec['holds'], spec['instructions'], lines),
                                          C.asked(spec['schema'])[0])
        for index, entry in enumerate(value['entries']):
            header = {'employer': (entry['header'].get('employer') or {}).get('value'),
                      'job_title': (entry['header'].get('jobTitle') or {}).get('value'),
                      'period': (entry['header'].get('period') or {}).get('value')}
            lines = [line for line in self.lines if line.ref in set(entry['lines']) and (line.ref not in self.hidden or line.ref in self.labels)]
            jobs['entry:' + str(index)] = pool.submit(self.call, 'entry', 'projects.' + str(index),
                                                      P.entry_request(header, lines, self.form), P.entry_schema(self.form))
        # Every block the CV has no text for and the template lets a model word is written from the CV's lines, in one
        # call beside the others.
        empty = [block for block in P.WRITE if block not in self.table and value['entries'] and self.writing.get(block)
                 and self.wanted(block)]
        if empty:
            asked = [line for line in self.lines if line.ref not in self.hidden]
            jobs['write'] = pool.submit(self.call, 'write', 'write', P.write_request(empty, asked, self.writing),
                                        P.write_schema(empty))
        family = None
        if 'identity' in jobs:
            reply = jobs.pop('identity').result()
            if reply is None:
                self.failed.add('identity')
            else:
                family = self.take_block('identity', reply)
        self.branch = 'skills_and_tools' if family in SKILLS_FAMILIES else 'technical'
        for block in BRANCH[self.branch]:
            if self.block_lines(block) and self.wanted(block):
                lines = [line for line in self.lines if line.ref in set(self.block_lines(block))]
                jobs[block] = pool.submit(self.call, 'fill', block, P.block_request(block, lines), P.block_schema(block))
        for key, future in jobs.items():
            reply = future.result()
            if key.startswith('entry:'):
                if reply is None:
                    continue  # no reply twice: the entry is no card, its lines are kept as «other» (keep_other)
                self.take_entry(int(key.split(':')[1]), reply)
            elif key == 'write':
                # No reply, or a text code refuses twice: the block stays empty, as in the CV.
                refused = {block: told for block in empty for told in [self.take_written(block, (reply or {}).get(block))]
                           if told} if reply is not None else {}
                if refused:
                    # One more call for the refused blocks alone, told what code refused.
                    again = self.call('write', 'write', P.write_request(list(refused), asked, self.writing, refused),
                                      P.write_schema(list(refused)))
                    for block in refused if again is not None else ():
                        self.take_written(block, again.get(block))
            elif reply is None:
                self.failed.add(key)
            elif key in self.custom:
                self.take_custom(key, reply)
            else:
                self.take_block(key, reply)

    def finish(self, started, state):
        self.seconds = round(time.monotonic() - started, 2)
        self.state = state
        return self

    def export(self):
        """Everything the adapter and the measures need (local file: it holds CV text)."""
        value = self.map or {}
        projects = [ref for ref in value.get('blocks', {}).get('projects', [])]
        return {'state': self.state, 'seconds': self.seconds, 'branch': getattr(self, 'branch', None), 'form': self.form,
                'table': {block: [payload, evidence] for block, (payload, evidence) in self.table.items()},
                'failed': sorted(self.failed), 'notes': self.notes, 'other': self.other,
                'entryLines': [[entry['lines'][0], entry['lines'][-1]] for entry in value.get('entries', [])
                               if entry.get('value') is not None and entry['lines']],
                'map': {'hidden': sorted(value.get('hidden', []), key=self.data.order.get),
                        'unused': list(value.get('unused', [])), 'entries': len(value.get('entries', [])),
                        'projectsLines': len(projects),
                        'blocks': {block: refs for block, refs in value.get('blocks', {}).items()},
                        'uncovered': value.get('uncovered', {})},
                'lines': len(self.lines)}
