"""Inclusive employment warnings and explicitly applied forward cascades."""

from dataclasses import dataclass
from datetime import date
from itertools import combinations
from typing import Literal

from .dates import partial_date, estimate_exposure
from .models.contracts import Id, Period, Wire
from .models.rich_facts import EmploymentRecord, SubprojectRecord, WorkingPeriod
from .models.rich_mutations import ActionCapture, DateCascadeProposal, DateShift, PutRecord, RichMutation
from .rich_assembly import identity
from .rich_dependencies import dependency, dependencies_current, fingerprint
from .rich_fields import set_text
from .rich_panel import endpoint_steps
from .rich_sync import linked_field_steps
from .rich_dependencies import placements


class TimelineWarning(Wire):
    id: Id
    kind: Literal["overlap", "quality", "future"]
    code: Id
    certainty: Literal["possible", "certain"] | None
    job_ids: list[Id]
    period_ids: list[Id]


class TimelineEstimate(Wire):
    scope_id: Id
    months_min: int | None
    months_max: int | None
    reason: Id | None


class TimelineReport(Wire):
    warnings: list[TimelineWarning]
    estimates: list[TimelineEstimate]


class CascadeRequest(Wire):
    anchor_job_id: Id
    anchor_period_id: Id
    capture: ActionCapture


class CascadeApplyRequest(Wire):
    proposal: DateCascadeProposal
    capture: ActionCapture


@dataclass(frozen=True)
class Entry:
    job: EmploymentRecord | SubprojectRecord
    period: WorkingPeriod

    @property
    def start(self):
        return self.period.start.value if self.period.start.status == "known" else None

    @property
    def end(self):
        return self.period.end.value if self.period.end.status == "known" and self.period.present.value is False and self.period.present.status == "known" else None

    @property
    def invalid(self):
        return self.start is not None and self.end is not None and self.start.lower() > self.end.upper()

    @property
    def unit(self):
        return self.start.precision if self.start and self.end and self.start.precision == self.end.precision and self.start.precision in {"month", "day"} and not self.invalid else None


def entries(facts):
    return [Entry(record, period) for record in facts.records if record.kind == "employment" for period in record.periods]


def overlap(a, b):
    if a.invalid or b.invalid:
        return None
    start_lower = max(a.start.lower() if a.start else (1, 1, 1), b.start.lower() if b.start else (1, 1, 1))
    end_upper = min(a.end.upper() if a.end else (9999, 12, 31), b.end.upper() if b.end else (9999, 12, 31))
    if start_lower > end_upper:
        return None
    if all((a.start, a.end, b.start, b.end)) and max(a.start.upper(), b.start.upper()) <= min(a.end.lower(), b.end.lower()):
        return "certain"
    return "possible"


def warnings(facts, as_of):
    result, timeline = [], entries(facts)
    for entry in timeline:
        if entry.invalid or entry.start is None or entry.end is None:
            code = "DATE_ORDER_INVALID" if entry.invalid else "OPEN_PERIOD" if entry.period.present.value is True else "DATE_INCOMPLETE"
            result.append(TimelineWarning(id=f"quality:{entry.period.id}", kind="quality", code=code, certainty=None,
                jobIds=[entry.job.id], periodIds=[entry.period.id]))
        future = [point for point in (entry.start, entry.end) if point is not None and point.upper() > as_of.upper()]
        if future:
            result.append(TimelineWarning(id=f"future:{entry.period.id}", kind="future", code="FUTURE_DATE",
                certainty="certain" if any(point.lower() > as_of.upper() for point in future) else "possible",
                jobIds=[entry.job.id], periodIds=[entry.period.id]))
    for a, b in combinations(timeline, 2):
        certainty = overlap(a, b)
        if certainty:
            result.append(TimelineWarning(id="overlap:" + fingerprint(sorted([a.period.id, b.period.id])), kind="overlap", code="PERIOD_OVERLAP",
                certainty=certainty, jobIds=list(dict.fromkeys([a.job.id, b.job.id])), periodIds=[a.period.id, b.period.id]))
    return result


