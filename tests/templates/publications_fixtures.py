"""CT08: the second template, defined by configuration only, and its scripted answers."""

from pathlib import Path

from packages.resume_core.templates.compiler import compile_template
from tests.templates.generic_fixtures import date, period


TEMPLATE = Path('tests/fixtures/synthetic/templates/publications/template.yaml')
BLOCKS = ['hdr-7', 'papers-x9', 'work-q2']
TITLE = 'Reliable Queues'
AWARD = 'Example Labs Quality Award'
DIVISION = 'Queue Systems'
URLS = ['https://example.org/paper-a', 'https://example.org/paper-b']


def publications_package():
    return compile_template(TEMPLATE)


def papers():
    return [{'title': TITLE, 'journal': journal, 'year': date(year, int(year)), 'url': url}
        for journal, year, url in [('Systems Notes', '2024', URLS[0]), ('Queue Review', '2025', URLS[1])]]


def job(company, raw, start, end, *, division=None, awards=()):
    return {'company': company, 'role': 'engineer', 'period': period(raw, date(start, int(start)), date(end, int(end)), False),
        'division': {'name': division} if division else None,
        'awards': [{'title': title, 'year': date(year, int(year))} for title, year in awards]}


def publications_table(name):
    """F05: one employer with an award and a division, two equal-title papers; F05-empty: no papers; F11 adds a
    second employer."""
    detailed = name in {'F05', 'F11'}
    jobs = [job('Example Labs', '2020–2023', '2020', '2023', division=DIVISION if detailed else None,
        awards=[(AWARD, '2022')] if detailed else [])]
    if name == 'F11':
        jobs.append(job('Second Works', '2024–2025', '2024', '2025'))
    return {'hdr-7': ({'name': 'Alex Example', 'profession': None}, {}),
        'papers-x9': (papers() if detailed else [], {}), 'work-q2': (jobs, {})}


def publications_workspace(name='F11'):
    """A published V7 workspace of the second template without the durable import record."""
    from tests.templates.generic_fixtures import direct_generic
    return direct_generic(name, BLOCKS, table=publications_table(name), package=publications_package())
