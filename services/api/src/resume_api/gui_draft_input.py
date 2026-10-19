"""Recover draft fields independently before canonical document assembly."""

from pydantic import ValidationError
import re

from packages.resume_core.gui_drafting import DraftField, GuiDraftProposal
from packages.resume_core.models.recovery import EditorialPlan, JobDisposition, PlanFocus, TechnologyGroup


class DraftInput:
    def __init__(self, request):
        self.request = request
        self.unresolved = 0
        self.guard = lambda: None

    def typed(self, model, value):
        self.guard()
        try:
            return model.model_validate(value, strict=True)
        except ValidationError:
            self.unresolved += 1
            return None

    def rows(self, value, limit):
        self.guard()
        if not isinstance(value, list):
            self.unresolved += 1
            return []
        if len(value) > limit:
            raise ValueError("draft row limit")
        return value

    def refs(self, value):
        if not isinstance(value, list):
            self.unresolved += 1
            return []
        refs = [ref for ref in value if isinstance(ref, str) and ref]
        if len(refs) != len(value):
            self.unresolved += 1
        return refs

    def parse(self, raw):
        if not isinstance(raw, dict):
            self.unresolved += 1
            raw = {}
        fields = []
        for row in self.rows(raw.get("fields"), 1000):
            if not isinstance(row, dict):
                self.unresolved += 1
                continue
            if (field := self.typed(DraftField, {"fieldId": row.get("fieldId"),
                    "text": row.get("text"), "factIds": self.refs(row.get("factIds"))})) is not None:
                fields.append(field)
        plan = raw.get("editorialPlan")
        if not isinstance(plan, dict):
            self.unresolved += 1
            plan = {}
        source = "\n".join(unit.text for item in self.request.normalized.sources for unit in item.units)
        language = "ru" if len(re.findall(r"[А-Яа-яЁё]", source)) > len(re.findall(r"[A-Za-z]", source)) else "en"
        defaults = dict(origin="model", revision=1, rulesRevision=self.request.normalized.rules_revision,
            formattingAsOf=self.request.formatting_as_of.model_dump(by_alias=True), sourceLanguage=language,
            profileLanguage=language, jobs=[], focus=[], technologyGroups=[], factIds=[])
        for key in ("origin", "revision", "rulesRevision", "formattingAsOf", "sourceLanguage", "profileLanguage"):
            if key in plan:
                trial = {**defaults, key: plan[key]}
                if self.typed(EditorialPlan, trial) is not None:
                    defaults[key] = plan[key]
        if "profileLanguage" not in plan and defaults["sourceLanguage"] in {"ru", "en"}:
            defaults["profileLanguage"] = defaults["sourceLanguage"]
        for key, model, limit in (("jobs", JobDisposition, 100), ("focus", PlanFocus, 1000),
                                  ("technologyGroups", TechnologyGroup, 1000)):
            rows, seen = [], set()
            for row in self.rows(plan.get(key), limit):
                if isinstance(row, dict):
                    row = {**row, "factIds": self.refs(row.get("factIds"))}
                item = self.typed(model, row)
                if item is None:
                    continue
                if key == "jobs":
                    if item.job_id in seen:
                        self.unresolved += 1
                        continue
                    seen.add(item.job_id)
                rows.append(item)
            defaults[key] = rows
        defaults["factIds"] = self.refs(plan.get("factIds"))
        return GuiDraftProposal(fields=fields, editorialPlan=EditorialPlan.model_validate(defaults))
