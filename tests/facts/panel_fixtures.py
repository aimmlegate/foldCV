"""Facts-panel request builders and a small technology facts fixture with the sidebar Focus it implies."""

import hashlib

from packages.resume_core.models.rich_document import RichDocumentV1
from packages.resume_core.models.rich_facts import WorkingFacts
from packages.resume_core.rendering.rich_template import require_rich_template
from packages.resume_core.rich_assembly import date_field, field
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_panel import RichPanelRequest, panel_mutation
from packages.resume_core.technologies import resolve_technology
from packages.resume_core.technology_focus import focus_candidates
from tests.support.rich import capture, without_sources


def edit(workspace, **values):
    return RichPanelRequest.model_validate({'operation': 'edit', 'recordId': 'candidate-1',
        'factsRevision': workspace.project.facts.revision, 'documentRevision': workspace.project.document.revision,
        'capture': capture(), **values})


def apply(workspace, **values):
    return apply_rich_mutation(workspace, panel_mutation(workspace, edit(workspace, **values)))[0]


def identify(kind, key):
    return kind + '-' + hashlib.sha256(str(key).encode()).hexdigest()[:12]


def job(start, end, technology="Python", **period):
    return {"kind": "employment", "employer": start + end, "technologies": [technology],
        "periods": [{"start": start, "end": end, **period}]}


def technology_record(identifier, display, job_id=None, technical=None, experience=""):
    canonical = resolve_technology(display).canonical_id
    extra = {"technical": technical} if technical is not None else {}
    if experience:
        extra["experience"] = field(experience)
    return {"id": identifier, "kind": "technology", "revision": 1, "origin": "source", "evidence": [], "jobId": job_id,
        "subprojectId": None, "display": field(display), "canonicalId": field(canonical, canonical or display), **extra}


def records(rows):
    """Working records for rows of employments (with linked technologies and periods) and technologies, in row order."""
    result = []
    for index, row in enumerate(rows):
        fact = f"content_fact_{index}"
        if row["kind"] == "technology":
            result.append(technology_record(identify("technology", fact), row["display"], technical=row.get("technical"),
                experience=row.get("experience", "")))
            continue
        employment = identify("employment", fact)
        periods = [{"id": identify("period", [fact, number]), "revision": 1, "start": date_field(period.get("start", "")),
            "end": date_field(period.get("end", "")),
            "present": field(period.get("present", False), period.get("end", "") if period.get("present") else ""),
            "evidence": []} for number, period in enumerate(row.get("periods", []))]
        result.append({"id": employment, "kind": "employment", "revision": 1, "origin": "source", "evidence": [],
            "employer": field(row.get("employer", "")), "role": field(row.get("role", "")), "periods": periods})
        for number, value in enumerate(row.get("technologies", [])):
            value = {"display": value} if isinstance(value, str) else value
            result.append(technology_record(identify("technology", [fact, number]), value["display"], employment,
                technical=value.get("technical"), experience=value.get("experience", "")))
    return result


def focus_section(raw):
    spec = require_rich_template().specification["focus"]
    selected = focus_candidates(raw, spec["referenceLogoEntries"] + spec["referenceTextOnlyEntries"])
    if not selected:
        return []
    children = []
    for record in selected:
        binding = identify("focus_binding", record["id"])
        children.append({"id": identify("focus_entry", record["id"]), "revision": 1, "type": "paragraph", "props": {},
            "children": [], "content": [{"type": "fact_field", "bindingId": binding, "recordId": record["id"],
                "fieldKey": "display", "text": record["display"]["rawText"], "styles": {}, "syncedFactRevision": 1}],
            "provenance": [{"kind": "field_binding", "id": binding, "recordId": record["id"], "fieldKey": "display"},
                {"kind": "citation", "id": identify("focus_source", record["id"]), "recordId": record["id"],
                    "fieldKeys": ["display"], "evidence": record["evidence"]}]})
    return [{"id": identify("focus", "summary"), "revision": 1, "type": "section",
        "props": {"recordId": None, "presentation": "focus"}, "content": [{"type": "text", "text": "FOCUS", "styles": {}}],
        "provenance": [], "children": children}]


def technology_facts(rows):
    """Facts for rows and a document whose sidebar holds the Focus section that the technical, known-logo tools fill."""
    raw = records(rows)
    facts = WorkingFacts(revision=1, records=raw, tombstones=[])
    regions = {"header": [], "sidebar": focus_section(raw), "main": []}
    document = RichDocumentV1(schemaVersion=1, revision=1, regions=[
        {"id": region, "role": region, "revision": 1, "blocks": regions[region]} for region in ["header", "sidebar", "main"]])
    return facts, document


def technology_workspace(rows):
    """The rich workspace fixture carrying `technology_facts(rows)` instead of its own facts and document."""
    facts, document = technology_facts(rows)
    workspace = without_sources()
    workspace.project.document, workspace.project.facts = document, facts
    workspace.project.evidence_records = []
    return workspace
