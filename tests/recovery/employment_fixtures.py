"""Frozen employment claims returned by the controlled normalization provider."""

from packages.resume_core.gui_normalization import GuiSemanticProposal
from tests.recovery.candidate_fixtures import proposal, span


def metric(number, unit, *, attribution="unknown", baseline=None, result=None, qualifiers=None):
    return {"number": number, "upperNumber": None, "comparator": "exact", "unit": unit,
            "period": None, "baseline": baseline, "result": result, "scope": None,
            "attribution": attribution, "qualifiers": qualifiers or []}


def employment_proposal(request, example="E1"):
    raw = proposal(request, example).model_dump(by_alias=True)
    source = request.sources[0]
    facts = []

    def add(id, kind, value, literal, job=None):
        evidence = span(source, literal)
        facts.append({"tempId": id, "kind": kind, "value": value, "sourceId": source.id,
                      "unitIds": [evidence["unitId"]], "jobTempId": job, "subprojectTempId": None,
                      "importance": "normal", "literalEvidence": [evidence]})

    if example == "E1":
        for id, display, job in [("python", "Python", "north"), ("postgres", "PostgreSQL", "north"),
                                  ("java", "Java", "west"), ("mysql", "MySQL", "west"),
                                  ("php", "PHP", "east"), ("docker", "Docker", None)]:
            add(id, "technology", {"canonicalId": id, "display": display, "scope": "job" if job else "global"}, display, job)
        add("north-context", "text", {"text": "Сервис обработки заказов."}, "Сервис обработки заказов.", "north")
        add("north-task", "text", {"text": "Делала REST API для заказов, писала интеграционные тесты."},
            "Делала REST API для заказов, писала интеграционные тесты.", "north")
        add("north-result", "metric", metric(70, "мс", attribution="team", baseline="100", result="70", qualifiers=["на 30%"]),
            "Командой сократили время обработки со 100 до 70 мс, на 30%.", "north")
        add("trainees", "leadership", {"action": "Обучила двух новых разработчиков", "teamSize": metric(2, "разработчиков", attribution="personal"),
                                       "attribution": "personal"}, "Обучила двух новых разработчиков.", "north")
        add("west-task", "text", {"text": "Поддерживала CRM и исправляла ошибки."}, "Поддерживала CRM и исправляла ошибки.", "west")
        add("east-task", "text", {"text": "Разрабатывала отчёты."}, "Разрабатывала отчёты.", "east")
    else:
        for id, display, job in [("python", "Python", "gamma"), ("exampledb", "ExampleDB-X", "gamma"),
                                  ("sql", "SQL", "delta"), ("rust", "Rust", None)]:
            add(id, "technology", {"canonicalId": id, "display": display, "scope": "job" if job else "global"}, display, job)
        add("gamma-task", "text", {"text": "Built pipelines with Python and ExampleDB-X."},
            "Built pipelines with Python and ExampleDB-X.", "gamma")
        add("delta-task", "text", {"text": "Готовил отчёты."}, "Готовил отчёты.", "delta")
        for id, literal, number in [("gamma-team-five", "пять", 5), ("gamma-team-six", "шесть", 6)]:
            add(id, "leadership", {"action": "Размер команды", "teamSize": metric(number, "человек"),
                                    "attribution": "unknown"}, literal, "gamma")
    for job in raw["jobs"]:
        owned = {uid for item in facts if item["jobTempId"] == job["tempId"] for uid in item["unitIds"]}
        job["unitIds"] = sorted(set(job["unitIds"]) | owned)
        for period in job["periods"]:
            period["present"] = job["tempId"] == "north" and period["end"] is None
            period["evidence"] = [span(source, job["employer"])]
            # Period evidence includes its whole located source line, rather than only company text.
            period["evidence"][0]["text"] = next(unit.text.strip() for unit in source.units if unit.id == period["evidence"][0]["unitId"])
    for unit in raw["units"]:
        unit["factTempIds"] = [item["tempId"] for item in facts if unit["unitId"] in item["unitIds"]]
        unit["disposition"] = "facts" if unit["factTempIds"] else "unresolved"
    raw["facts"] = facts
    return GuiSemanticProposal.model_validate(raw)
