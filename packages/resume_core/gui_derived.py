"""Initial pure projections; observation evidence alone bounds ongoing exposure."""

from __future__ import annotations

import hashlib
import json
import re

from .dates import month_bounds, partial_date, union_months
from .models.contracts import Job, PartialDate, Period, TechnologyFact
from .models.recovery import (DerivedState, DerivedValue, Document, EmploymentFact, RecoveryFact)
from .rendering.preparation import _duration
from .technologies import canonical_id


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


def aliases(text: str) -> list[str]:
    result = []
    for part in re.split(r"[,;\n|]", text):
        id = canonical_id(part.strip())
        candidates = [id] if id else [canonical_id(piece.strip()) for piece in part.split("/")]
        for candidate in candidates:
            if candidate and candidate not in result:
                result.append(candidate)
    return result


def complete_period(period, facts):
    start, end = endpoint(period.start_text, facts), endpoint(period.end_text, facts)
    return bool(start and (not period.end_text.text.strip() if period.present
                          else end is not None and start.lower() <= end.upper()))


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
    active = list(dict.fromkeys([*mapped, *document.early_career.represented_job_ids]))
    for id in active:
        if id in mapped:
            periods[id] = []
            complete[id] = bool(mapped[id].periods)
            for item in mapped[id].periods:
                start = endpoint(item.start_text, facts)
                end = endpoint(item.end_text, facts)
                for field, parsed in ((item.start_text, start), (item.end_text, end)):
                    valid = parsed is not None
                    if field is item.end_text:
                        valid = not field.text.strip() if item.present else parsed is not None and (not start or start.lower() <= parsed.upper())
                    values.append(DerivedValue(fieldId=field.field_id, parsedDate=parsed,
                        canonicalAliases=[], monthsMin=None, monthsMax=None, display=None,
                        valid=valid,
                        completeExposure=False, dependencyFingerprint=stamp))
                if complete_period(item, facts):
                    periods[id].append(Period(start=start, end=end if not item.present else None))
                else:
                    complete[id] = False
        else:
            job = original.get(id)
            if job is None:
                continue
            periods[id] = job.periods
            headers = [fact for fact in facts if isinstance(fact, EmploymentFact) and fact.value.job_id == id]
            complete[id] = bool(job.periods) and all(p.start and (not p.end_text.strip() if p.present else p.end and p.start.lower() <= p.end.upper())
                                                   for fact in headers for p in fact.value.periods)
    for record in [*document.jobs, document.skills_focus]:
        field = record.stack if record.kind == "job" else record.skills_text
        values.append(DerivedValue(fieldId=field.field_id, parsedDate=None, canonicalAliases=aliases(field.text),
            monthsMin=None, monthsMax=None, display=None, valid=True, completeExposure=False, dependencyFingerprint=stamp))
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
            current = mapped.get(fact.job_id)
            if fact.job_id not in active or fact.job_id not in periods:
                continue
            if current and current.stack.origin == "user" and entry.catalog_id not in aliases(current.stack.text):
                continue
            if job is None:
                full = False
                continue
            if fact.subproject_id:
                sub = next((sub for sub in job.subprojects if sub.id == fact.subproject_id), None)
                associated = [sub.period] if sub and sub.period else []
                full = full and bool(associated) and complete[job.id]
                if current and any(field.origin == "user" for period in current.periods for field in (period.start_text, period.end_text)):
                    contained = all(any(bound.start.lower() <= period.start.lower() and bound.end is not None
                        and period.end is not None and period.end.upper() <= bound.end.upper() for bound in periods[job.id]) for period in associated)
                    if not contained:
                        associated, full = [], False
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
        for job in document.jobs:
            if job.stack.origin != "user" or entry.catalog_id not in aliases(job.stack.text):
                continue
            if any(isinstance(fact, TechnologyFact) and fact.id in entry.fact_ids and fact.job_id == job.id for fact in facts):
                continue
            full = full and complete.get(job.id, False)
            for period in periods.get(job.id, []):
                end = period.end or observed
                if end is None or period.start.lower() > end.upper():
                    full = False
                    continue
                a, b = month_bounds(period.start)
                c, d = month_bounds(end)
                lower.append((b, c)); upper.append((a, d)); supported = True
        minimum = union_months(lower) if supported else None
        maximum = union_months(upper) if supported else None
        values.append(DerivedValue(fieldId=entry.display.field_id, parsedDate=None,
            canonicalAliases=[entry.catalog_id], monthsMin=minimum, monthsMax=maximum,
            display=_duration(minimum, language) if full and minimum is not None else None,
            valid=True, completeExposure=full and supported, dependencyFingerprint=stamp))
    return DerivedState(documentRevision=revision, values=values)
