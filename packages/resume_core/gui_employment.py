"""GUI employment and scoped claims from the same normalization response."""

from __future__ import annotations

from collections import defaultdict
import re

from .gui_normalization import (
    FactConflict, GuiNormalizeRequest, GuiNormalizedResult, GuiSemanticProposal,
    NormalizationFailure, NormalizedPeriod, validate_span, literal_contains, supported_text,
)
from .models.contracts import Job, PartialDate, Period, Subproject, TechnologyValue
from .models.recovery import EvidenceSpan, EmploymentFact, GuiTextFact, GuiTechnologyFact, GuiMetricFact, GuiLeadershipFact, GuiDateFact
from .normalization import _id, _observed_date, _observed_number
from .technologies import resolve_technology


FACT_TYPES = {"text": GuiTextFact, "technology": GuiTechnologyFact, "metric": GuiMetricFact,
              "leadership": GuiLeadershipFact, "date": GuiDateFact}
PRESENT = re.compile(r"(?<!\w)(?:по\s+)?(?:настоящее\s+время|н\.?\s*в\.?|present|current|ongoing|to\s+date)(?!\w)", re.I)
NEGATED_PRESENT = re.compile(r"(?<!\w)(?:not|no|never|не|нет)\s+"
    r"(?:(?:longer|still|currently|уже|более)\s+)*" + PRESENT.pattern, re.I)


def _explicit_present(text: str) -> bool:
    negated = [match.span() for match in NEGATED_PRESENT.finditer(text)]
    return any(not any(start <= match.start() < end for start, end in negated)
               for match in PRESENT.finditer(text))


def _supported_header(value, source_id, unit_ids, sources):
    source = next(source for source in sources if source.id == source_id)
    groups = []
    previous = None
    for unit in sorted((unit for unit in source.units if unit.id in unit_ids), key=lambda unit: unit.order):
        if previous is None or previous.order + 1 != unit.order or previous.location != unit.location:
            groups.append([])
        groups[-1].append(EvidenceSpan(sourceId=source.id, sourceRevision=source.revision,
            unitId=unit.id, unitRevision=unit.revision, text=unit.text))
        previous = unit
    return any(supported_text(value, group, sources) for group in groups)


def _date_text(date: PartialDate | None) -> str:
    if date is None:
        return ""
    text = f"{date.year:04d}"
    if date.month is not None:
        text += f"-{date.month:02d}"
    if date.day is not None:
        text += f"-{date.day:02d}"
    return text


