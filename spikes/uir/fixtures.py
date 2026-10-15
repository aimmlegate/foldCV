"""Synthetic canonical inputs for the bounded prototype presentation proof."""

from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess

from packages.resume_core.dates import partial_date
from packages.resume_core.extraction.parser import extract
from packages.resume_core.gui_normalization import canonical_source, GuiSemanticProposal
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.rendering.rich_template import require_rich_template
from packages.resume_core.rich_presentation import authored_text

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "docs/gui/handoffs/PROTOTYPE-ADOPTION"
FIXTURES = HANDOFF / "fixtures"
NOW = "2026-10-15T18:00:00+00:00"
ALIASES = {"employment": {"title": "role"}, "technology": {"name": "display"},
    "education": {"school": "institution", "program": "specialty", "year": "completion"},
    "language": {"name": "language"}}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sample():
    raw = subprocess.check_output(["/Users/fostral/.nvm/versions/node/v22.14.0/bin/node",
        "spikes/uir/reference-input.mjs"], cwd=ROOT)
    return json.loads(raw)


def field(value=None, raw=None):
    return {"value": value, "rawText": str(value) if raw is None and value is not None else raw or "",
        "status": "known" if value is not None else "unknown", "revision": 1, "pendingRawText": None}


def canonical_facts(demo):
    result = []
    for item in demo["facts"]:
        record = {"id": item["id"], "kind": item["kind"], "revision": 1, "origin": "user", "evidence": []}
        kind = item["kind"]
        if kind == "candidate":
            record.update({key: field(item[key]) for key in ("name", "title", "location")})
            result.append({"id": "candidate-email", "kind": "detail", "revision": 1, "origin": "user",
                "evidence": [], "detailType": "email", "label": "Email", "value": field(item["email"])})
        elif kind == "employment":
            record.update(employer=field(item["employer"]), role=field(item["title"]))
            present = item["end"] == "настоящее время"
            record["periods"] = [{"id": "period-" + item["id"], "revision": 1, "evidence": [],
                "start": field(partial_date(item["start"]).model_dump(), item["start"]),
                "end": field(None if present else partial_date(item["end"]).model_dump(), "" if present else item["end"]),
                "present": field(present, item["end"] if present else "")}]
        elif kind == "technology":
            record.update(display=field(item["name"]), canonicalId=field(), jobId=item["jobId"], subprojectId=None)
        elif kind == "education":
            record.update(institution=field(item["school"]), specialty=field(item["program"]), qualification=field(),
                completion=field(partial_date(item["year"]).model_dump(), item["year"]))
        elif kind == "language":
            record.update(language=field(item["name"]), level=field(item["level"]))
        result.append(record)
    return {"revision": 1, "records": result, "tombstones": []}


class InlineParser(HTMLParser):
    def __init__(self, demo, identifier):
        super().__init__()
        self.demo, self.identifier, self.content = demo, identifier, []
        self.binding, self.styles, self.index = None, {}, 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "br":
            self.handle_data("\n")
        if tag in {"strong", "b", "em", "i", "u"}:
            self.styles[{"strong": "bold", "b": "bold", "em": "italic", "i": "italic", "u": "underline"}[tag]] = True
        if tag == "span" and "data-record" in values:
            record = next(item for item in self.demo["facts"] if item["id"] == values["data-record"])
            key = values["data-field"]
            identifier = record["id"]
            if key == "email":
                identifier, key = "candidate-email", "value"
            elif record["kind"] == "employment" and key in {"start", "end"}:
                part = "present" if key == "end" and record["end"] == "настоящее время" else key
                key = f"period:period-{identifier}:{part}"
            else:
                key = ALIASES.get(record["kind"], {}).get(key, key)
            self.binding = identifier, key

    def handle_endtag(self, tag):
        if tag == "span": self.binding = None
        if tag in {"strong", "b", "em", "i", "u"}: self.styles = {}

    def handle_data(self, data):
        if not data: return
        if self.binding:
            self.index += 1
            self.content.append({"type": "fact_field", "recordId": self.binding[0], "fieldKey": self.binding[1],
                "bindingId": f"binding-{self.identifier}-{self.index}", "syncedFactRevision": 1,
                "text": data, "styles": dict(self.styles)})
        else:
            self.content.append({"type": "text", "text": data, "styles": dict(self.styles)})


