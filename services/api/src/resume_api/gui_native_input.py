"""Read native proposal rows independently before canonical validation."""

from pydantic import ValidationError

from packages.resume_core.gui_normalization import (
    CandidateDetails, CertificationDetails, EducationDetails, EvidenceSpan,
    GuiFactProposal, GuiJobProposal, GuiPeriodProposal, GuiSemanticProposal,
    LanguageDetails, PrivateDetails, SupportedText,
)
from packages.resume_core.models.contracts import PartialDate, Period
from packages.resume_core.models.recovery import NameAssessment, ObservationAssessment
from packages.resume_core.normalization import ProposedSubproject, _id


class NativeInput:
    def __init__(self, request):
        self.request = request
        self.unresolved = 0
        self.guard = lambda: None

    def typed(self, model, value, default=None):
        self.guard()
        if isinstance(value, dict):
            keys = {field.alias or name for name, field in model.model_fields.items()}
            if set(value) - keys:
                self.unresolved += 1
            value = {key: part for key, part in value.items() if key in keys}
        try:
            return model.model_validate(value, strict=True)
        except ValidationError:
            self.unresolved += 1
            return default

    def rows(self, value, limit):
        self.guard()
        if not isinstance(value, list):
            if value is not None:
                self.unresolved += 1
            return []
        if len(value) > limit:
            raise ValueError("native row limit")
        return value

    def spans(self, value):
        return [span for raw in self.rows(value, 500)
                if (span := self.typed(EvidenceSpan, raw)) is not None]

    def text(self, value):
        empty = SupportedText(text="", evidence=[])
        if not isinstance(value, dict):
            if value is not None:
                self.unresolved += 1
            return empty
        spans = self.spans(value.get("evidence"))
        return self.typed(SupportedText, {"text": value.get("text", ""),
            "evidence": [span.model_dump(by_alias=True) for span in spans]},
            SupportedText(text="", evidence=spans))

    def date(self, value):
        return self.typed(PartialDate, value) if value is not None else None

    def period(self, raw):
        if not isinstance(raw, dict):
            self.unresolved += 1
            return None
        present = raw.get("present", False)
        if type(present) is not bool:
            self.unresolved += 1
            present = False
        texts = {}
        for key in ("startText", "endText"):
            text = raw.get(key)
            if text is not None and not isinstance(text, str):
                self.unresolved += 1
                text = None
            texts[key] = text
        return self.typed(GuiPeriodProposal, {"start": self.date(raw.get("start")),
            "end": self.date(raw.get("end")), "present": present,
            **texts,
            "evidence": self.spans(raw.get("evidence"))})

    def details(self, model, value, keys, limit):
        result = []
        for index, raw in enumerate(self.rows(value, limit)):
            if not isinstance(raw, dict):
                self.unresolved += 1
                continue
            row = {key: self.text(raw.get(key)) for key in keys}
            row["id"] = _id("native-row", model.__name__, str(index))
            result.append(model.model_validate(row))
        return result

    def jobs(self, value):
        result = []
        for raw in self.rows(value, 100):
            if not isinstance(raw, dict):
                self.unresolved += 1
                continue
            row = dict(raw)
            row["periods"] = [period for part in self.rows(row.get("periods"), 20)
                if (period := self.period(part)) is not None]
            subs = []
            for part in self.rows(row.get("subprojects"), 100):
                if isinstance(part, dict):
                    part = dict(part)
                    if part.get("period") is not None:
                        part["period"] = self.typed(Period, part["period"])
                if (sub := self.typed(ProposedSubproject, part)) is not None:
                    subs.append(sub)
            row["subprojects"] = subs
            if (job := self.typed(GuiJobProposal, row)) is not None:
                result.append(job)
        return result

    def facts(self, value):
        result = []
        for index, raw in enumerate(self.rows(value, 500)):
            if isinstance(raw, dict):
                raw = dict(raw)
                spans = self.spans(raw.get("literalEvidence"))
                raw["literalEvidence"] = spans
                if "tempId" not in raw:
                    raw["tempId"] = _id("native-fact", str(index))
                if not raw.get("unitIds"):
                    raw["unitIds"] = list(dict.fromkeys(span.unit_id for span in spans))
                sources = {span.source_id for span in spans}
                if "sourceId" not in raw and len(sources) == 1:
                    raw["sourceId"] = next(iter(sources))
            if (fact := self.typed(GuiFactProposal, raw)) is not None:
                result.append(fact)
                continue
            if (not isinstance(raw, dict) or not isinstance(raw.get("kind"), str)
                    or raw["kind"] not in {"text", "technology", "date", "metric", "leadership"}):
                continue
            spans = raw["literalEvidence"]
            literal = "\n".join(span.text for span in spans)
            if not literal.strip() or len(literal) > 500:
                continue
            row = dict(raw)
            row.update(tempId=_id("native-fact", str(index)), kind="text", value={"text": literal},
                literalEvidence=spans, unitIds=list(dict.fromkeys(span.unit_id for span in spans)))
            if (fact := self.typed(GuiFactProposal, row)) is not None:
                result.append(fact)
        return result

    def parse(self, value):
        if (not isinstance(value, dict) or type(value.get("schemaVersion", 1)) is not int or value.get("schemaVersion", 1) != 1
                or not {"candidate", "jobs", "facts"}.intersection(value)):
            raise ValueError("native proposal envelope")
        self.unresolved += sum(key not in value for key in
                               ("candidate", "jobs", "facts", "nameAssessment", "observationAssessment"))
        candidate = value.get("candidate")
        candidate = candidate if isinstance(candidate, dict) else {}
        private = []
        for raw in self.rows(value.get("privateDetails"), 100):
            if not isinstance(raw, dict):
                self.unresolved += 1
                continue
            kind = raw.get("kind")
            if not isinstance(kind, str) or kind not in {"phone", "email", "messenger", "birth_date", "age", "platform_metadata"}:
                self.unresolved += 1
                kind = "platform_metadata"
            private.append(PrivateDetails(kind=kind, value=self.text(raw.get("value"))))
        name = value.get("nameAssessment")
        name = name if isinstance(name, dict) else {}
        name = self.typed(NameAssessment, {"missingSurname": name.get("missingSurname"),
            "evidence": self.spans(name.get("evidence")), "revision": self.request.revision},
            NameAssessment(missingSurname=None, evidence=[], revision=self.request.revision))
        observation = value.get("observationAssessment")
        observation = observation if isinstance(observation, dict) else {}
        date = self.date(observation.get("sourceObservedAt"))
        evidence = self.typed(EvidenceSpan, observation["evidence"]) if observation.get("evidence") is not None else None
        observation = self.typed(ObservationAssessment,
            {"sourceObservedAt": date, "evidence": evidence, "revision": self.request.revision},
            ObservationAssessment(sourceObservedAt=None, evidence=None, revision=self.request.revision))
        return GuiSemanticProposal(schemaVersion=1, candidate=CandidateDetails(**{
            key: self.text(candidate.get(key)) for key in ("name", "title", "location")}),
            education=self.details(EducationDetails, value.get("education"),
                ("institution", "qualification", "specialty", "dateText"), 40),
            certifications=self.details(CertificationDetails, value.get("certifications"), ("name", "issuer", "dateText"), 40),
            languages=self.details(LanguageDetails, value.get("languages"), ("name", "proficiency"), 40),
            privateDetails=private, nameAssessment=name, observationAssessment=observation,
            jobs=self.jobs(value.get("jobs")), facts=self.facts(value.get("facts")), units=[])
