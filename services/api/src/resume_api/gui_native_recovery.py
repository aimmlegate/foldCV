"""Accept native rows independently through the canonical validators."""

from collections import Counter
import json

from pydantic import ValidationError

from packages.resume_core.gui_employment import normalize_employment
from packages.resume_core.gui_normalization import (
    EvidenceSpan, GuiPeriodProposal, NormalizationFailure, SupportedText, literal_contains,
    normalize_candidate, supported_text, validate_span,
)
from packages.resume_core.normalization import UnitProposal, _observed_date



class NativeRecovery:
    def __init__(self, request, rules):
        self.request, self.rules = request, rules
        self.unresolved = 0
        self.guard = lambda: None
        self.units = {(source.id, unit.id): unit for source in request.sources for unit in source.units}

    def valid_spans(self, spans):
        try:
            for span in spans:
                validate_span(span, self.request.sources)
            return True
        except NormalizationFailure:
            return False

    def text(self, value):
        self.guard()
        spans = [span for span in value.evidence if self.valid_spans([span])]
        if len(spans) != len(value.evidence):
            self.unresolved += 1
        if (not value.text and not spans or value.text and spans
                and supported_text(value.text, spans, self.request.sources)):
            return value.model_copy(update={"evidence": spans}, deep=True)
        self.unresolved += 1
        return SupportedText(text="", evidence=[])

    def ledger(self, facts):
        refs = {}
        for fact in facts:
            self.guard()
            for span in fact.literal_evidence:
                refs.setdefault((span.source_id, span.unit_id), []).append(fact.temp_id)
        return [UnitProposal(sourceId=source.id, unitId=unit.id,
            disposition="facts" if (ids := list(dict.fromkeys(refs.get((source.id, unit.id), [])))) else "unresolved",
            factTempIds=ids, duplicateOf=None) for source in self.request.sources for unit in source.units]

    def accepts(self, base, proposal, jobs, facts):
        self.guard()
        trial = proposal.model_copy(update={"jobs": jobs, "facts": facts, "units": self.ledger(facts)})
        try:
            normalize_employment(self.request, trial, base)
            self.guard()
            return True
        except (NormalizationFailure, ValidationError):
            return False

    def period(self, proposal, base, job, period):
        if self.accepts(base, proposal, [job.model_copy(update={"periods": [period]})], []):
            return period
        self.unresolved += 1
        spans = [span for span in period.evidence if span.source_id == job.source_id
                 and span.unit_id in job.unit_ids and self.valid_spans([span])]
        text = "\n".join(span.text for span in spans)
        start = period.start_text if period.start_text and literal_contains(period.start_text, text) else None
        end = period.end_text if period.end_text and literal_contains(period.end_text, text) else None
        if not start and not end:
            return None
        recovered = GuiPeriodProposal(start=None, end=None, present=False,
            startText=start, endText=end, evidence=spans)
        if self.accepts(base, proposal, [job.model_copy(update={"periods": [recovered]})], []):
            return recovered
        return None

    def recover(self, incoming):
        clean = incoming.model_copy(deep=True)
        private = []
        for row in clean.private_details:
            value = self.text(row.value)
            if value.text:
                private.append(row.model_copy(update={"value": value}))
            else:
                # Retain independently supported fragments when their combined value is unsupported.
                for span in row.value.evidence:
                    if span.text and len(span.text) <= 4000 and self.valid_spans([span]):
                        private.append(row.model_copy(update={"value": SupportedText(text=span.text, evidence=[span])}))
        if len(private) > 100:
            raise ValueError("native private detail limit")
        clean.private_details = private
        for key in ("name", "title", "location"):
            setattr(clean.candidate, key, self.text(getattr(clean.candidate, key)))
        for key, fields in (("education", ("institution", "qualification", "specialty", "date_text")),
                            ("certifications", ("name", "issuer", "date_text")),
                            ("languages", ("name", "proficiency"))):
            rows, seen = [], set()
            for row in getattr(clean, key):
                for field in fields:
                    setattr(row, field, self.text(getattr(row, field)))
                signature = json.dumps(row.model_dump(mode="json", exclude={"id"}), sort_keys=True)
                if not any(getattr(row, field).text for field in fields) or signature in seen:
                    self.unresolved += 1
                    continue
                seen.add(signature)
                rows.append(row)
            setattr(clean, key, rows)
        name = clean.name_assessment
        if not self.valid_spans(name.evidence) or name.missing_surname is not None and not name.evidence:
            self.unresolved += 1
            name.missing_surname, name.evidence = None, []
        observed = clean.observation_assessment
        if (observed.evidence and not self.valid_spans([observed.evidence]) or observed.source_observed_at
                and (not observed.evidence or not _observed_date(observed.source_observed_at, observed.evidence.text)
                     or observed.source_observed_at.upper() > self.request.formatting_as_of.upper())):
            self.unresolved += 1
            observed.source_observed_at, observed.evidence = None, None
        clean.jobs, clean.facts, clean.units = [], [], self.ledger([])
        base = normalize_candidate(self.request, clean, self.rules)
        ids = Counter(job.temp_id for job in incoming.jobs)
        for original in incoming.jobs:
            self.guard()
            if ids[original.temp_id] != 1:
                self.unresolved += 1
                continue
            refs = list(dict.fromkeys(uid for uid in original.unit_ids if (original.source_id, uid) in self.units))
            if not refs:
                self.unresolved += 1
                continue
            if refs != original.unit_ids:
                self.unresolved += 1
            job = original.model_copy(update={"unit_ids": refs, "periods": [], "subprojects": []}, deep=True)
            source = next(source for source in self.request.sources if source.id == job.source_id)
            header_spans = [EvidenceSpan(sourceId=source.id, sourceRevision=source.revision, unitId=uid,
                unitRevision=self.units[(source.id, uid)].revision, text=self.units[(source.id, uid)].text) for uid in refs]
            if not self.accepts(base, clean, [*clean.jobs, job], []):
                self.unresolved += 1
                continue
            job.periods = [recovered for period in original.periods
                if (recovered := self.period(clean, base, job, period)) is not None]
            sub_ids = Counter(sub.temp_id for sub in original.subprojects)
            for sub in original.subprojects:
                trial = job.model_copy(update={"subprojects": [*job.subprojects, sub]})
                if sub_ids[sub.temp_id] == 1 and self.accepts(base, clean, [trial], []):
                    job.subprojects.append(sub)
                    continue
                self.unresolved += 1
                stripped = sub.model_copy(update={"period": None})
                trial = job.model_copy(update={"subprojects": [*job.subprojects, stripped]})
                if sub_ids[sub.temp_id] == 1 and self.accepts(base, clean, [trial], []):
                    job.subprojects.append(stripped)
            clean.jobs.append(job)
        ids = Counter(fact.temp_id for fact in incoming.facts)
        for fact in incoming.facts:
            self.guard()
            spans = [span for span in fact.literal_evidence
                if span.source_id == fact.source_id and self.valid_spans([span])]
            if len(spans) != len(fact.literal_evidence):
                self.unresolved += 1
            fact = fact.model_copy(update={"literal_evidence": spans,
                "unit_ids": list(dict.fromkeys(span.unit_id for span in spans))})
            if ids[fact.temp_id] == 1 and self.accepts(base, clean, clean.jobs, [fact]):
                clean.facts.append(fact)
            else:
                self.unresolved += 1
        clean.units = self.ledger(clean.facts)
        return clean
