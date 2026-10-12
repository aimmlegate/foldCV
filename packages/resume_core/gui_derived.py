"""Initial pure projections; observation evidence alone bounds ongoing exposure."""

from __future__ import annotations

import hashlib
import json

from .dates import month_bounds, partial_date, union_months
from .models.contracts import Job, PartialDate, Period, TechnologyFact
from .models.recovery import (DerivedState, DerivedValue, Document, EmploymentFact, RecoveryFact)
from .rendering.preparation import _duration


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def endpoint(field, facts: list[RecoveryFact]) -> PartialDate | None:
    try:
        return partial_date(field.text.strip())
    except ValueError:
        for fact in facts:
            if isinstance(fact, EmploymentFact) and fact.id in field.fact_ids:
                for period in fact.value.periods:
                    if field.text and field.text == period.start_text:
                        return period.start
                    if field.text and field.text == period.end_text:
                        return period.end
    return None


def initial_derived(document: Document, facts: list[RecoveryFact], employment: list[Job],
                    observed: PartialDate | None, revision: int, language: str) -> DerivedState:
    stamp = digest({"document": document.model_dump(mode="json", by_alias=True),
                    "facts": [fact.model_dump(mode="json", by_alias=True) for fact in facts],
                    "observed": observed.model_dump() if observed else None})
    values = []
    mapped = {job.id: job for job in document.jobs}
    original = {job.id: job for job in employment}
    periods = {}
    complete = {}
    for id, job in original.items():
        if id in mapped:
            periods[id] = []
            complete[id] = bool(mapped[id].periods)
            for item in mapped[id].periods:
                start = endpoint(item.start_text, facts)
                end = endpoint(item.end_text, facts)
                for field, parsed in ((item.start_text, start), (item.end_text, end)):
                    values.append(DerivedValue(fieldId=field.field_id, parsedDate=parsed,
                        canonicalAliases=[], monthsMin=None, monthsMax=None, display=None,
                        valid=parsed is not None or (field is item.end_text and item.present),
                        completeExposure=False, dependencyFingerprint=stamp))
                if start and (end or item.present) and (not end or start.lower() <= end.upper()):
                    periods[id].append(Period(start=start, end=end if not item.present else None))
                else:
                    complete[id] = False
        else:
            periods[id] = job.periods
            headers = [fact for fact in facts if isinstance(fact, EmploymentFact) and fact.value.job_id == id]
            complete[id] = bool(job.periods) and all(p.start and (p.end or p.present)
                                                   for fact in headers for p in fact.value.periods)
    for entry in document.skills_focus.focus:
        lower, upper = [], []
        supported = False
        full = True
        for fact in facts:
            if not isinstance(fact, TechnologyFact) or fact.id not in entry.fact_ids:
                continue
            if fact.value.scope == "global" or fact.job_id is None:
                continue
            job = original.get(fact.job_id)
            if job is None:
                full = False
                continue
            if fact.subproject_id:
                sub = next((sub for sub in job.subprojects if sub.id == fact.subproject_id), None)
                associated = [sub.period] if sub and sub.period else []
                full = full and bool(associated)
            else:
                associated = periods[job.id]
                full = full and complete[job.id]
            for period in associated:
                end = period.end or observed
                if end is None or period.start.lower() > end.upper():
                    full = False
                    continue
                a, b = month_bounds(period.start)
                c, d = month_bounds(end)
                lower.append((b, c))
                upper.append((a, d))
                supported = True
        minimum = union_months(lower) if supported else None
        maximum = union_months(upper) if supported else None
        values.append(DerivedValue(fieldId=entry.display.field_id, parsedDate=None,
            canonicalAliases=[entry.catalog_id], monthsMin=minimum, monthsMax=maximum,
            display=_duration(minimum, language) if full and minimum is not None else None,
            valid=True, completeExposure=full and supported, dependencyFingerprint=stamp))
    return DerivedState(documentRevision=revision, values=values)
