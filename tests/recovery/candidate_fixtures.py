"""Controlled candidate responses; expected facts remain in the independent manifest."""

from pathlib import Path

from packages.resume_core.extraction.parser import extract
from packages.resume_core.gui_normalization import GuiNormalizeRequest, GuiSemanticProposal, canonical_source

ROOT = Path(__file__).resolve().parents[1] / "fixtures/recovery"
AS_OF = {"precision": "day", "year": 2026, "month": 10, "day": 11}


def request(text: str, name: str = "synthetic.txt") -> GuiNormalizeRequest:
    parsed = extract(text.encode(), name, pasted=True)
    source = canonical_source(parsed)
    return GuiNormalizeRequest.model_validate({"sources": [source.model_dump(by_alias=True)], "formattingAsOf": AS_OF, "revision": 1})


def span(source, text):
    unit = next(unit for unit in source.units if text in unit.text)
    return {"sourceId": source.id, "sourceRevision": source.revision,
            "unitId": unit.id, "unitRevision": unit.revision, "text": text}


def value(source, text):
    return {"text": text, "evidence": [span(source, text)] if text else []}


def proposal(source_request, example="E1"):
    source = source_request.sources[0]
    name = "Ирина Примерова" if example == "E1" else "Алексей"
    title = "backend-разработчик" if example == "E1" else "Data engineer"
    candidate = {key: value(source, text) for key, text in {"name": name, "title": title, "location": ""}.items()}
    education = []
    languages = []
    if example == "E1":
        education = [{"id": "school", "institution": value(source, "Учебный технический университет"),
                      "qualification": value(source, ""), "specialty": value(source, "прикладная информатика"),
                      "dateText": value(source, "2016")}]
        languages = [{"id": id, "name": value(source, name), "proficiency": value(source, level)}
                     for id, name, level in [("ru", "русский", "родной"), ("en", "английский", "B2")]]
    jobs = []
    for id, employer, role, start, end in ([
        ("north", "Север", "backend-разработчик", 2021, None),
        ("west", "Запад", "разработчик", 2017, 2020), ("east", "Восток", "разработчик", 2008, 2009),
    ] if example == "E1" else [("gamma", "Гамма", "data engineer", None, None), ("delta", "Дельта", "аналитик", 2020, 2022)]):
        year = lambda number: {"precision": "year", "year": number, "month": None, "day": None}
        jobs.append({"tempId": id, "employer": employer, "role": role,
                     "periods": [{"start": year(start), "end": year(end) if end else None}] if start else [],
                     "sourceId": source.id, "unitIds": [span(source, employer)["unitId"]], "subprojects": []})
    return GuiSemanticProposal.model_validate({"schemaVersion": 1, "jobs": jobs, "facts": [],
        "units": [{"sourceId": source.id, "unitId": unit.id, "disposition": "unresolved", "factTempIds": [], "duplicateOf": None}
                  for unit in source.units], "candidate": candidate, "education": education, "certifications": [],
        "languages": languages, "privateDetails": [], "nameAssessment": {"missingSurname": False if example == "E1" else None,
        "evidence": [span(source, name)] if example == "E1" else [], "revision": 1},
        "observationAssessment": {"sourceObservedAt": None, "evidence": None, "revision": 1}})
