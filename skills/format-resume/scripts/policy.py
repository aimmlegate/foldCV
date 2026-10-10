"""Deterministic date, focus, and source coverage policies."""

import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.resume_core.dates import month_bounds, old_job as _old_job, union_months
from packages.resume_core.technologies import canonical_id

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
FOCUS = {
    'golang': 'golang', 'python': 'python', 'c#': 'csharp', 'c++': 'cplusplus',
    '.net': 'dotnet', '.net core': 'dotnet', '.net framework': 'dotnet',
    'postgresql': 'postgresql', 'redis': 'redis', 'kafka': 'kafka',
    'rabbitmq': 'rabbitmq', 'kubernetes': 'kubernetes', 'docker': 'docker',
    'php': 'php', 'node.js': 'nodejs', 'grpc': 'grpc', 'linux': 'linux',
    'fastapi': 'fastapi', 'django rest framework': 'djangorest',
    'grafana': 'grafana', 'kibana': 'kibana',
}


def key(text):
    text = unicodedata.normalize('NFKC', text).strip().casefold()
    text = re.sub(r'^microsoft\s+', '', text)
    aliases = {'go': 'golang', 'go (golang)': 'golang', 'nodejs': 'node.js',
               'apache kafka': 'kafka', 'csharp': 'c#', 'c sharp': 'c#',
               'django rest framework (drf)': 'django rest framework', 'drf': 'django rest framework',
               '.net и .net framework': '.net', 'keycloack': 'keycloak',
               'postges': 'postgresql', 'postrgesql': 'postgresql'}
    text = aliases.get(text, text)
    return text


def matches(focus, technology):
    return canonical_id(focus) is not None and canonical_id(focus) == canonical_id(technology)


def old_job(job, as_of):
    return _old_job(job['end'], as_of)


def duration_label(months):
    if months < 12:
        value = months
        suffix = 'месяц' if value == 1 else 'месяца' if 2 <= value <= 4 else 'месяцев'
        return f'{value} {suffix}'
    # Half-year precision is intentional: project periods are only an exposure proxy.
    halves = int(months / 6 + 0.5)
    years = halves / 2
    number = str(int(years)) if years.is_integer() else str(years).replace('.', ',')
    if not years.is_integer():
        suffix = 'года'
    else:
        n = int(years)
        suffix = 'лет' if 11 <= n % 100 <= 14 else 'год' if n % 10 == 1 else 'года' if n % 10 in (2, 3, 4) else 'лет'
    return f'{number} {suffix}'


def estimate(focus, archive):
    intervals, refs, assumptions = [], set(), []
    limit = month_bounds(archive['as_of'])[1]
    for job in archive['jobs']:
        for tech in job['technologies']:
            if not matches(focus, tech['name']) or not tech.get('duration_eligible', True):
                continue
            start = tech.get('start') or job['start']
            stop = tech.get('end') or job['end']
            if stop is None:
                stop = job.get('observed_at') or archive['as_of']
                if not job.get('observed_at'):
                    assumptions.append(f"{job['id']}: no observation date; archive as-of date is an explicit assumption")
            lo_start, hi_start = month_bounds(start)
            lo_stop, hi_stop = month_bounds(stop)
            if lo_start > min(hi_stop, limit):
                raise ValueError(f"Invalid or future interval in {job['id']}")
            intervals.append({'job_id': job['id'], 'start': start, 'end': stop,
                              'lower': [hi_start, min(lo_stop, limit)],
                              'upper': [lo_start, min(hi_stop, limit)]})
            refs.update(tech['sources'])
            refs.update(job['period']['sources'])
            if job['end'] is None:
                refs.update(job.get('observed_sources', []))
    if not intervals:
        raise ValueError(f'No dated project evidence for focus technology: {focus}')
    low = union_months([item['lower'] for item in intervals])
    high = union_months([item['upper'] for item in intervals])
    a, b = duration_label(low), duration_label(high)
    label = '≈ ' + (a if a == b else f'{a} – {b}')
    return {'text': label, 'sources': sorted(refs), 'derived': True}, {
        'method': 'union_of_project_months', 'months_min': low, 'months_max': high,
        'as_of': archive['as_of'], 'intervals': intervals, 'assumptions': assumptions,
        'limitation': 'Technology exposure estimated from project periods; continuous full-time use is not established.',
    }


def public_statements(view):
    result = []
    def collect(value, path):
        if isinstance(value, dict):
            if 'text' in value and 'sources' in value:
                result.append((path, value))
            else:
                for k, v in value.items():
                    if k != 'estimate':
                        collect(v, path + '/' + k)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                collect(v, path + '/' + str(i))
    for field in ('candidate', 'focus', 'sidebar', 'projects', 'earlier_experience', 'achievements', 'skill_groups'):
        collect(view.get(field, []), '/' + field)
    return result


def numbers(text):
    # Treat grouped thousands, decimal comma/dot, and dash variants consistently.
    text = re.sub(r'(?<=\d)[ \u00a0\u202f](?=\d{3}(?:\D|$))', '', text)
    for word, value in {'один': '1', 'одного': '1', 'два': '2', 'двух': '2',
                        'две': '2', 'три': '3', 'трёх': '3', 'трех': '3',
                        'третьей': '3'}.items():
        text = re.sub(r'\b' + word + r'\b', value, text, flags=re.I)
    return {n.replace(',', '.') for n in re.findall(r'(?<![\w.])\d+(?:[.,]\d+)?', text)}
