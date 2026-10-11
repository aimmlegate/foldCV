"""Pure technology and early-career selection; never changes source facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .dates import ExperienceEstimate, month_bounds, old_job, project_experience
from .models.contracts import Job, PartialDate, Project, TechnologyFact
from .technologies import BY_ID, CATALOG, CatalogEntry, resolve_technology


@dataclass(frozen=True)
class FocusItem:
    canonical_id: str
    display: str
    logo: str
    experience: ExperienceEstimate | None
    fact_ids: tuple[str, ...]


def _latest_jobs(project: Project) -> set[str]:
    dated = [job for job in project.employment if job.periods]
    observation = month_bounds(project.as_of)[0] if project.as_of is not None else None

    def rank(job: Job) -> tuple[int, int, str]:
        latest = max(month_bounds(period.end or project.as_of or period.start)[0]
                     for period in job.periods)
        if observation is not None:
            latest = min(latest, observation)
        start = max(month_bounds(period.start)[0] for period in job.periods)
        return (-latest, -start, job.id)

    dated.sort(key=rank)
    return {job.id for job in dated[:2]}


def select_focus(project: Project, available_logo_paths: Iterable[str],
                 role_priorities: Mapping[str, int] | None = None,
                 explicit_order: Iterable[str] = (), limit: int = 8) -> tuple[FocusItem, ...]:
    if not 0 <= limit <= 8:
        raise ValueError("Focus limit must be between zero and eight")
    available = set(available_logo_paths)
    priorities = role_priorities or {}
    override = tuple(explicit_order)
    if len(override) != len(set(override)) or any(item not in BY_ID for item in override):
        raise ValueError("Explicit focus order contains duplicate or unknown IDs")
    latest = _latest_jobs(project)
    facts_by_id: dict[str, list[TechnologyFact]] = {}
    for fact in project.facts:
        if isinstance(fact, TechnologyFact) and fact.value.canonical_id in BY_ID:
            facts_by_id.setdefault(fact.value.canonical_id, []).append(fact)
    ranked = []
    for entry in CATALOG:
        facts = facts_by_id.get(entry.canonical_id, [])
        if not any(fact.job_id is not None for fact in facts) or entry.logo is None or entry.logo not in available:
            continue
        facts.sort(key=lambda fact: (fact.job_id is None, fact.id))
        experience = project_experience(project, entry.canonical_id)
        recent = any(fact.job_id in latest for fact in facts)
        last_use = max((interval.upper[1] for interval in experience.intervals), default=-1) if experience else -1
        months = experience.months_max if experience else 0
        explicit = override.index(entry.canonical_id) if entry.canonical_id in override else len(override)
        key = (0 if entry.canonical_id in override else 1, explicit,
               priorities.get(entry.canonical_id, 10_000), 0 if recent else 1,
               -last_use, -months, entry.canonical_id)
        ranked.append((key, FocusItem(entry.canonical_id, facts[0].value.display,
                                       entry.logo, experience,
                                       tuple(sorted(fact.id for fact in facts)))))
    return tuple(item for _, item in sorted(ranked, key=lambda item: item[0])[:limit])


def group_technologies(project: Project) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for fact in project.facts:
        if isinstance(fact, TechnologyFact):
            entry = BY_ID.get(fact.value.canonical_id)
            if entry is None:
                entry = BY_ID.get(resolve_technology(fact.value.display).canonical_id)
            category = entry.category if entry else "other"
            groups.setdefault(category, [])
            if fact.value.display not in groups[category]:
                groups[category].append(fact.value.display)
    return {category: tuple(sorted(names, key=str.casefold)) for category, names in sorted(groups.items())}


@dataclass(frozen=True)
class EarlyCareerRow:
    job_id: str
    employer: str
    role: str
    periods: tuple[str, ...]
    labels: tuple[str, ...]


def _date_text(value: PartialDate | None) -> str:
    if value is None:
        return "present"
    return f"{value.year:04d}" + (f"-{value.month:02d}" if value.month is not None else "") + (
        f"-{value.day:02d}" if value.day is not None else "")


def early_career_rows(jobs: Iterable[Job], as_of: PartialDate,
                      approved_labels: Mapping[str, Iterable[str]] | None = None) -> tuple[EarlyCareerRow, ...]:
    labels = approved_labels or {}
    result = []
    for job in jobs:
        if not job.periods or not all(old_job(period.end, as_of) for period in job.periods):
            continue
        periods = tuple(f"{_date_text(period.start)}–{_date_text(period.end)}" for period in job.periods)
        result.append(EarlyCareerRow(job.id, job.employer, job.role, periods,
                                     tuple(labels.get(job.id, ()))))
    result.sort(key=lambda item: item.job_id)
    return tuple(result)


def format_early_career(row: EarlyCareerRow) -> str:
    periods = ", ".join(row.periods)
    text = f"{row.employer} — {row.role} ({periods})"
    return text + (": " + ", ".join(row.labels) if row.labels else "")