def estimate(scope, selected, as_of, observed_at):
    periods = []
    for entry in selected:
        ongoing = entry.period.present.status == "known" and entry.period.present.value is True
        if entry.start is None or entry.invalid or (entry.end is None and not ongoing):
            return TimelineEstimate(scopeId=scope, monthsMin=None, monthsMax=None, reason="DATE_INCOMPLETE")
        endpoint = observed_at if ongoing else entry.end
        if endpoint is None:
            return TimelineEstimate(scopeId=scope, monthsMin=None, monthsMax=None, reason="SOURCE_OBSERVATION_REQUIRED")
        if entry.start.lower() > endpoint.upper() or entry.start.upper() > as_of.upper() or endpoint.upper() > as_of.upper():
            return TimelineEstimate(scopeId=scope, monthsMin=None, monthsMax=None, reason="FUTURE_OR_INVALID_PERIOD")
        periods.append((entry.job.id, None, Period(start=entry.start, end=endpoint)))
    try:
        value = estimate_exposure(periods, as_of)
    except ValueError:
        value = None
    return TimelineEstimate(scopeId=scope, monthsMin=value.months_min if value else None,
        monthsMax=value.months_max if value else None, reason=None if value else "NO_DATED_EMPLOYMENT")


def timeline_report(workspace):
    if workspace.project is None:
        raise ValueError("DOCUMENT_REQUIRED")
    timeline = entries(workspace.project.facts)
    estimates = [estimate("employment", timeline, workspace.formatting_as_of, workspace.source_observed_at)]
    for record in workspace.project.facts.records:
        if record.kind != "technology" or record.job_id is None:
            continue
        selected = [entry for entry in timeline if entry.job.id == record.job_id]
        if record.subproject_id is not None:
            sub = next((item for item in workspace.project.facts.records if item.id == record.subproject_id and item.kind == "subproject"), None)
            selected = [Entry(sub, period) for period in sub.periods] if sub else []
        estimates.append(estimate(record.id, selected, workspace.formatting_as_of, workspace.source_observed_at))
    return TimelineReport(warnings=warnings(workspace.project.facts, workspace.formatting_as_of), estimates=estimates)


def unit_value(point, unit):
    return point.year * 12 + point.month - 1 if unit == "month" else date(*point.lower()).toordinal()


def unit_date(value, unit):
    if unit == "month":
        year, month = divmod(value, 12)
        return partial_date(f"{year:04d}-{month + 1:02d}")
    return partial_date(date.fromordinal(value).isoformat())


def date_text(point):
    return f"{point.year:04d}" + (f"-{point.month:02d}" if point.month else "") + (f"-{point.day:02d}" if point.day else "")


