"""Check preservation and selection invariants; semantic review remains separate."""

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from archive import digest, source_units
from extract import extract
from policy import ASSETS, FOCUS, estimate, key, month_bounds, numbers, old_job, public_statements
from validate import validate

CATEGORIES = {'identity', 'profile', 'job_header', 'period', 'role', 'task', 'result',
              'stack', 'education', 'course', 'language', 'location', 'preferences',
              'contacts', 'personal', 'meta'}
MONTHS = ['январ', 'феврал', 'март', 'апрел', 'ма[йя]', 'июн', 'июл', 'август',
          'сентябр', 'октябр', 'ноябр', 'декабр']
EN_MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']


def dates_in(text):
    result = set()
    for month, (ru, en) in enumerate(zip(MONTHS, EN_MONTHS), 1):
        for match in re.finditer(r'\b(?:' + ru + '|' + en + r')\w*\.?\s+(\d{4})\b', text, re.I):
            result.add(f'{match[1]}-{month:02d}')
    for match in re.finditer(r'\b(0?[1-9]|1[0-2])[./](\d{4})\b', text):
        result.add(f'{match[2]}-{int(match[1]):02d}')
    result.update(re.findall(r'\b\d{4}-\d{2}\b', text))
    return result


def check(view, archive, archive_path, source=None):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    archive_path = Path(archive_path)
    require(view.get('schema_version') == archive.get('schema_version') == 2, 'Version 2 required')
    require(view.get('archive_sha256') == digest(archive_path), 'Archive changed; finalize the view again')
    frozen_source = json.loads((archive_path.parent / 'source.json').read_text())
    require(archive['source'] == frozen_source, 'Archive source text was changed')
    if source is not None:
        require(source == frozen_source, 'Render source differs from archived source')
    require(archive['units'] == source_units(frozen_source), 'Source units were changed or lost')
    snapshot = archive_path.parent / archive['source_snapshot']
    require(snapshot.parent.resolve() == archive_path.parent.resolve(), 'Snapshot must be inside the case folder')
    require(snapshot.is_file() and digest(snapshot) == frozen_source['sha256'], 'Original bytes differ or are missing')
    extracted = extract(snapshot)
    require(extracted['pages'] == frozen_source['pages'], 'Archived text differs from fresh source extraction')
    date.fromisoformat(archive['as_of'])
    base = validate(view, frozen_source)
    units = {u['id']: u for u in archive['units']}
    ids = set(units)
    require(view['evidence'] == {u['id']: {'page': u['page'], 'quote': u['text']} for u in archive['units']},
            'Evidence must be exactly the complete source units')

    def refs(value, label):
        references = value.get('sources')
        require(isinstance(references, list) and references and set(references) <= ids,
                f'{label}: missing or unknown sources')
        return '\n'.join(units[r]['text'] for r in references)

    jobs = {j['id']: j for j in archive['jobs']}
    require(len(jobs) == len(archive['jobs']), 'Duplicate job IDs')
    classifications = archive['classifications']
    require(isinstance(classifications, dict) and set(classifications) == ids, 'Classify every unit in an ID-keyed object')
    for uid, item in classifications.items():
        require(item['category'] in CATEGORIES and item['importance'] in {'essential', 'supporting', 'administrative'},
                f'{uid}: invalid classification')
        require(item['job_id'] is None or item['job_id'] in jobs, f'{uid}: unknown job')
    for job in jobs.values():
        for field in ('company', 'period', 'role'):
            refs(job[field], f"{job['id']}.{field}")
        source_period = refs(job['period'], job['id'])
        for field in ('start', 'end'):
            value = job[field]
            if value is None:
                require(field == 'end' and re.search(r'настоящее|present|current', source_period, re.I), f"{job['id']}: unsupported open date")
                continue
            month_bounds(value)
            supported = value in dates_in(source_period) if len(value) > 4 else value in source_period
            require(supported, f"{job['id']}: normalized {field} {value} absent from cited dates")
        require(job['end'] is None or month_bounds(job['start'])[0] <= month_bounds(job['end'])[1], 'Reversed job dates')
        if job.get('observed_at'):
            observed = date.fromisoformat(job['observed_at'])
            text = refs({'sources': job['observed_sources']}, job['id'] + '.observed_at')
            require(job['observed_at'][:7] in dates_in(text) and re.search(r'\b0?' + str(observed.day) + r'\b', text),
                    f"{job['id']}: observation date not supported")
        for tech in job['technologies']:
            tech_source = refs(tech, f"{job['id']}.{tech['name']}")
            for bound in ('start', 'end'):
                if tech.get(bound):
                    value = tech[bound]
                    month_bounds(value)
                    require(value in dates_in(tech_source) if len(value) > 4 else value in tech_source,
                            f"{job['id']}.{tech['name']}: unsupported subproject date")
                    require(month_bounds(value)[0] >= month_bounds(job['start'])[0] and
                            month_bounds(value)[1] <= month_bounds(job['end'] or job.get('observed_at') or archive['as_of'])[1],
                            f"{job['id']}.{tech['name']}: subproject date outside employment")
    for tech in archive['global_technologies']:
        refs(tech, 'global.' + tech['name'])

    detailed = [p['id'] for p in view['projects']]
    early = [jid for item in view['earlier_experience'] for jid in item['job_ids']]
    require(Counter(detailed + early) == Counter(jobs.keys()), 'Every job must appear exactly once')
    for jid in detailed:
        require(not old_job(jobs[jid], archive['as_of']), f'{jid}: old work must be condensed')
    for jid in early:
        require(old_job(jobs[jid], archive['as_of']), f'{jid}: recent work must remain detailed')
    recent = view['recent_project_ids']
    newest = sorted(jobs, key=lambda jid: month_bounds(jobs[jid]['start'])[0], reverse=True)
    require(1 <= len(recent) <= 2 and recent == newest[:len(recent)], 'Profile must focus on latest projects')
    summary_jobs = {classifications[r]['job_id'] for r in view['candidate']['summary']['sources']}
    require(set(recent) <= summary_jobs, 'Profile lacks sources from recent projects')

    focus_keys = [key(f['label']['text']) for f in view['focus']]
    require(len(set(focus_keys)) == len(focus_keys) <= 8, 'Duplicate or excessive focus technologies')
    for item, name in zip(view['focus'], focus_keys):
        require(name in FOCUS, f'{name}: not in the familiar technology/logo catalog')
        alias = FOCUS[name]
        require(any((ASSETS / folder / (alias + '.png')).is_file() for folder in ('images', 'devicon')), f'{name}: missing logo')
        require(item['icon'] is None or item['icon'] == alias, f'{name}: incorrect logo')
        duration, calculation = estimate(name, archive)
        require(item['duration'] == duration and item['estimate'] == calculation, f'{name}: duration differs from project calculation')

    statements = public_statements(view)
    referenced = {r for _, statement in statements for r in statement['sources']}
    coverage = view['coverage']
    require(isinstance(coverage, dict) and set(coverage) == ids, 'Coverage must account for every source unit')
    decisions = {'shown', 'condensed', 'archive_only', 'duplicate', 'metadata'}
    checked_numbers = 0
    for uid, disposition in coverage.items():
        decision = disposition['decision']
        require(decision in decisions, f'{uid}: invalid disposition')
        require(decision == 'shown' or bool(disposition.get('reason', '').strip()), f'{uid}: missing exclusion/condensation reason')
        if decision in {'shown', 'condensed'}:
            require(uid in referenced, f'{uid}: marked visible but never cited')
        classification = classifications[uid]
        if classification['job_id'] in detailed and classification['category'] in {'task', 'result'} and classification['importance'] == 'essential':
            project_index = detailed.index(classification['job_id'])
            texts = [s['text'] for path, s in statements if path.startswith(f'/projects/{project_index}/') and uid in s['sources']]
            require(texts, f'{uid}: essential recent work omitted from its project')
            missing = numbers(units[uid]['text']) - numbers(' '.join(texts))
            require(not missing, f'{uid}: important numeric markers lost: {sorted(missing)}')
            checked_numbers += len(numbers(units[uid]['text']))

    text = key(' '.join(s['text'] for _, s in statements))
    hidden = {key(t['name']): t['reason'] for t in view['archived_technologies']}
    require(all(isinstance(reason, str) and reason.strip() for reason in hidden.values()), 'Technology exclusions require reasons')
    unaccounted = []
    for tech in archive['global_technologies'] + [t for j in jobs.values() for t in j['technologies']]:
        name = key(tech['name'])
        if name not in text and name not in hidden:
            unaccounted.append(tech['name'])
    require(not unaccounted, f'Technologies not displayed or explicitly archived: {sorted(set(unaccounted))}')
    return {**base, 'source_bytes_verified': True, 'source_text_verified': True,
            'source_units': len(units), 'jobs': len(jobs), 'detailed_jobs': len(detailed),
            'condensed_jobs': len(early), 'dispositions': dict(Counter(i['decision'] for i in coverage.values())),
            'focus_items': len(focus_keys), 'numeric_markers_checked': checked_numbers}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('view', type=Path)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(json.loads(args.view.read_text()), json.loads(args.archive.read_text()), args.archive), indent=2))
