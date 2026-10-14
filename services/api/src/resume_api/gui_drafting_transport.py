"""Expose only writable prose fields and compact native draft references."""

import json

from packages.resume_core.gui_drafting import GuiDraftRequest, GuiDraftProposal


class DraftingTransport:
    def __init__(self, request: GuiDraftRequest):
        jobs = [job.id for job in request.normalized.employment]
        facts = [fact.id for fact in request.normalized.facts]
        fields = ["profile/text", "skills-focus/skillsText", "early-career/text"]
        fields.extend(f"job:{job}/{key}" for job in jobs for key in ("context", "tasks", "results", "stack"))
        reserved = set(jobs + facts + fields)
        prefix = ""
        while any(prefix + tag + str(i) in reserved for tag, values in (("j", jobs), ("f", facts), ("p", fields))
                  for i in range(len(values))):
            prefix += "_"
        self.jobs = {prefix + "j" + str(i): value for i, value in enumerate(jobs)}
        self.facts = {prefix + "f" + str(i): value for i, value in enumerate(facts)}
        self.fields = {prefix + "p" + str(i): value for i, value in enumerate(fields)}
        self.aliases = {value: key for mapping in (self.jobs, self.facts, self.fields) for key, value in mapping.items()}

    def encode(self, text: str) -> str:
        payload = json.loads(text)
        skeleton = payload["input"].pop("skeleton")
        payload["input"]["structuredContext"] = {
            key: skeleton[key] for key in ("candidate", "education", "certifications", "languages")
        }
        payload["input"]["writableFields"] = [
            {"fieldId": alias, "purpose": value.split("/")[-1],
             "jobId": self.aliases[value.split("/", 1)[0].removeprefix("job:")] if value.startswith("job:") else None,
             **({"allowedFactIds": [fact["id"] for fact in payload["input"]["facts"]
                 if fact["jobId"] == value.split("/", 1)[0].removeprefix("job:")]}
                if value.startswith("job:") else {}),
             "section": value.split("/", 1)[0] if not value.startswith("job:") else "job"}
            for alias, value in self.fields.items()
        ]
        options = {}
        for fact in payload["input"]["facts"]:
            if fact["kind"] == "technology":
                value = fact["value"]
                option = options.setdefault(value["canonicalId"], {"catalogId": value["canonicalId"],
                    "display": value["display"], "factIds": []})
                option["factIds"].append(fact["id"])
        payload["input"]["focusOptions"] = list(options.values())
        payload["input"]["output"] = (
            "Return fields only for the listed writableFields, plus editorialPlan. "
            "Never return candidate, education, certification, language, employer, role or period fields. "
            "These structured values are read-only context and the application preserves them. "
            "Use the short fieldId, jobId and fact IDs exactly. Return every non-job field, even when text is empty. "
            "For every detailed job return context, tasks, results and stack; empty text is allowed only when unsupported. "
            "Every nonempty field needs supporting factIds. Job fields use only their listed allowedFactIds; "
            "global and other-job IDs cannot support a job field. "
            "Account for all active jobs in editorialPlan.jobs. Keep formattingAsOf and rulesRevision unchanged. "
            "editorialPlan.focus entries must copy catalogId, display and factIds from focusOptions; "
            "choose at most eight supported technologies, or return focus=[]. Never attach text or employment facts to focus."
        )
        payload["constraints"][-1] = "Write supported prose fields and an EditorialPlan accounting for every active job."

        def visit(value):
            if isinstance(value, list):
                return [visit(part) for part in value]
            if not isinstance(value, dict):
                return value
            result = {}
            for key, part in value.items():
                if key in {"id", "jobId", "fieldId"} and isinstance(part, str):
                    result[key] = self.aliases.get(part, part)
                elif key in {"factIds", "allowedFactIds", "blockedConflictFactIds"} and isinstance(part, list):
                    result[key] = [self.aliases.get(item, item) for item in part]
                else:
                    result[key] = visit(part)
            return result

        encoded = json.dumps(visit(payload), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return encoded

    def restore(self, proposal: GuiDraftProposal) -> GuiDraftProposal:
        data = proposal.model_dump(mode="json", by_alias=True)

        def visit(value):
            if isinstance(value, list):
                return [visit(part) for part in value]
            if not isinstance(value, dict):
                return value
            result = {}
            for key, part in value.items():
                if key == "jobId" and isinstance(part, str):
                    result[key] = self.jobs.get(part, part)
                elif key == "fieldId" and isinstance(part, str):
                    result[key] = self.fields.get(part, part)
                elif key == "factIds" and isinstance(part, list):
                    result[key] = [self.facts.get(item, item) for item in part]
                else:
                    result[key] = visit(part)
            return result

        return GuiDraftProposal.model_validate(visit(data))