def cascade_proposal(workspace, request, proposal_id=None):
    if workspace.project is None:
        raise ValueError("DOCUMENT_REQUIRED")
    if not dependencies_current(workspace, request.capture.dependencies):
        raise ValueError("STALE_CASCADE")
    timeline = entries(workspace.project.facts)
    anchor = next((entry for entry in timeline if entry.job.id == request.anchor_job_id and entry.period.id == request.anchor_period_id), None)
    if anchor is None:
        raise ValueError("ANCHOR_PERIOD_MISSING")
    ordered = sorted(timeline, key=lambda entry: (entry.start.lower() if entry.start else (1, 1, 1),
        0 if entry.period.id == anchor.period.id else 1, entry.job.id, entry.period.id))
    stamps = [dependency(workspace, "period", entry.period.id) for entry in timeline]
    stamps.append(dependency(workspace, "timeline_order", "employment"))
    capture = request.capture.model_copy(update={"dependencies": stamps})
    order, shifts = [entry.period.id for entry in ordered], []
    def result(reason=None):
        return DateCascadeProposal(id=proposal_id or identity("cascade"), anchorJobId=anchor.job.id, anchorPeriodId=anchor.period.id,
            formattingAsOf=workspace.formatting_as_of, capture=capture, periodOrder=order, shifts=[] if reason else shifts,
            status="unavailable" if reason else "available", reason=reason,
            warnings=[warning.id for warning in warnings(workspace.project.facts, workspace.formatting_as_of)])
    if anchor.unit is None:
        return result("EXACT_CLOSED_PERIOD_REQUIRED")
    index = order.index(anchor.period.id)
    if any(overlap(previous, anchor) for previous in ordered[:index]):
        return result("EARLIER_OR_UNCERTAIN_OVERLAP")
    frontier = anchor
    for entry in ordered[index + 1:]:
        if entry.invalid and entry.start.lower() <= frontier.end.upper():
            return result("CHAIN_PRECISION_OR_OPEN_BOUNDARY")
        if not overlap(frontier, entry):
            break
        if entry.unit != anchor.unit:
            return result("CHAIN_PRECISION_OR_OPEN_BOUNDARY")
        span = unit_value(entry.end, entry.unit) - unit_value(entry.start, entry.unit) + 1
        start = unit_value(frontier.end, anchor.unit) + 1
        try:
            after_start, after_end = unit_date(start, anchor.unit), unit_date(start + span - 1, anchor.unit)
        except (ValueError, OverflowError):
            return result("DATE_RANGE_EXCEEDED")
        if after_end.upper() > workspace.formatting_as_of.upper():
            return result("FUTURE_BOUNDARY")
        copy = entry.job.model_copy(deep=True)
        set_text(copy, f"period:{entry.period.id}:start", date_text(after_start))
        set_text(copy, f"period:{entry.period.id}:end", date_text(after_end))
        shifted = next(period for period in copy.periods if period.id == entry.period.id)
        shifts.append(DateShift(jobId=entry.job.id, periodId=entry.period.id, before=entry.period, after=shifted,
            unit=anchor.unit, inclusiveSpan=span))
        # The occupied chain starts at the anchor, including earlier tied periods.
        frontier = Entry(copy, shifted.model_copy(update={"start": anchor.period.start}))
    if not shifts:
        return result("NO_FORWARD_OVERLAP")
    preview = workspace.model_copy(deep=True)
    for shift in shifts:
        record = next(record for record in preview.project.facts.records if record.id == shift.job_id)
        record.periods = [shift.after if period.id == shift.period_id else period for period in record.periods]
    proposal = result()
    proposal.warnings = [warning.id for warning in warnings(preview.project.facts, preview.formatting_as_of)]
    return proposal


def cascade_mutation(workspace, request):
    proposal = request.proposal
    if proposal.status != "available" or proposal.formatting_as_of != workspace.formatting_as_of or not dependencies_current(workspace, proposal.capture.dependencies):
        raise ValueError("STALE_CASCADE")
    expected = cascade_proposal(workspace, CascadeRequest(anchorJobId=proposal.anchor_job_id,
        anchorPeriodId=proposal.anchor_period_id, capture=proposal.capture), proposal.id)
    if expected.model_dump() != proposal.model_dump():
        raise ValueError("STALE_CASCADE")
    preview = workspace.model_copy(deep=True)
    changed = {}
    for shift in proposal.shifts:
        record = next(record for record in preview.project.facts.records if record.id == shift.job_id)
        record.periods = [shift.after.model_copy(deep=True) if period.id == shift.period_id else period for period in record.periods]
        record.user_corrected = True
        changed[record.id] = record
    steps = [PutRecord(kind="put_record", beforeRevision=record.revision, record=record) for record in changed.values()]
    steps += linked_field_steps(preview, list(changed))
    for record in changed.values():
        steps = endpoint_steps(workspace.project, record, steps, placements(workspace.project.document))
    return RichMutation(schemaVersion=1, projectId=workspace.project_id, clientMutationId=identity("cascade-apply"),
        actionId=request.capture.action_id, kind="cascade", capture=request.capture, steps=steps)
