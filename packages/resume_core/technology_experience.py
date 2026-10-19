"""Source-stated durations and approximate exposure from linked, closed job periods."""

from .dates import month_bounds, union_months
from .technologies import technology_identity
import math
import re


def exposure_months(records, jobs):
    lower, upper, missing, dated = [], [], False, set()
    for record in records:
        identifier = record.subproject_id or record.job_id
        if identifier is None:
            continue
        job = jobs.get(identifier)
        if job is None or not job.periods:
            missing = True
            continue
        for period in job.periods:
            if period.id in dated:
                continue
            dated.add(period.id)
            if (period.start.status != "known" or period.end.status != "known"
                    or period.present.status != "known" or period.present.value is not False
                    or period.start.value.lower() > period.end.value.upper()):
                missing = True
                continue
            start, end = month_bounds(period.start.value), month_bounds(period.end.value)
            lower.append((start[1], end[0])); upper.append((start[0], end[1]))
    return (union_months(lower), union_months(upper), missing) if upper else (None, None, missing)


def stated_years(text):
    years = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:год|года|лет|years?)", text, re.I)
    months = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:месяц|months?)", text, re.I)
    if years and months:
        value = float(years[1].replace(",", ".")) + float(months[1].replace(",", ".")) / 12
        return math.floor(value + .5) if 0 <= value <= 100 else None
    values = [float(value.replace(",", ".")) for value in re.findall(r"\d+(?:[.,]\d+)?", text)]
    if not values or len(values) > 2:
        return None
    value = sum(values) / len(values)
    if re.search(r"месяц|months?", text, re.I):
        value /= 12
    return math.floor(value + .5) if 0 <= value <= 100 else None


def technology_years(facts):
    groups, jobs = {}, {}
    for record in facts.records:
        if record.kind in {"employment", "subproject"}:
            jobs[record.id] = record
        elif record.kind == "technology":
            groups.setdefault(technology_identity(record), []).append(record)
    result = {}
    for key, records in groups.items():
        corrected = [r for r in records if r.experience.user_corrected]
        considered = corrected or records
        statements = {r.experience.raw_text.strip() for r in considered if r.experience.raw_text.strip()}
        if corrected or statements:
            values = {stated_years(text) for text in statements}
            result[key] = next(iter(values)) if len(values) == 1 and all(r.experience.status == "known" for r in considered if r.experience.raw_text) else None
        else:
            minimum, maximum, _missing = exposure_months(records, jobs)
            result[key] = math.floor((minimum + maximum) / 24 + .5) if minimum is not None else None
    return result


def whole_years_text(years, russian=True):
    noun = "лет" if 11 <= years % 100 <= 14 else "год" if years % 10 == 1 else "года" if 2 <= years % 10 <= 4 else "лет"
    return f"{years} {noun}" if russian else f"{years} year" + ("s" if years != 1 else "")


def years_text(months, russian):
    if months < 12:
        return "менее года" if russian else "under 1 year"
    years = months // 12
    noun = "лет" if 11 <= years % 100 <= 14 else "год" if years % 10 == 1 else "года" if 2 <= years % 10 <= 4 else "лет"
    return f"{years} {noun}" if russian else f"{years} year" + ("s" if years != 1 else "")


def technology_experience(facts, russian=True):
    groups, jobs = {}, {}
    for record in facts.records:
        if record.kind in {"employment", "subproject"}:
            jobs[record.id] = record
        if record.kind == "technology":
            groups.setdefault(technology_identity(record), []).append(record)
    result = {}
    for key, records in groups.items():
        uncertain = [record.experience.pending_raw_text or record.experience.raw_text for record in records
            if (record.experience.raw_text or record.experience.pending_raw_text) and record.experience.status != "known"]
        if uncertain:
            result[key] = ("Срок требует проверки" if russian else "Duration needs review", "; ".join(uncertain))
            continue
        statements = list(dict.fromkeys(record.experience.raw_text.strip() for record in records
            if record.experience.raw_text.strip() and record.experience.status == "known"))
        if statements:
            text = statements[0] if len(statements) == 1 else "Сроки расходятся" if russian else "Conflicting durations"
            note = ("Указано в резюме: " if russian else "Stated in the resume: ") + "; ".join(statements)
            result[key] = (text, note)
            continue
        minimum, maximum, missing = exposure_months(records, jobs)
        if minimum is None:
            result[key] = ("Срок не указан" if russian else "Duration not stated",
                "Нет указанного срока или полных закрытых периодов работы." if russian else "No stated duration or complete closed job periods.")
            continue
        low, high = years_text(minimum, russian), years_text(maximum, russian)
        if missing:
            text = "≈ " + low + "+" if minimum >= 12 else ("Частичные даты" if russian else "Partial dates")
        else:
            text = low if maximum < 12 else "≈ " + (low if low == high else low + " – " + high)
        note = ("Оценка по датам связанных мест работы; пересечения объединены. Упоминание не доказывает использование весь период."
            if russian else "Estimated from linked job dates; overlaps merged. A mention does not prove use throughout the job.")
        if missing:
            note += " Незакрытые и неполные периоды не включены." if russian else " Open and incomplete periods excluded."
        result[key] = (text, note)
    return result