def normalize_employment(request: GuiNormalizeRequest, proposal: GuiSemanticProposal,
                         candidate: GuiNormalizedResult) -> GuiNormalizedResult:
    result = candidate.model_copy(deep=True)
    units = {(source.id, unit.id): unit for source in result.sources for unit in source.units}
    proposed_jobs = {job.temp_id: job for job in proposal.jobs}
    if len(proposed_jobs) != len(proposal.jobs) or len({fact.temp_id for fact in proposal.facts}) != len(proposal.facts):
        raise NormalizationFailure("DUPLICATE_NORMALIZATION_ID")
    job_ids = {temp: _id("job", job.source_id, job.employer, job.role, *sorted(job.unit_ids))
               for temp, job in proposed_jobs.items()}
    if len(set(job_ids.values())) != len(job_ids):
        raise NormalizationFailure("DUPLICATE_EMPLOYMENT")
    sub_ids = {}
    jobs = []
    job_periods = {}
    for temp, job in proposed_jobs.items():
        if not job.unit_ids or len(set(job.unit_ids)) != len(job.unit_ids) or any((job.source_id, uid) not in units for uid in job.unit_ids):
            raise NormalizationFailure("INVALID_JOB_EVIDENCE")
        text = "\n".join(units[(job.source_id, uid)].text for uid in job.unit_ids)
        if any(not _supported_header(value, job.source_id, job.unit_ids, result.sources) for value in (job.employer, job.role)):
            raise NormalizationFailure("UNSUPPORTED_EMPLOYMENT_LITERAL")
        periods = []
        projection = []
        for index, period in enumerate(job.periods):
            refs = [validate_span(span, result.sources) for span in period.evidence]
            if refs and any(ref.source_id != job.source_id or ref.unit_id not in job.unit_ids for ref in refs):
                raise NormalizationFailure("PERIOD_OUTSIDE_JOB")
            evidence_text = "\n".join(span.text for span in period.evidence) if refs else text
            for date in (period.start, period.end):
                if date is not None and not _observed_date(date, evidence_text):
                    raise NormalizationFailure("UNSUPPORTED_EMPLOYMENT_DATE")
            if period.present and (period.start is None or period.end is not None):
                raise NormalizationFailure("INVALID_PRESENT_PERIOD")
            # Source endpoints may include duration text around the present phrase.
            if period.present and (not _explicit_present(evidence_text) or
                    period.end_text and not _explicit_present(period.end_text)):
                raise NormalizationFailure("INVALID_PRESENT_PERIOD")
            if period.start and period.end and period.start.lower() > period.end.upper():
                raise NormalizationFailure("INVALID_EMPLOYMENT_PERIOD")
            start_text = period.start_text if period.start_text is not None else _date_text(period.start)
            end_text = "" if period.present else period.end_text if period.end_text is not None else _date_text(period.end)
            if period.start_text and not literal_contains(period.start_text, evidence_text) or period.end_text and not literal_contains(period.end_text, evidence_text):
                raise NormalizationFailure("UNSUPPORTED_PERIOD_TEXT")
            periods.append(NormalizedPeriod.model_validate({"id": _id("period", job_ids[temp], str(index), start_text, end_text),
                "start": period.start.model_dump(by_alias=True) if period.start else None,
                "end": period.end.model_dump(by_alias=True) if period.end else None,
                "startText": start_text, "endText": end_text, "present": period.present,
                "evidence": [span.model_dump(by_alias=True) for span in period.evidence]}))
            if period.start and (period.end or period.present):
                projection.append(Period(start=period.start, end=period.end))
        subprojects = []
        for sub in job.subprojects:
            if (temp, sub.temp_id) in sub_ids or not sub.unit_ids or not set(sub.unit_ids) <= set(job.unit_ids):
                raise NormalizationFailure("INVALID_SUBPROJECT_EVIDENCE")
            subtext = "\n".join(units[(job.source_id, uid)].text for uid in sub.unit_ids)
            if not _supported_header(sub.name, job.source_id, sub.unit_ids, result.sources):
                raise NormalizationFailure("UNSUPPORTED_SUBPROJECT_LITERAL")
            if sub.period:
                for date in (sub.period.start, sub.period.end):
                    if date and not _observed_date(date, subtext):
                        raise NormalizationFailure("UNSUPPORTED_SUBPROJECT_DATE")
                if not any(parent.start.lower() <= sub.period.start.lower() and
                           (parent.end is None or sub.period.end is not None and sub.period.end.upper() <= parent.end.upper())
                           for parent in projection):
                    raise NormalizationFailure("SUBPROJECT_OUTSIDE_JOB")
            sub_id = _id("subproject", job_ids[temp], sub.name, *sorted(sub.unit_ids))
            sub_ids[(temp, sub.temp_id)] = sub_id
            subprojects.append(Subproject.model_validate({"id": sub_id, "name": sub.name,
                                  "period": sub.period.model_dump(by_alias=True) if sub.period else None, "factIds": []}))
        jobs.append(Job.model_validate({"id": job_ids[temp], "employer": job.employer, "role": job.role,
                                       "periods": [period.model_dump(by_alias=True) for period in projection],
                                       "subprojects": [sub.model_dump(by_alias=True) for sub in subprojects], "factIds": []}))
        job_periods[job_ids[temp]] = periods
    fact_ids = {}
    team_claims = defaultdict(list)
    for item in proposal.facts:
        if not item.literal_evidence:
            raise NormalizationFailure("FACT_NEEDS_LITERAL_EVIDENCE")
        refs = [validate_span(span, result.sources) for span in item.literal_evidence]
        if any(ref.source_id != item.source_id for ref in refs) or set(item.unit_ids) != {ref.unit_id for ref in refs}:
            raise NormalizationFailure("FACT_EVIDENCE_MISMATCH")
        job = proposed_jobs.get(item.job_temp_id) if item.job_temp_id else None
        if item.job_temp_id and (job is None or job.source_id != item.source_id or not set(item.unit_ids) <= set(job.unit_ids)):
            raise NormalizationFailure("FACT_OUTSIDE_JOB")
        sub_id = sub_ids.get((item.job_temp_id, item.subproject_temp_id)) if item.subproject_temp_id else None
        if item.subproject_temp_id and (sub_id is None or job is None or not set(item.unit_ids) <= set(
                next(sub.unit_ids for sub in job.subprojects if sub.temp_id == item.subproject_temp_id))):
            raise NormalizationFailure("FACT_OUTSIDE_SUBPROJECT")
        literal = "\n".join(span.text for span in item.literal_evidence)
        value = item.value.model_dump(mode="json", by_alias=True)
        if item.kind == "text" and item.value.text not in literal and not any(
                literal_contains(item.value.text, span.text) for span in item.literal_evidence):
            raise NormalizationFailure("UNSUPPORTED_FACT_TEXT")
        if item.kind == "date" and not _observed_date(item.value, literal):
            raise NormalizationFailure("UNSUPPORTED_FACT_DATE")
        if item.kind == "metric":
            metric = item.value
            for number in [metric.number, *([metric.upper_number] if metric.upper_number is not None else [])]:
                if not _observed_number(number, literal):
                    raise NormalizationFailure("UNSUPPORTED_METRIC_NUMBER")
            if metric.unit.casefold() not in literal.casefold() or any(qualifier.casefold() not in literal.casefold() for qualifier in metric.qualifiers):
                raise NormalizationFailure("UNSUPPORTED_METRIC_QUALIFIER")
            if any(text is not None and text not in literal for text in (metric.baseline, metric.result)):
                raise NormalizationFailure("UNSUPPORTED_METRIC_BOUNDS")
        if item.kind == "technology":
            technology = item.value
            if not isinstance(technology, TechnologyValue) or not any(
                    literal_contains(technology.display.casefold(), span.text.casefold()) for span in item.literal_evidence):
                raise NormalizationFailure("UNSUPPORTED_TECHNOLOGY_LITERAL")
            if (technology.scope == "global" and job is not None or
                technology.scope == "job" and (job is None or sub_id is not None) or
                technology.scope == "subproject" and sub_id is None):
                raise NormalizationFailure("TECHNOLOGY_SCOPE_MISMATCH")
            resolved = resolve_technology(technology.display)
            value["canonicalId"] = resolved.canonical_id or _id("unknown", technology.display)
        if item.kind == "leadership" and item.value.team_size and re.search(r"\d", literal):
            size = item.value.team_size
            if any(not _observed_number(number, literal) for number in [size.number, *(
                    [size.upper_number] if size.upper_number is not None else [])]):
                raise NormalizationFailure("UNSUPPORTED_TEAM_SIZE")
        # Word-number claims remain model assertions backed by literal spans, not a numeral parser.
        identity = _id("fact", item.temp_id, item.source_id, item.kind, *[span.text for span in item.literal_evidence])
        if identity in {fact.id for fact in result.facts}:
            raise NormalizationFailure("DUPLICATE_FACT")
        fact = FACT_TYPES[item.kind].model_validate({"id": identity, "revision": request.revision,
            "kind": item.kind, "value": value, "evidence": [ref.model_dump(by_alias=True) for ref in refs],
            "literalEvidence": [span.model_dump(by_alias=True) for span in item.literal_evidence],
            "origin": "source", "importance": item.importance,
            "jobId": job_ids[item.job_temp_id] if item.job_temp_id else None, "subprojectId": sub_id})
        result.facts.append(fact)
        fact_ids[item.temp_id] = fact.id
        for ref in refs:
            unit = units[(ref.source_id, ref.unit_id)]
            if fact.id not in unit.represented_fact_ids:
                unit.represented_fact_ids.append(fact.id)
        if fact.job_id:
            owned = next(job for job in jobs if job.id == fact.job_id)
            owned.fact_ids.append(fact.id)
            if sub_id:
                next(sub for sub in owned.subprojects if sub.id == sub_id).fact_ids.append(fact.id)
        if isinstance(fact, GuiLeadershipFact) and fact.job_id and fact.value.team_size:
            size = fact.value.team_size
            team_claims[(fact.job_id, fact.subproject_id, size.period, size.scope)].append(fact)
    accounts = {(account.source_id, account.unit_id): account for account in proposal.units}
    if len(accounts) != len(proposal.units) or set(accounts) != set(units):
        raise NormalizationFailure("INCOMPLETE_UNIT_ACCOUNTING")
    for key, account in accounts.items():
        if not set(account.fact_temp_ids) <= set(fact_ids) or len(set(account.fact_temp_ids)) != len(account.fact_temp_ids):
            raise NormalizationFailure("INVALID_UNIT_FACT_REFERENCE")
        mapped = [fact_ids[temp] for temp in account.fact_temp_ids]
        expected = [fact.id for fact in result.facts if fact.id in set(fact_ids.values()) and any(
                    ref.source_id == key[0] and ref.unit_id == key[1] for ref in fact.evidence)]
        if set(mapped) != set(expected):
            raise NormalizationFailure("UNIT_FACT_COVERAGE_MISMATCH")
        if account.disposition == "duplicate":
            if account.fact_temp_ids or not account.duplicate_of or account.duplicate_of not in {f"{source}:{unit}" for source, unit in units}:
                raise NormalizationFailure("INVALID_DUPLICATE_UNIT")
        units[key].disposition = {"facts": "shown", "administrative": "administrative", "duplicate": "duplicate", "unresolved": "unresolved"}[account.disposition]
    conflicts = []
    for (job_id, _sub, _period, _scope), claims in team_claims.items():
        if len({claim.value.team_size.number for claim in claims}) > 1:
            conflicts.append(FactConflict.model_validate({"id": _id("conflict", job_id, *sorted(claim.id for claim in claims)),
                "jobId": job_id, "code": "team_size_conflict", "factIds": [claim.id for claim in claims],
                "evidence": [span.model_dump(by_alias=True) for claim in claims for span in claim.literal_evidence]}))
    for temp, original in proposed_jobs.items():
        job = next(job for job in jobs if job.id == job_ids[temp])
        spans = [{"sourceId": original.source_id, "sourceRevision": next(source.revision for source in result.sources if source.id == original.source_id),
                  "unitId": uid, "unitRevision": units[(original.source_id, uid)].revision,
                  "text": units[(original.source_id, uid)].text} for uid in original.unit_ids]
        identity = _id("fact", "employment", job.id)
        header = EmploymentFact.model_validate({"id": identity, "revision": request.revision, "kind": "employment",
            "value": {"jobId": job.id, "employer": job.employer, "role": job.role,
                      "periods": [period.model_dump(by_alias=True) for period in job_periods[job.id]],
                      "subprojects": [sub.model_dump(by_alias=True) for sub in job.subprojects]},
            "evidence": [{key: value for key, value in span.items() if key != "text"} for span in spans],
            "literalEvidence": spans, "origin": "source", "importance": "essential", "jobId": job.id, "subprojectId": None})
        result.facts.append(header)
        job.fact_ids.append(header.id)
        for span in spans:
            units[(original.source_id, span["unitId"])].represented_fact_ids.append(header.id)
    result.employment = jobs
    result.job_periods = job_periods
    result.conflicts = conflicts
    return result