def structured(demo):
    regions = {role: [] for role in ("header", "sidebar", "main")}
    mapping, section, job = [], None, None
    predicates = {"name": "header heading level 1 bound to candidate.name", "title": "header heading level 2 bound to candidate.title",
        "section": "nonempty canonical section; focus presentation only for technology section",
        "job": "main heading level 2 bound to employment.employer", "caption": "paragraph with employment period bindings",
        "focus": "paragraph in focus section bound to global technology.display", "tech": "paragraph with job technology.display bindings",
        "paragraph": "ordinary paragraph preserving inline bindings, marks and line breaks"}
    classes = {"name": "candidate-name", "title": "candidate-title", "section": "cv-section", "job": "cv-job",
        "caption": "cv-caption", "focus": "cv-focus", "tech": "cv-tech", "paragraph": "cv-block block-content"}
    for item in demo["blocks"]:
        parser = InlineParser(demo, item["id"]); parser.feed(item["html"])
        kind = item["kind"]
        block = {"id": item["id"], "revision": 1, "type": "paragraph", "props": {},
            "content": parser.content, "children": [], "provenance": []}
        if kind in {"name", "title", "job"}:
            block.update(type="heading", props={"level": 1 if kind == "name" else 2})
        if kind == "section":
            block.update(type="section", props={"recordId": None, "presentation": "focus" if item["id"] == "focus-heading" else "standard"})
            regions[item["region"]].append(block); section, job = block, None
        elif item["region"] == "header": regions["header"].append(block)
        elif kind == "job":
            job = {"id": "owner-" + item["recordId"], "revision": 1, "type": "section",
                "props": {"recordId": item["recordId"], "presentation": "standard"}, "content": [], "children": [], "provenance": []}
            section["children"].append(job); job["children"].append(block)
        else: (job or section)["children"].append(block)
        mapping.append({"sampleBlockId": item["id"], "prototypeKind": kind, "canonicalId": block["id"],
            "canonicalType": block["type"], "props": block["props"], "region": item["region"],
            "bindings": [{key: span[key] for key in ("bindingId", "recordId", "fieldKey")} for span in parser.content if span["type"] == "fact_field"],
            "viewClass": classes[kind], "predicateAfterReopen": predicates[kind],
            "visibleText": "".join(span["text"] for span in parser.content)})
    source = canonical_source(extract(demo["original"].encode(), "structured-source.txt", pasted=True), source_id="uir-structured-source")
    document = {"schemaVersion": 1, "revision": 1, "regions": [{"id": role, "role": role, "revision": 1, "blocks": blocks} for role, blocks in regions.items()]}
    project = {"schemaVersion": 5, "projectId": "uir-structured", "revision": 1, "createdAt": NOW,
        "sources": [source.model_dump(by_alias=True)], "evidenceRecords": [], "facts": canonical_facts(demo),
        "document": document, "assets": [], "operations": [], "renders": [],
        "template": require_rich_template().manifest.model_dump(by_alias=True)}
    workspace = WorkspaceV6.model_validate({"schemaVersion": 6, "projectId": project["projectId"], "projectRevision": 1,
        "documentRevision": 1, "title": "Алексей Соколов", "titleManuallySet": False, "createdAt": NOW, "updatedAt": NOW,
        "project": project, "preDraft": None, "formattingAsOf": partial_date("2026-10-15").model_dump(),
        "sourceObservedAt": None, "rulesUsed": None, "syncRecords": [], "mutationReplay": [], "warnings": []})
    return workspace, {(workspace.project_id, source.id): demo["original"].encode()}, mapping


