"""Project the current authored document into the unchanged DOCX writer."""

from __future__ import annotations

from .gui_derived import digest, endpoint
from .models.recovery import WorkspaceV5, FieldAnchor, SectionAnchor
from .rendering.docx_errors import validate_document


def render_input(workspace: WorkspaceV5):
    if workspace.project is None or workspace.editorial_plan is None:
        raise ValueError("DOCUMENT_UNAVAILABLE")
    document = workspace.project.document
    russian = workspace.editorial_plan.source_language == "ru"
    labels = (["Имя не указано", "Должность не указана", "Компания не указана", "не указана", "Даты не указаны"]
              if russian else ["Name not specified", "Title not specified", "Company not specified", "not specified", "Dates not specified"])
    anchors = {}

    def field(path, value):
        anchors[path] = FieldAnchor(kind="field", fieldId=value.field_id, range=None)
        return value.text.replace("\r\n", "\n").replace("\r", "\n")

    def required(path, value, fallback):
        text = field(path, value)
        return text if text.strip() else fallback

    def section(path, id):
        anchors[path] = SectionAnchor(kind="section", sectionId=id)

    def date_text(value):
        parsed = endpoint(value, workspace.project.facts)
        if parsed:
            return str(parsed.year).zfill(4) + (f"-{parsed.month:02d}" if parsed.month else "") + (f"-{parsed.day:02d}" if parsed.day else "")
        return value.text if value.text.strip() else "?"

    projects = []
    section("projects", "employment")
    for job in document.jobs:
        if not job.visible:
            continue
        prefix = f"projects[{len(projects)}]"
        periods = []
        for period in job.periods:
            if not period.start_text.text.strip() and not period.end_text.text.strip() and not period.present:
                periods.append(labels[4])
            else:
                periods.append(date_text(period.start_text) + "–" + (("н. в." if russian else "present") if period.present else date_text(period.end_text)))
        anchors[prefix + ".period"] = FieldAnchor(kind="field", fieldId=job.periods_field_id, range=None)
        item = {"company": required(prefix + ".company", job.employer, labels[2]),
                "role": required(prefix + ".role", job.role, labels[3]), "period": ", ".join(periods) or labels[4],
                "stack": field(prefix + ".stack", job.stack), "description": field(prefix + ".description", job.context)}
        for key in ("tasks", "results"):
            value = getattr(job, key)
            lines = [line for line in field(prefix + "." + key, value).split("\n") if line.strip()]
            item[key] = lines
            for index in range(len(lines)):
                anchors[f"{prefix}.{key}[{index}]"] = anchors[prefix + "." + key]
        projects.append(item)
    sidebar = []
    section("sidebar", "document-sidebar")

    def add(title, rows, id):
        rows = [(text, anchor) for text, anchor in rows if text.strip()]
        if not rows:
            return
        prefix = f"sidebar[{len(sidebar)}]"
        section(prefix + ".title", id)
        section(prefix + ".items", id)
        for i, (_, anchor) in enumerate(rows):
            anchors[f"{prefix}.items[{i}]"] = anchor
        sidebar.append({"title": title, "items": [text.replace("\r\n", "\n").replace("\r", "\n") for text, _ in rows]})

    add("МЕСТОПОЛОЖЕНИЕ" if russian else "LOCATION", [(document.candidate.location.text,
        FieldAnchor(kind="field", fieldId=document.candidate.location.field_id, range=None))], "candidate")
    for collection, ru, en, keys in [("education", "ОБРАЗОВАНИЕ", "EDUCATION", ("institution", "qualification", "specialty", "date_text")),
            ("certifications", "СЕРТИФИКАТЫ", "CERTIFICATIONS", ("name", "issuer", "date_text")),
            ("languages", "ЯЗЫКИ", "LANGUAGES", ("name", "proficiency"))]:
        rows = []
        for row in getattr(document, collection):
            if not row.visible:
                continue
            if row.legacy_text is not None:
                text = row.legacy_text.text
                anchor = FieldAnchor(kind="field", fieldId=row.legacy_text.field_id, range=None)
            else:
                text = (" — " if collection == "languages" else "\n").join(getattr(row, key).text for key in keys if getattr(row, key).text.strip())
                anchor = SectionAnchor(kind="section", sectionId=f"{row.kind}:{row.id}")
            rows.append((text, anchor))
        add(ru if russian else en, rows, collection)
    early = document.early_career
    if early.visible:
        add("РАННИЙ ОПЫТ" if russian else "EARLY CAREER", [(early.text.text, FieldAnchor(kind="field", fieldId=early.text.field_id, range=None))], "early-career")
    focus = []
    section("focus", "skills-focus")
    derived = {value.field_id: value for value in workspace.derived_state.values} if workspace.derived_state else {}
    from .gui_drafting import available_focus_ids
    available = available_focus_ids()
    seen = set()
    if document.skills_focus.visible:
        for entry in document.skills_focus.focus:
            if entry.catalog_id in seen or entry.catalog_id not in available or len(focus) >= 8:
                continue
            seen.add(entry.catalog_id)
            index = len(focus)
            value = derived.get(entry.display.field_id)
            section(f"focus[{index}].icon", "skills-focus")
            section(f"focus[{index}].duration", "skills-focus")
            focus.append({"label": field(f"focus[{index}].label", entry.display), "icon": entry.catalog_id,
                          "duration": value.display or "" if value and value.complete_exposure else ""})
    skills = []
    section("skillGroups", "skills-focus")
    if document.skills_focus.visible and document.skills_focus.skills_text.text.strip():
        section("skillGroups[0].title", "skills-focus")
        skills.append({"title": "НАВЫКИ" if russian else "SKILLS", "items": field("skillGroups[0].items", document.skills_focus.skills_text)})
    data = {"sourceLanguage": workspace.editorial_plan.source_language,
        "candidate": {"name": required("candidate.name", document.candidate.name, labels[0]),
            "title": required("candidate.title", document.candidate.title, labels[1]),
            "summary": field("candidate.summary", document.profile.text) if document.profile.visible else ""},
        "projects": projects, "sidebar": sidebar, "focus": focus, "skillGroups": skills, "achievements": [], "footer": ""}
    return validate_document(data, anchors), anchors, digest(data)
