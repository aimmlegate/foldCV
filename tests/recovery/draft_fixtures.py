"""Supplied Draft/EditorialPlan responses; no fake Markdown interpretation."""

from packages.resume_core.gui_drafting import GuiDraftRequest, GuiDraftProposal
from packages.resume_core.gui_normalization import normalize_candidate
from packages.resume_core.gui_employment import normalize_employment
from packages.resume_core.rules import captured_rules, DEFAULT_RULES
from packages.resume_core.models.recovery import GuiTechnologyFact, GuiLeadershipFact, EmploymentFact
from tests.recovery.candidate_fixtures import ROOT, request
from tests.recovery.employment_fixtures import employment_proposal

RULES = captured_rules(DEFAULT_RULES, 1)


def draft_request(example="E1"):
    source = request((ROOT / f"{example}.txt").read_text())
    reply = employment_proposal(source, example)
    normalized = normalize_employment(source, reply, normalize_candidate(source, reply, RULES))
    return GuiDraftRequest.model_validate({"projectId": "draft-" + example, "projectRevision": 1,
        "documentRevision": 1, "normalized": normalized.model_dump(by_alias=True), "formattingAsOf": source.formatting_as_of.model_dump(by_alias=True)})


def draft_reply(request, *, rules_revision=1, detailed_old=False, example="E1"):
    normalized = request.normalized
    facts = normalized.facts
    ids = {fact.id for fact in facts}
    blocked = {id for conflict in normalized.conflicts for id in conflict.fact_ids}
    public = [fact.id for fact in facts if fact.kind not in {"name_assessment", "source_observation"} and fact.id not in blocked]
    fields = [{"fieldId": "profile/text", "text": "Разрабатываю backend-сервисы на Python." if example == "E1" else "Разрабатываю пайплайны данных.",
               "factIds": [fact.id for fact in facts if isinstance(fact, GuiTechnologyFact) and fact.value.display == "Python"]}]
    plan_jobs = []
    early = []
    for index, job in enumerate(normalized.employment):
        is_early = example == "E1" and index == 2 and not detailed_old
        owned = [fact.id for fact in facts if fact.job_id == job.id and fact.id not in blocked]
        plan_jobs.append({"jobId": job.id, "disposition": "early-career" if is_early else "detailed", "factIds": owned})
        if is_early:
            early.append(job)
            continue
        texts = {
            "context": "Сервис обработки заказов." if example == "E1" and index == 0 else "Внутренняя CRM." if example == "E1" and index == 1 else "",
            "tasks": "Разработка REST API для заказов.\nИнтеграционные тесты." if example == "E1" and index == 0 else
                     "Поддержка CRM и исправление ошибок." if example == "E1" and index == 1 else
                     "Разработка отчётов." if example == "E1" else "Built pipelines with Python and ExampleDB-X." if index == 0 else "Готовил отчёты.",
            "results": "В составе команды сократила время обработки со 100 до 70 мс — на 30%.\nОбучила двух новых разработчиков." if example == "E1" and index == 0 else "",
            "stack": ", ".join(fact.value.display for fact in facts if isinstance(fact, GuiTechnologyFact) and fact.job_id == job.id),
        }
        for key, text in texts.items():
            fields.append({"fieldId": f"job:{job.id}/{key}", "text": text, "factIds": owned if text else []})
    global_facts = [fact for fact in facts if isinstance(fact, GuiTechnologyFact) and fact.value.scope == "global"]
    fields.extend([{"fieldId": "skills-focus/skillsText", "text": ", ".join(fact.value.display for fact in global_facts), "factIds": [fact.id for fact in global_facts]},
                   {"fieldId": "early-career/text", "text": "Восток, 2008–2009. PHP. Разрабатывала отчёты." if early else "",
                    "factIds": [fact.id for fact in facts if early and fact.job_id == early[0].id]}])
    python = [fact for fact in facts if isinstance(fact, GuiTechnologyFact) and fact.value.canonical_id == "python"]
    plan = {"origin": "model", "revision": 1, "rulesRevision": rules_revision, "formattingAsOf": request.formatting_as_of.model_dump(by_alias=True),
            "sourceLanguage": "ru" if example == "E1" else "mixed", "profileLanguage": "ru", "jobs": plan_jobs,
            "focus": [{"catalogId": "python", "display": "Python", "factIds": [fact.id for fact in python]}],
            "technologyGroups": [{"title": "Backend", "factIds": [fact.id for fact in python]}], "factIds": public}
    return GuiDraftProposal.model_validate({"fields": fields, "editorialPlan": plan})
