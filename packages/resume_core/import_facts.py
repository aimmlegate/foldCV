"""Map small import records to the existing editable facts without semantic rejection."""

import re

from .rich_assembly import date_field, field
from .technologies import resolve_technology


def import_date_field(text):
    result = date_field(text)
    if result["value"] is not None:
        return result
    names = ["январь января january jan", "февраль февраля february feb", "март марта march mar",
        "апрель апреля april apr", "май мая may", "июнь июня june jun", "июль июля july jul",
        "август августа august aug", "сентябрь сентября september sep sept", "октябрь октября october oct",
        "ноябрь ноября november nov", "декабрь декабря december dec"]
    months = {name: index for index, group in enumerate(names, 1) for name in group.split()}
    match = re.fullmatch(r"(?:([0-9]{1,2})\s+)?([а-яёa-z]+)\.?\s+([0-9]{4})(?:\s*г\.?)?", text.strip().casefold())
    numeric = re.fullmatch(r"([0-9]{1,2})\.([0-9]{4})", text.strip())
    if match and match[2] in months:
        normalized = f"{match[3]}-{months[match[2]]:02}" + (f"-{int(match[1]):02}" if match[1] else "")
    elif numeric:
        normalized = f"{numeric[2]}-{int(numeric[1]):02}"
    else:
        return result
    decoded = date_field(normalized)
    if decoded["value"] is not None:
        decoded["rawText"] = text
        return decoded
    return result


def assemble_import_facts(draft, identity, evidence):
    records, evidence_records, links = [], [], []

    def add(kind, identifier, keys, **values):
        spans = evidence(keys)
        record = {"id": identifier, "kind": kind, "revision": 1, "origin": "source",
            "evidence": spans, **values}
        records.append(record)
        evidence_records.append({"id": identifier, "evidence": spans,
            "rawText": "".join(span["text"] for span in spans)})
        links.append((record, set(keys)))

    def technology(identifier, display, keys, job_id=None, technical=None, experience=""):
        canonical = resolve_technology(display).canonical_id
        extra = {"technical": technical} if technical is not None else {}
        if experience:
            extra["experience"] = field(experience)
        add("technology", identifier, keys, jobId=job_id, subprojectId=None,
            display=field(display), canonicalId=field(canonical, canonical or display), **extra)

    profile = draft.profile
    if any((profile.name, profile.title, profile.location)):
        add("candidate", "candidate", profile.source_keys, name=field(profile.name),
            title=field(profile.title), location=field(profile.location))
    for fact in draft.facts:
        data, keys = fact.record, fact.source_keys
        if data is None:
            add("claim", identity("digest", fact.id), keys, jobId=None, subprojectId=None, value=field(fact.text))
            continue
        identifier = identity(data.kind, fact.id)
        if data.kind == "employment":
            periods = [{"id": identity("period", [fact.id, index]), "revision": 1,
                "start": import_date_field(period.start),
                "end": import_date_field(period.end),
                "present": field(period.present, period.end if period.present else ""),
                "evidence": evidence(keys)} for index, period in enumerate(data.periods)]
            add(data.kind, identifier, keys, employer=field(data.employer), role=field(data.role), periods=periods)
            for index, display in enumerate(data.technologies):
                if isinstance(display, str):
                    technology(identity("technology", [fact.id, index]), display, keys, identifier)
                else:
                    technology(identity("technology", [fact.id, index]), display.display, keys, identifier,
                        technical=display.technical, experience=display.experience)
        elif data.kind == "technology":
            technology(identifier, data.display, keys, technical=data.technical, experience=data.experience)
        elif data.kind == "education":
            add(data.kind, identifier, keys, institution=field(data.institution),
                qualification=field(data.qualification), specialty=field(data.specialty),
                completion=import_date_field(data.completion))
        elif data.kind == "language":
            add(data.kind, identifier, keys, language=field(data.language), level=field(data.level))
    return records, evidence_records, links


def record_fields(record):
    for key, value in record.items():
        if key != "canonicalId" and isinstance(value, dict) and "rawText" in value:
            yield key, value["rawText"]
    for period in record.get("periods", []):
        for key in (("start", "present") if period["present"]["value"] is True else ("start", "end", "present")):
            yield f"period:{period['id']}:{key}", period[key]["rawText"]
