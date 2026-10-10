"""Independent preservation and view selection checks on in-memory projects."""

from __future__ import annotations

from hashlib import sha256
from typing import Mapping

from .models.contracts import Project
from .technologies import BY_ID


def source_byte_issues(project: Project, source_bytes: Mapping[str, bytes]) -> tuple[str, ...]:
    issues = []
    for source in project.sources:
        original = source_bytes.get(source.byte_ref)
        if original is None or sha256(original).hexdigest() != source.byte_sha256:
            issues.append(f"{source.id}@{source.revision}: original bytes missing or changed")
    return tuple(issues)


def preservation_issues(current: Project, baseline: Project) -> tuple[str, ...]:
    """Compare retained facts and extraction against an explicit earlier snapshot."""
    if current.project_id != baseline.project_id:
        return ("project: baseline belongs to a different project",)

    issues = []
    current_sources = {(source.id, source.revision): source for source in current.sources}
    for original in baseline.sources:
        key = (original.id, original.revision)
        source = current_sources.get(key)
        label = f"{original.id}@{original.revision}"
        if source is None:
            issues.append(f"{label}: original source revision removed")
            continue
        source_fields = ("original_name", "mime_type", "byte_sha256", "byte_ref", "parser", "parser_version")
        if any(getattr(source, field) != getattr(original, field) for field in source_fields):
            issues.append(f"{label}: original source revision changed")
        units = {(unit.id, unit.revision): unit for unit in source.units}
        original_units = {(unit.id, unit.revision) for unit in original.units}
        for original_unit in original.units:
            unit = units.get((original_unit.id, original_unit.revision))
            unit_label = f"{label}/{original_unit.id}@{original_unit.revision}"
            if unit is None:
                issues.append(f"{unit_label}: extracted unit removed")
            elif (unit.order, unit.text, unit.location) != (
                original_unit.order, original_unit.text, original_unit.location
            ):
                issues.append(f"{unit_label}: extracted unit changed")
        for unit in source.units:
            if (unit.id, unit.revision) not in original_units:
                issues.append(f"{label}/{unit.id}@{unit.revision}: extracted unit added to original revision")

    facts = {fact.id: fact for fact in current.facts}
    for original in baseline.facts:
        fact = facts.get(original.id)
        if fact is None:
            issues.append(f"{original.id}: fact removed")
        elif fact.revision < original.revision:
            issues.append(f"{original.id}: fact revision went backwards")
        elif fact.revision == original.revision and fact != original:
            issues.append(f"{original.id}@{original.revision}: fact changed without revision")
    return tuple(issues)


def selection_issues(project: Project, focus_ids: tuple[str, ...],
                     available_logo_paths: frozenset[str],
                     detailed_job_ids: tuple[str, ...],
                     early_job_ids: tuple[str, ...]) -> tuple[str, ...]:
    issues = []
    for source in project.sources:
        for unit in source.units:
            if unit.disposition == "unresolved":
                issues.append(f"{unit.id}: source unit unresolved")
    if len(focus_ids) > 8 or len(focus_ids) != len(set(focus_ids)):
        issues.append("focus: duplicate or more than eight technologies")
    technology_ids = {fact.value.canonical_id for fact in project.facts
                      if fact.kind == "technology" and fact.job_id is not None}
    for tech_id in focus_ids:
        entry = BY_ID.get(tech_id)
        if tech_id not in technology_ids or entry is None or entry.logo not in available_logo_paths:
            issues.append(f"{tech_id}: missing job link, catalog entry, or logo")
    all_jobs = {job.id for job in project.employment}
    selected = detailed_job_ids + early_job_ids
    if len(selected) != len(set(selected)) or set(selected) != all_jobs:
        issues.append("jobs: each job must appear exactly once")
    if project.as_of is not None:
        from .dates import old_job
        for job in project.employment:
            is_old = bool(job.periods) and all(old_job(period.end, project.as_of) for period in job.periods)
            if job.id in detailed_job_ids and is_old:
                issues.append(f"{job.id}: old job should be condensed")
            if job.id in early_job_ids and not is_old:
                issues.append(f"{job.id}: recent or undated job should be detailed")
    elif early_job_ids:
        issues.append("jobs: early-career selection requires an as-of date")
    return tuple(issues)
