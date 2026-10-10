"""Pure date and exposure policies for canonical resume models."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .models.contracts import PartialDate, Period, Project, TechnologyFact


def partial_date(value: str | PartialDate) -> PartialDate:
    if isinstance(value, PartialDate):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
        raise ValueError(f"Invalid normalized date: {value}")
    parts = [int(part) for part in value.split("-")]
    return PartialDate(precision=("year", "month", "day")[len(parts) - 1],
                       year=parts[0], month=parts[1] if len(parts) > 1 else None,
                       day=parts[2] if len(parts) > 2 else None)


def month_bounds(value: str | PartialDate) -> tuple[int, int]:
    point = partial_date(value)
    return (point.lower()[0] * 12 + point.lower()[1] - 1,
            point.upper()[0] * 12 + point.upper()[1] - 1)


def union_months(intervals: Iterable[tuple[int, int] | list[int]]) -> int:
    total, end = 0, -1
    for start, stop in sorted(intervals):
        if stop < start:
            continue
        total += max(0, stop - max(start, end + 1) + 1)
        end = max(end, stop)
    return total


def old_job(end: str | PartialDate | None, as_of: str | PartialDate) -> bool:
    if end is None:
        return False
    current = partial_date(as_of)
    # The earliest possible as-of day gives a conservative answer for partial dates.
    today = date(*current.lower())
    cutoff_year = today.year - 15
    if cutoff_year < 1:
        return False
    cutoff = today.replace(year=cutoff_year,
                           day=min(today.day, calendar.monthrange(cutoff_year, today.month)[1]))
    return date(*partial_date(end).upper()) < cutoff


@dataclass(frozen=True)
class ExposureInterval:
    job_id: str
    subproject_id: str | None
    start: PartialDate
    end: PartialDate
    lower: tuple[int, int]
    upper: tuple[int, int]


@dataclass(frozen=True)
class ExperienceEstimate:
    months_min: int
    months_max: int
    as_of: PartialDate
    intervals: tuple[ExposureInterval, ...]
    fact_ids: tuple[str, ...]


def exposure_intervals(periods: Iterable[tuple[str, str | None, Period]],
                       as_of: PartialDate) -> tuple[ExposureInterval, ...]:
    limit = month_bounds(as_of)[1]
    result = []
    for job_id, subproject_id, period in periods:
        end = period.end or as_of
        lo_start, hi_start = month_bounds(period.start)
        lo_end, hi_end = month_bounds(end)
        if period.start.lower() > as_of.upper() or lo_start > min(hi_end, limit):
            raise ValueError(f"Invalid or future interval in {job_id}")
        lower = (hi_start, min(lo_end, limit))
        upper = (lo_start, min(hi_end, limit))
        result.append(ExposureInterval(job_id, subproject_id, period.start, end, lower, upper))
    return tuple(result)


def estimate_exposure(periods: Iterable[tuple[str, str | None, Period]],
                      as_of: PartialDate | None, fact_ids: Iterable[str] = ()) -> ExperienceEstimate | None:
    # A missing observation date cannot silently become the machine's current date.
    if as_of is None:
        return None
    intervals = exposure_intervals(periods, as_of)
    if not intervals:
        return None
    return ExperienceEstimate(union_months(item.lower for item in intervals),
                              union_months(item.upper for item in intervals), as_of,
                              intervals, tuple(sorted(set(fact_ids))))


def project_experience(project: Project, canonical_id: str) -> ExperienceEstimate | None:
    periods: list[tuple[str, str | None, Period]] = []
    fact_ids: list[str] = []
    jobs = {job.id: job for job in project.employment}
    for fact in project.facts:
        if not isinstance(fact, TechnologyFact) or fact.value.canonical_id != canonical_id:
            continue
        if fact.value.scope == "global" or fact.job_id is None:
            continue
        if fact.value.scope == "subproject" and fact.subproject_id is None:
            continue
        job = jobs[fact.job_id]
        if fact.subproject_id:
            subproject = next(item for item in job.subprojects if item.id == fact.subproject_id)
            if subproject.period is None:
                continue
            associated = (subproject.period,)
        else:
            associated = tuple(job.periods)
        for period in associated:
            periods.append((job.id, fact.subproject_id, period))
        fact_ids.append(fact.id)
    return estimate_exposure(periods, project.as_of, fact_ids)
