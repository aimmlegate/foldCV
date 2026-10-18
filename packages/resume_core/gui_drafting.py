"""Complete GUI document assembly driven by the supplied EditorialPlan."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import date
from collections.abc import Callable

from pydantic import Field

from .gui_draft_recovery import DraftWarnings, fill_literal
from .gui_normalization import GuiNormalizedResult, public_context_facts
from .gui_prompts import content_input
from .models.contracts import Id, PartialDate, Revision, Wire
from .models.recovery import (
    Annotation, CandidateFact, Document, EditorialPlan, EmploymentFact, FocusEntry,
    Rules, JobDisposition, DocumentAnchor, authored_fields,
)
from .normalization import _id
from .technologies import BY_ID


class GuiDraftRequest(Wire):
    project_id: Id
    project_revision: Revision
    document_revision: Revision
    normalized: GuiNormalizedResult
    formatting_as_of: PartialDate


class DraftField(Wire):
    field_id: Id
    text: str = Field(max_length=12000)
    fact_ids: list[Id]


class GuiDraftProposal(Wire):
    fields: list[DraftField] = Field(max_length=1000)
    editorial_plan: EditorialPlan


class GuiDraftResult(Wire):
    document: Document
    editorial_plan: EditorialPlan
    annotations: list[Annotation]


class DraftFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def available_focus_ids() -> set[str]:
    root = Path(__file__).resolve().parents[2] / "skills/format-resume/assets"
    return {id for id, entry in BY_ID.items() if entry.logo and (root / entry.logo).is_file()}


def _field(id: str, text: str = "", facts: list[str] | None = None) -> dict:
    return {"fieldId": id, "text": text, "factIds": facts or [], "evidence": [], "origin": "source"}


def _record(kind: str, id: str, **fields) -> dict:
    return {"kind": kind, "id": id, "revision": 1, "visible": True, **fields}


def draft_skeleton(normalized: GuiNormalizedResult) -> Document:
    refs = normalized.field_fact_ids
    doc = {"candidate": _record("candidate", "candidate", **{key: _field(f"candidate/{key}", getattr(normalized.candidate, key).text, refs.get(f"candidate/{key}"))
              for key in ("name", "title", "location")}),
           "profile": _record("profile", "profile", text=_field("profile/text")),
           "jobs": [], "education": [], "certifications": [], "languages": [],
           "skillsFocus": _record("skills-focus", "skills-focus", skillsText=_field("skills-focus/skillsText"), focusFieldId="skills-focus/focus", focus=[]),
           "earlyCareer": _record("early-career", "early-career", text=_field("early-career/text"), representedJobIds=[])}
    for job in normalized.employment:
        prefix = f"job:{job.id}"
        header_ids = [fact.id for fact in normalized.facts if isinstance(fact, EmploymentFact) and fact.value.job_id == job.id]
        periods = [{"id": period.id, "startText": _field(f"{prefix}/period:{period.id}/startText", period.start_text, header_ids),
                    "endText": _field(f"{prefix}/period:{period.id}/endText", period.end_text, header_ids), "present": period.present}
                   for period in normalized.job_periods[job.id]]
        doc["jobs"].append(_record("job", job.id, employer=_field(prefix + "/employer", job.employer, header_ids),
            role=_field(prefix + "/role", job.role, header_ids), periodsFieldId=prefix + "/periods", periods=periods,
            context=_field(prefix + "/context"), tasks=_field(prefix + "/tasks"), results=_field(prefix + "/results"),
            stack=_field(prefix + "/stack"), subprojectIds=[sub.id for sub in job.subprojects]))
    doc["candidate"]["details"] = [_field(f"private/{row.kind}/{index}", row.value.text,
        refs.get(f"private/{row.kind}/{index}")) for index, row in enumerate(normalized.private_details)]
    groups = [("education", "education", normalized.education, ("institution", "qualification", "specialty", "date_text")),
              ("certifications", "certification", normalized.certifications, ("name", "issuer", "date_text")),
              ("languages", "language", normalized.languages, ("name", "proficiency"))]
    for collection, kind, rows, keys in groups:
        for row in rows:
            values = {}
            for key in keys:
                alias = "dateText" if key == "date_text" else key
                id = f"{kind}:{row.id}/{alias}"
                values[alias] = _field(id, getattr(row, key).text, refs.get(id))
            doc[collection].append(_record(kind, row.id, **values, legacyText=None))
    return Document.model_validate(doc)


def drafting_input(request: GuiDraftRequest, rules: Rules, *, transform: Callable[[str], str] | None = None,
                   return_canonical: bool = False) -> str:
    skeleton = draft_skeleton(request.normalized)
    excerpts = []
    for source in request.normalized.sources:
        for unit in source.units:
            excerpts.append({"sourceId": source.id, "unitId": unit.id, "text": unit.text})
    blocked = {id for conflict in request.normalized.conflicts for id in conflict.fact_ids}
    facts = []
    for fact in public_context_facts(request.normalized.facts):
        if fact.id in blocked:
            continue
        value = fact.model_dump(mode="json", by_alias=True, exclude={"evidence", "literal_evidence"})
        if isinstance(fact, EmploymentFact):
            value["value"] = fact.value.model_dump(mode="json", by_alias=True,
                exclude={"periods": {"__all__": {"evidence"}}})
        facts.append(value)
    active_jobs = []
    for job in request.normalized.employment:
        bounds = []
        for period in job.periods:
            item = {"startLower": period.start.lower(), "startUpper": period.start.upper(),
                    "endLower": period.end.lower() if period.end else None,
                    "endUpper": period.end.upper() if period.end else None,
                    "daysSinceEndBounds": None}
            if period.end:
                item["daysSinceEndBounds"] = [
                    (date(*request.formatting_as_of.lower()) - date(*period.end.upper())).days,
                    (date(*request.formatting_as_of.upper()) - date(*period.end.lower())).days,
                ]
            bounds.append(item)
        active_jobs.append({**job.model_dump(by_alias=True), "periodBounds": bounds})
    payload = {"projectId": request.project_id, "formattingAsOf": request.formatting_as_of.model_dump(by_alias=True),
               "sourceObservedAt": request.normalized.source_observed_at.model_dump(by_alias=True) if request.normalized.source_observed_at else None,
               "activeJobs": active_jobs,
               "facts": facts, "skeleton": skeleton.model_dump(by_alias=True), "sourceExcerpts": excerpts,
               "blockedConflictFactIds": sorted(blocked), "output": "Write prose fields only: profile/text, skills-focus/skillsText, early-career/text and job context/tasks/results/stack. Keep structured skeleton fields unchanged. Supply an EditorialPlan accounting for all active jobs. Do not omit supported prose or use blocked conflict claims for authored text."}
    return content_input("draft_prose", payload, rules, transform=transform, return_canonical=return_canonical)


def validate_draft(request: GuiDraftRequest, proposal: GuiDraftProposal, rules: Rules,
                   available_logos: set[str] | None = None) -> GuiDraftResult:
    normalized = request.normalized
    plan = proposal.editorial_plan.model_copy(deep=True)
    jobs = {job.id for job in normalized.employment}
    facts = {fact.id: fact for fact in normalized.facts}
    blocked = {id for conflict in normalized.conflicts for id in conflict.fact_ids}
    warnings = DraftWarnings(request, rules)
    if (plan.origin != "model" or plan.rules_revision != rules.revision or plan.formatting_as_of != request.formatting_as_of or
        {job.job_id for job in plan.jobs} != jobs):
        warnings.add("INVALID_EDITORIAL_PLAN_CONTEXT")
    plan.origin, plan.rules_revision, plan.formatting_as_of = "model", rules.revision, request.formatting_as_of
    plan.profile_language = plan.profile_language or "ru"
    plan.jobs = [job for job in plan.jobs if job.job_id in jobs]
    represented = {job.job_id for job in plan.jobs}
    plan.jobs.extend(JobDisposition(jobId=job.id, disposition="detailed", factIds=[])
                     for job in normalized.employment if job.id not in represented)
    all_plan_items = [plan, *plan.jobs, *plan.focus, *plan.technology_groups]
    for item in all_plan_items:
        if not set(item.fact_ids) <= set(facts):
            warnings.add("INVALID_EDITORIAL_FACT_REFERENCE")
        item.fact_ids = list(dict.fromkeys(id for id in item.fact_ids if id in facts))
    for job in plan.jobs:
        if any(facts[id].job_id not in (None, job.job_id) for id in job.fact_ids):
            warnings.add("EDITORIAL_FACT_OUTSIDE_JOB")
    document = draft_skeleton(normalized)
    fields = {field.field_id: field for record in document.records() for field in authored_fields(record)}
    prose_ids = {"profile/text", "skills-focus/skillsText", "early-career/text"}
    prose_ids.update(f"job:{id}/{key}" for id in jobs for key in ("context", "tasks", "results", "stack"))
    seen, unplaced, texts = set(), [], {}
    for item in proposal.fields:
        if item.field_id not in fields:
            warnings.add("INVALID_DRAFT_FIELD_REFERENCE")
            if item.text.strip():
                unplaced.append(item.text)
            continue
        field = fields[item.field_id]
        if item.field_id not in prose_ids:
            warnings.add("DRAFT_STRUCTURED_FIELD", item.field_id)
            continue
        if item.field_id in seen:
            warnings.add("DUPLICATE_DRAFT_FIELD", item.field_id)
        seen.add(item.field_id)
        refs = list(dict.fromkeys(id for id in item.fact_ids if id in facts))
        if len(refs) != len(item.fact_ids) or set(refs) & blocked:
            warnings.add("INVALID_DRAFT_FIELD_REFERENCE", item.field_id)
        if item.text.strip() and not refs:
            warnings.add("DRAFT_TEXT_NEEDS_FACTS", item.field_id)
        if item.field_id.startswith("job:"):
            job_id = item.field_id.split("/", 1)[0].removeprefix("job:")
            if any(facts[id].job_id != job_id for id in refs):
                warnings.add("DRAFT_FACT_OUTSIDE_JOB", item.field_id)
        paragraphs = texts.setdefault(item.field_id, [])
        if item.text not in paragraphs:
            paragraphs.append(item.text)
        field.text = "\n".join(paragraphs)
        field.fact_ids = list(dict.fromkeys([*field.fact_ids, *refs]))
        field.evidence = [ref for id in field.fact_ids for ref in facts[id].evidence]
        field.origin = "generated"
    if unplaced:
        document.profile.text.text = "\n\n".join([document.profile.text.text, *unplaced]).strip()
        warnings.add("DRAFT_TEXT_NEEDS_FACTS", "profile/text")
    required = {"profile/text", "skills-focus/skillsText", "early-career/text"}
    detailed = [item.job_id for item in plan.jobs if item.disposition == "detailed"]
    early = [item.job_id for item in plan.jobs if item.disposition == "early-career"]
    required.update(f"job:{id}/{key}" for id in detailed for key in ("context", "tasks", "results", "stack"))
    for missing in required - seen:
        warnings.add("INCOMPLETE_DRAFT_FIELDS", missing)
    supported = public_context_facts(normalized.facts)
    prose_kinds = {"text", "technology", "metric", "leadership"}
    if any(fact.kind in prose_kinds for fact in supported) and not document.profile.text.text.strip():
        warnings.add("EMPTY_SUPPORTED_DRAFT_PROSE", "profile/text")
        fill_literal(document.profile.text, [fact for fact in supported if fact.kind in prose_kinds])
    if any(fact.kind == "technology" and fact.value.scope == "global" for fact in supported) and not document.skills_focus.skills_text.text.strip():
        warnings.add("EMPTY_SUPPORTED_DRAFT_PROSE", "skills-focus/skillsText")
        fill_literal(document.skills_focus.skills_text,
                     [fact for fact in supported if fact.kind == "technology" and fact.value.scope == "global"])
    for job in document.jobs:
        if job.id not in detailed:
            continue
        owned = [fact for fact in supported if fact.job_id == job.id]
        if (any(fact.kind in {"text", "metric", "leadership"} for fact in owned)
            and not any(field.text.strip() for field in (job.context, job.tasks, job.results))):
            warnings.add("EMPTY_SUPPORTED_DRAFT_PROSE", job.context.field_id)
            fill_literal(job.context, [fact for fact in owned if fact.kind != "technology"])
        if any(fact.kind == "technology" for fact in owned) and not job.stack.text.strip():
            warnings.add("EMPTY_SUPPORTED_DRAFT_PROSE", job.stack.field_id)
            fill_literal(job.stack, [fact for fact in owned if fact.kind == "technology"])
    if early and not document.early_career.text.text.strip():
        warnings.add("EARLY_CAREER_NOT_REPRESENTED", "early-career/text")
        # Keep missing early-career prose as editable job blocks rather than hiding the source jobs.
        for job in plan.jobs:
            if job.disposition == "early-career":
                job.disposition = "detailed"
                detailed.append(job.job_id)
                record = next(record for record in document.jobs if record.id == job.job_id)
                fill_literal(record.context, [fact for fact in supported if fact.job_id == job.job_id])
        early = []
    document.jobs = [next(job for job in document.jobs if job.id == id) for id in detailed]
    document.early_career.represented_job_ids = early
    visible_fields = {field.field_id for record in document.records() for field in authored_fields(record)}
    for mark in warnings.marks.values():
        if mark.anchor.kind == "field" and mark.anchor.field_id not in visible_fields:
            mark.anchor = DocumentAnchor(kind="document")
    if not any(field.text.strip() for record in document.records() for field in authored_fields(record)) or (
            normalized._native_recovery_count and not document.profile.text.text.strip()):
        document.profile.text.text = "\n".join(unit.text for source in normalized.sources for unit in source.units if unit.text.strip())
        document.profile.text.origin = "source"
        warnings.add("IMPORT_CONTENT_RECOVERED", "profile/text")
    logos = available_focus_ids() if available_logos is None else available_logos
    focus = []
    removed = []
    seen = set()
    accepted = []
    for item in plan.focus:
        reason = "duplicate" if item.catalog_id in seen else "unknown-ID" if item.catalog_id not in BY_ID else "missing-logo" if item.catalog_id not in logos else "capacity" if len(accepted) >= 8 else None
        seen.add(item.catalog_id)
        if reason:
            removed.append({"catalogId": item.catalog_id, "reason": reason})
            continue
        if not item.fact_ids or any(facts[id].kind != "technology" or facts[id].value.canonical_id != item.catalog_id for id in item.fact_ids):
            warnings.add("FOCUS_FACT_MISMATCH", "skills-focus/skillsText")
        accepted.append(item)
        id = _id("focus", item.catalog_id)
        focus.append({"id": id, "catalogId": item.catalog_id,
                      "display": {**_field(f"skills-focus/focus:{id}/display", item.display, item.fact_ids), "origin": "generated"},
                      "factIds": item.fact_ids})
    plan.focus = accepted
    document.skills_focus.focus = [FocusEntry.model_validate(item) for item in focus]
    annotations = list(warnings.marks.values())
    if removed:
        fingerprint = hashlib.sha256(drafting_input(request, rules).encode()).hexdigest()
        annotations.append(Annotation.model_validate({"id": _id("annotation", "focus-removals", request.project_id),
            "type": "warning", "code": "focus_entry_removed", "anchor": {"kind": "section", "sectionId": "skills-focus"},
            "dependencies": {"projectRevision": request.project_revision, "documentRevision": request.document_revision,
                "rulesSha256": rules.sha256, "sourceFingerprint": normalized.source_fingerprint, "dependencyFingerprint": fingerprint},
            "factIds": [], "reason": "Ineligible focus entries were removed.", "evidence": [], "resolved": False,
            "updateSuggestionId": None, "removedFocus": removed}))
    return GuiDraftResult.model_validate({"document": document.model_dump(by_alias=True), "editorialPlan": plan.model_dump(by_alias=True),
                                          "annotations": [annotation.model_dump(by_alias=True) for annotation in annotations]})


GUI_DRAFT_CONTRACTS = {"gui_draft_request": GuiDraftRequest, "gui_draft_proposal": GuiDraftProposal, "gui_draft_result": GuiDraftResult}


def replace_focus_warnings(previous: list[Annotation], current: list[Annotation]) -> list[Annotation]:
    return [annotation for annotation in previous if annotation.code != "focus_entry_removed"] + current
