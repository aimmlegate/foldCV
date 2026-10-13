"""Compact normalization references; restore canonical evidence before acceptance."""

import json
import re

from packages.resume_core.gui_normalization import GuiNormalizeRequest, GuiSemanticProposal, normalization_input, literal_contains, supported_text
from packages.resume_core.models.recovery import Rules
from packages.resume_core.normalization import UnitProposal
from packages.resume_core.normalization import _observed_number, _observed_date


class NormalizationTransport:
    def __init__(self, request: GuiNormalizeRequest):
        self.request = request
        reserved = {source.id for source in request.sources} | {unit.id for source in request.sources for unit in source.units}
        prefix = ""
        while any(prefix + "s" + str(i) in reserved for i in range(len(request.sources))) or any(
                prefix + "u" + str(i) in reserved for i in range(sum(len(source.units) for source in request.sources))):
            prefix += "_"
        self.sources = {prefix + "s" + str(i): source.id for i, source in enumerate(request.sources)}
        self.units = {}
        self.source_aliases = {value: key for key, value in self.sources.items()}
        self.unit_aliases = {}
        for source in request.sources:
            for unit in source.units:
                alias = prefix + "u" + str(len(self.units))
                self.units[alias] = unit.id
                self.unit_aliases[(source.id, unit.id)] = alias
        self.duplicates = {self.source_aliases[source.id] + ":" + self.unit_aliases[(source.id, unit.id)]:
                           source.id + ":" + unit.id for source in request.sources for unit in source.units}
        self.duplicates.update({self.unit_aliases[(source.id, unit.id)]: source.id + ":" + unit.id
                                for source in request.sources for unit in source.units})
        self.duplicates.update({self.source_aliases[source.id] + separator + self.unit_aliases[(source.id, unit.id)]:
            source.id + ":" + unit.id for separator in ("/", ".") for source in request.sources for unit in source.units})

    def prompt(self, rules: Rules) -> str:
        return self.encode(normalization_input(self.request, rules))

    def encode(self, text: str) -> str:
        payload = json.loads(text)
        payload["input"]["sources"] = [{"id": self.source_aliases[source.id], "revision": source.revision,
            "units": [{"id": self.unit_aliases[(source.id, unit.id)], "revision": unit.revision,
                       "text": unit.text} for unit in source.units]} for source in self.request.sources]
        payload["input"]["transportInstructions"] = (
            "Use the supplied short source/unit IDs for all references. Return compact JSON. "
            "units is sparse: return only administrative or duplicate classifications; normally return units=[]. "
            "The application derives complete unit fact accounting from literalEvidence and retains every other unit as unresolved. "
            "Include every supported job and claim. Job unitIds must include employer, exact role, dates and all its claim evidence. "
            "Text fact values, employer and role are exact source substrings, not rewritten prose. "
            "Every candidate, education, certification, language and private-detail text must be an exact substring of its cited evidence. "
            "Do not expand abbreviations, combine separate source fragments into a new value, or infer qualifications. Unknown text is empty with evidence=[]. "
            "Copy evidence text exactly from its unit; do not join separate units into a literal span."
        )
        payload["constraints"].append(
            "Normalization creates NEW job and fact tempIds; these are local proposal IDs, not source references. "
            "Only sourceId and unitId must use supplied IDs. Extract explicit technologies, duties, outcomes, metrics and context into facts; "
            "do not return facts=[] when such claims are present. Give each claim its exact literalEvidence and matching sourceId/unitIds. "
            "Use kind=text for a literal narrative claim and value={text: the exact claim}; use kind=technology for named tools. "
            "Use kind=metric only for explicit numeric source tokens: number and upperNumber must retain the literal magnitude, "
            "without scaling, arithmetic, rounding or invented counts; unit and qualifiers must occur in literalEvidence. "
            "For example, a source amount written as 2 million stays number=2 with the literal scale in unit, not number=2000000. "
            "Qualitative outcomes without a literal number are text facts. "
            "Keep global skills separate. Technology value.scope must be global when jobTempId=null, "
            "job when jobTempId is set and subprojectTempId=null, and subproject when both owner IDs are set. "
            "Create subprojects only with an explicit literal source name. "
            "Subproject unitIds include both its name and every evidence unit for its assigned facts."
        )
        payload["constraints"].append(
            "sourceObservedAt: explicit update date only. Unsupported/missing or after formattingAsOf: null, with evidence=null."
        )
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return text

    def restore(self, proposal: GuiSemanticProposal) -> GuiSemanticProposal:
        source_revisions = {source.id: source.revision for source in self.request.sources}
        units = {(source.id, unit.id): unit for source in self.request.sources for unit in source.units}

        def visit(value):
            if isinstance(value, list):
                return [visit(part) for part in value]
            if not isinstance(value, dict):
                return value
            result = {}
            for key, part in value.items():
                if key == "sourceId" and isinstance(part, str):
                    result[key] = self.sources.get(part, part)
                elif key == "unitId" and isinstance(part, str):
                    result[key] = self.units.get(part, part)
                elif key == "unitIds" and isinstance(part, list):
                    result[key] = [self.units.get(item, item) for item in part]
                elif key == "duplicateOf" and isinstance(part, str):
                    result[key] = self.duplicates.get(part, part)
                else:
                    result[key] = visit(part)
            if {"sourceId", "sourceRevision", "unitId", "unitRevision", "text"} <= result.keys():
                unit = units.get((result["sourceId"], result["unitId"]))
                if (unit and source_revisions[result["sourceId"]] == result["sourceRevision"]
                        and unit.revision == result["unitRevision"] and result["text"] not in unit.text):
                    words = result["text"].split()
                    if words:
                        matches = list(re.finditer(r"\s+".join(re.escape(word) for word in words), unit.text))
                        # Recover original spacing only within the exact cited unit and revision.
                        if len(matches) == 1:
                            result["text"] = matches[0].group()
            return result

        restored = GuiSemanticProposal.model_validate(visit(proposal.model_dump(mode="json", by_alias=True)))
        for collection, keys in (("education", ("institution", "qualification", "specialty", "date_text")),
                                 ("certifications", ("name", "issuer", "date_text")),
                                 ("languages", ("name", "proficiency"))):
            rows = getattr(restored, collection)
            # Native required fields can produce empty placeholders for an unknown optional row.
            setattr(restored, collection, [row for row in rows if any(
                getattr(row, key).text or getattr(row, key).evidence for key in keys)])
        observation = restored.observation_assessment
        if observation.source_observed_at and observation.evidence:
            span = observation.evidence
            unit = units.get((span.source_id, span.unit_id))
            verified = (unit is not None and source_revisions[span.source_id] == span.source_revision
                and unit.revision == span.unit_revision and span.text in unit.text)
            if verified and (not _observed_date(observation.source_observed_at, span.text)
                    or observation.source_observed_at.upper() > self.request.formatting_as_of.upper()):
                # An unsupported observation remains unknown; source dates are never shifted to today.
                observation.source_observed_at, observation.evidence = None, None
        details = [getattr(restored.candidate, key) for key in ("name", "title", "location")]
        for rows, keys in ((restored.education, ("institution", "qualification", "specialty", "date_text")),
                           (restored.certifications, ("name", "issuer", "date_text")),
                           (restored.languages, ("name", "proficiency"))):
            details.extend(getattr(row, key) for row in rows for key in keys)
        for detail in details:
            if not detail.text.strip() or len(detail.evidence) != 1 or supported_text(detail.text, detail.evidence, self.request.sources):
                continue
            anchor = detail.evidence[0]
            unit = units.get((anchor.source_id, anchor.unit_id))
            if (unit is None or source_revisions[anchor.source_id] != anchor.source_revision
                    or unit.revision != anchor.unit_revision or anchor.text.strip() != unit.text.strip()
                    or unit.location.kind != "page"):
                continue
            source = next(source for source in self.request.sources if source.id == anchor.source_id)
            ordered = sorted(source.units, key=lambda unit: unit.order)
            start = ordered.index(unit)
            group = [unit]
            for following in ordered[start + 1:]:
                if group[-1].order + 1 != following.order or following.location != unit.location:
                    break
                group.append(following)
            text = "\n".join(part.text for part in group)
            pattern = r"\s+".join(re.escape(word) for word in detail.text.split())
            matches = list(re.finditer(pattern, text, re.I))
            # Extend an exact full-unit citation only along its unique PDF continuation.
            if len(matches) != 1 or matches[0].start() >= len(unit.text) or matches[0].end() <= len(unit.text):
                continue
            end = matches[0].end()
            offset = len(unit.text)
            for following in group[1:]:
                if offset >= end:
                    break
                detail.evidence.append(anchor.model_copy(update={"unit_id": following.id,
                    "unit_revision": following.revision, "text": following.text}))
                offset += 1 + len(following.text)
        jobs = {job.temp_id: job for job in restored.jobs}
        self.unparsed_metrics = 0
        for index, fact in enumerate(restored.facts):
            valid_spans = bool(fact.literal_evidence) and all((unit := units.get((span.source_id, span.unit_id))) is not None
                and source_revisions[span.source_id] == span.source_revision and unit.revision == span.unit_revision
                and span.text in unit.text and span.source_id == fact.source_id for span in fact.literal_evidence)
            if valid_spans:
                # Literal spans already identify the units; the separate list is bookkeeping.
                fact.unit_ids = list(dict.fromkeys(span.unit_id for span in fact.literal_evidence))
                if fact.kind == "technology" and fact.job_temp_id is None and fact.subproject_temp_id is None:
                    # An unowned skill cannot acquire employment duration from a redundant scope label.
                    fact.value.scope = "global"
                job = jobs.get(fact.job_temp_id)
                if job and fact.source_id == job.source_id and set(fact.unit_ids) <= set(job.unit_ids):
                    subproject = next((sub for sub in job.subprojects if sub.temp_id == fact.subproject_temp_id), None)
                    if subproject:
                        # Complete redundant unit accounting within the already declared job boundary.
                        subproject.unit_ids = list(dict.fromkeys([*subproject.unit_ids, *fact.unit_ids]))
            literal = "\n".join(span.text for span in fact.literal_evidence)
            if fact.kind == "technology" and valid_spans:
                scope = "subproject" if fact.subproject_temp_id else "job" if fact.job_temp_id else "global"
                if fact.value.scope != scope and literal.strip() and len(literal) <= 500:
                    # Preserve the claim without deriving duration from conflicting scope metadata.
                    data = fact.model_dump(mode="json", by_alias=True)
                    data.update(kind="text", value={"text": literal})
                    restored.facts[index] = type(fact).model_validate(data)
                    continue
            if fact.kind == "text" and fact.value.text not in literal and not any(
                    literal_contains(fact.value.text, span.text) for span in fact.literal_evidence):
                if literal.strip() and len(literal) <= 500 and valid_spans:
                    # Store the verified claim instead of the model's unsupported paraphrase.
                    fact.value.text = literal
            if fact.kind != "metric":
                continue
            metric = fact.value
            numbers = [metric.number, *([metric.upper_number] if metric.upper_number is not None else [])]
            grounded = (all(_observed_number(number, literal) for number in numbers)
                and metric.unit.casefold() in literal.casefold()
                and all(value.casefold() in literal.casefold() for value in metric.qualifiers)
                and all(value is None or value in literal for value in (metric.baseline, metric.result)))
            if not grounded and literal.strip() and len(literal) <= 500 and valid_spans:
                # Keep the source claim without storing an unsupported numeric interpretation.
                data = fact.model_dump(mode="json", by_alias=True)
                data.update(kind="text", value={"text": literal})
                restored.facts[index] = type(fact).model_validate(data)
                self.unparsed_metrics += 1
        supplied = {(unit.source_id, unit.unit_id) for unit in restored.units}
        duplicate_targets = {source.id + ":" + unit.id for source in self.request.sources for unit in source.units}
        for unit in restored.units:
            if unit.disposition == "duplicate" and not unit.fact_temp_ids and unit.duplicate_of not in duplicate_targets:
                unit.disposition, unit.duplicate_of = "unresolved", None
        refs = {}
        for fact in restored.facts:
            for span in fact.literal_evidence:
                key = (span.source_id, span.unit_id)
                if fact.temp_id not in refs.setdefault(key, []):
                    refs[key].append(fact.temp_id)
        for source in self.request.sources:
            for unit in source.units:
                key = (source.id, unit.id)
                if key not in supplied:
                    fact_ids = refs.get(key, [])
                    restored.units.append(UnitProposal.model_validate({"sourceId": source.id, "unitId": unit.id,
                        "disposition": "facts" if fact_ids else "unresolved", "factTempIds": fact_ids, "duplicateOf": None}))
        return restored