def extraction_reply(payload):
    source = payload["input"]["sources"][0]
    def evidence(text):
        unit = next(unit for unit in source["units"] if text in unit["text"])
        return {"sourceId": source["id"], "sourceRevision": source["revision"], "unitId": unit["id"], "unitRevision": unit["revision"], "text": text}
    def text(value): return {"text": value, "evidence": [evidence(value)] if value else []}
    jobs = []
    for identifier, employer, role, start, end in [("north", "Север", "Фронтенд-разработчик", "2022-01", None),
        ("line", "Студия Линия", "Веб-разработчик", "2019-06", "2022-03")]:
        jobs.append({"tempId": identifier, "employer": employer, "role": role, "sourceId": source["id"],
            "unitIds": [evidence(employer)["unitId"]], "subprojects": [], "periods": [{"start": partial_date(start).model_dump(),
                "end": partial_date(end).model_dump() if end else None, "present": end is None,
                "startText": start, "endText": end or "настоящее время", "evidence": [evidence(start)]}]})
    facts = []
    for identifier, display, owner in [("react", "React", None), ("typescript", "TypeScript", "north"), ("git", "Git", None)]:
        span = evidence(display)
        facts.append({"tempId": identifier, "kind": "technology", "value": {"canonicalId": identifier,
            "display": display, "scope": "job" if owner else "global"}, "sourceId": source["id"], "unitIds": [span["unitId"]],
            "jobTempId": owner, "subprojectTempId": None, "importance": "normal", "literalEvidence": [span]})
    return GuiSemanticProposal.model_validate({"schemaVersion": 1, "jobs": jobs, "facts": facts,
        "units": [{"sourceId": source["id"], "unitId": unit["id"], "disposition": "facts" if any(unit["id"] in fact["unitIds"] for fact in facts) else "unresolved",
            "factTempIds": [fact["tempId"] for fact in facts if unit["id"] in fact["unitIds"]], "duplicateOf": None} for unit in source["units"]],
        "candidate": {"name": text("Алексей Соколов"), "title": text("Фронтенд-разработчик"), "location": text("Санкт-Петербург")},
        "education": [{"id": "school", "institution": text("СПбПУ"), "qualification": text(""),
            "specialty": text("Информатика и вычислительная техника"), "dateText": text("2019")}],
        "certifications": [], "languages": [{"id": "ru", "name": text("Русский"), "proficiency": text("родной")},
            {"id": "en", "name": text("Английский"), "proficiency": text("B2")}],
        "privateDetails": [{"kind": "email", "value": text("alexey@example.com")}],
        "nameAssessment": {"missingSurname": False, "evidence": [evidence("Алексей Соколов")], "revision": 1},
        "observationAssessment": {"sourceObservedAt": None, "evidence": None, "revision": 1}})


def demo_from_workspace(workspace):
    blocks = [{"id": block.id, "region": region.role, "kind": "paragraph", "html": escape(authored_text(block)).replace("\n", "<br>"),
        "recordId": None, "indent": 0} for region in workspace.project.document.regions for block in region.blocks]
    records = []
    for record in workspace.project.facts.records:
        value = {"id": record.id, "kind": record.kind}
        if record.kind == "candidate": value.update(name=record.name.raw_text, title=record.title.raw_text, location=record.location.raw_text, email="")
        elif record.kind == "employment":
            period = record.periods[0] if record.periods else None
            value.update(employer=record.employer.raw_text, title=record.role.raw_text,
                start=period.start.raw_text if period else "", end=(period.present.raw_text or period.end.raw_text) if period else "")
        elif record.kind == "technology": value.update(name=record.display.raw_text, jobId=record.job_id)
        elif record.kind == "education": value.update(school=record.institution.raw_text, program=record.specialty.raw_text, year=record.completion.raw_text)
        elif record.kind == "language": value.update(name=record.language.raw_text, level=record.level.raw_text)
        else: continue
        records.append(value)
    return {"id": "uir-fresh-import", "facts": records, "blocks": blocks,
        "original": (FIXTURES / "import-source.txt").read_text(), "sourceName": "import-source.txt",
        "revision": 1, "dirty": False, "overlapDisposition": "open"}
