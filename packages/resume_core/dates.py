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


@dataclass(frozen=True)
class DatePattern:
    """How a source writes its dates, down to `precision`: numbers with a separator, day first or year first, or a month
    name before the year."""
    precision: str
    separator: str = "."
    year_first: bool = False
    months: tuple[str, ...] = ()


ISO_DATE = DatePattern("day", "-", True)
_MONTH_NAMES = tuple(tuple(names.split()) for names in (
    "январь февраль март апрель май июнь июль август сентябрь октябрь ноябрь декабрь",
    "янв фев мар апр май июн июл авг сен окт ноя дек",
    "january february march april may june july august september october november december",
    "jan feb mar apr may jun jul aug sep oct nov dec"))
_PRECISIONS = ("year", "month", "day")


def source_date(text: str) -> tuple[PartialDate, DatePattern] | None:
    """The date a source writes as 2020, 2020-03, 03.2020, 15/03/2020 or Март 2020, with how it writes it; None for
    anything else."""
    value = text.strip()
    try:
        if re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
            point = partial_date(value)
            return point, DatePattern(point.precision, "-", True)
        match = re.fullmatch(r"(?:(\d{1,2})([./]))?(\d{1,2})([./])(\d{4})", value)
        if match and match[2] in {None, match[4]}:
            day, month, year = match[1], int(match[3]), int(match[5])
            precision = "day" if day else "month"
            return (PartialDate(precision=precision, year=year, month=month, day=int(day) if day else None),
                DatePattern(precision, match[4]))
        match = re.fullmatch(r"(\w+)\.?\s+(\d{4})", value)
        months = next((names for names in _MONTH_NAMES if match and match[1].lower() in names), None)
        if months:
            names = tuple(name.capitalize() for name in months) if match[1][0].isupper() else months
            return (PartialDate(precision="month", year=int(match[2]), month=months.index(match[1].lower()) + 1, day=None),
                DatePattern("month", months=names))
    except ValueError:
        pass
    return None


def format_date(value: PartialDate, pattern: DatePattern) -> str:
    """The date as the pattern writes it, at the coarser of their precisions."""
    precision = _PRECISIONS[min(_PRECISIONS.index(value.precision), _PRECISIONS.index(pattern.precision))]
    year = f"{value.year:04d}"
    if precision == "year":
        return year
    if pattern.months:
        return f"{pattern.months[value.month - 1]} {year}"
    parts = [year, f"{value.month:02d}"] if pattern.year_first else [f"{value.month:02d}", year]
    if precision == "day":
        parts = [*parts, f"{value.day:02d}"] if pattern.year_first else [f"{value.day:02d}", *parts]
    return pattern.separator.join(parts)


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
