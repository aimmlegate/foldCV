"""GUI candidate normalization over immutable canonical source evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, PrivateAttr, model_validator

from .extraction.models import ExtractResult
from .gui_prompts import CONTENT_INPUT_BYTES, content_input
from .models.contracts import Evidence, Id, Job, PartialDate, Revision, Source, Wire
from .models.recovery import (
    CandidateFact, EvidenceSpan, NameAssessment, NameAssessmentFact, ObservationAssessment,
    ObservationFact, RecoveryFact, Rules,
)
from .normalization import ProposedFact, ProposedJob, SemanticProposal, _id
from .models.rich_facts import ExtractionReport


class SupportedText(Wire):
    text: str = Field(max_length=4000)
    evidence: list[EvidenceSpan]


class CandidateDetails(Wire):
    name: SupportedText
    title: SupportedText
    location: SupportedText


class EducationDetails(Wire):
    id: Id
    institution: SupportedText
    qualification: SupportedText
    specialty: SupportedText
    date_text: SupportedText


class CertificationDetails(Wire):
    id: Id
    name: SupportedText
    issuer: SupportedText
    date_text: SupportedText


class LanguageDetails(Wire):
    id: Id
    name: SupportedText
    proficiency: SupportedText


class PrivateDetails(Wire):
    kind: Literal["phone", "email", "messenger", "birth_date", "age", "platform_metadata"]
    value: SupportedText


class GuiNormalizeRequest(Wire):
    sources: list[Source] = Field(min_length=1, max_length=10)
    formatting_as_of: PartialDate
    revision: Revision

    @model_validator(mode="after")
    def usable_sources(self) -> GuiNormalizeRequest:
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("DUPLICATE_SOURCE")
        if not any(unit.text.strip() for source in self.sources for unit in source.units):
            raise ValueError("NO_USABLE_TEXT")
        return self


class GuiPeriodProposal(Wire):
    start: PartialDate | None
    end: PartialDate | None
    present: bool = False
    start_text: str | None = None
    end_text: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class GuiJobProposal(ProposedJob):
    periods: list[GuiPeriodProposal] = Field(max_length=20)


class GuiFactProposal(ProposedFact):
    literal_evidence: list[EvidenceSpan] = Field(default_factory=list)


class FactConflict(Wire):
    id: Id
    job_id: Id
    code: Literal["team_size_conflict"]
    fact_ids: list[Id]
    evidence: list[EvidenceSpan]


class NormalizedPeriod(Wire):
    id: Id
    start: PartialDate | None
    end: PartialDate | None
    start_text: str
    end_text: str
    present: bool
    evidence: list[EvidenceSpan]


class GuiSemanticProposal(SemanticProposal):
    jobs: list[GuiJobProposal] = Field(max_length=100)
    facts: list[GuiFactProposal] = Field(max_length=500)
    candidate: CandidateDetails
    education: list[EducationDetails] = Field(max_length=40)
    certifications: list[CertificationDetails] = Field(max_length=40)
    languages: list[LanguageDetails] = Field(max_length=40)
    private_details: list[PrivateDetails] = Field(max_length=100)
    name_assessment: NameAssessment
    observation_assessment: ObservationAssessment


class GuiNormalizedResult(Wire):
    _native_recovery_count: int = PrivateAttr(default=0)
    sources: list[Source]
    facts: list[RecoveryFact]
    candidate: CandidateDetails
    education: list[EducationDetails]
    certifications: list[CertificationDetails]
    languages: list[LanguageDetails]
    private_details: list[PrivateDetails]
    name_assessment: NameAssessment
    observation_assessment: ObservationAssessment
    source_observed_at: PartialDate | None
    field_fact_ids: dict[str, list[Id]]
    source_fingerprint: str
    rules_revision: Revision
    semantic_proposal: GuiSemanticProposal
    employment: list[Job] = Field(default_factory=list)
    job_periods: dict[str, list[NormalizedPeriod]] = Field(default_factory=dict)
    conflicts: list[FactConflict] = Field(default_factory=list)
    extraction: ExtractionReport | None = None


class NormalizationFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical_source(result: ExtractResult, *, source_id: str | None = None) -> Source:
    identity = source_id if source_id is not None else result.source_id
    units = []
    for unit in result.units:
        location = unit.location
        kind = "table_cell" if location.kind == "table_cell" else "page" if location.page else "pasted" if location.kind == "pasted" else "paragraph"
        index = location.page - 1 if location.page else location.table if kind == "table_cell" else location.paragraph
        units.append({"id": f"{identity}/{unit.id}", "revision": 1, "order": unit.order,
                      "text": unit.text.replace("\r\n", "\n").replace("\r", "\n"),
                      "location": {"kind": kind, "index": index if index is not None else unit.order,
                                   "row": location.row if kind == "table_cell" else None,
                                   "column": location.column if kind == "table_cell" else None},
                      "structure": unit.structure.model_dump(by_alias=True) if unit.structure else None,
                      "disposition": "unresolved", "representedFactIds": []})
    return Source.model_validate({"id": identity, "revision": 1, "originalName": result.original_name,
                                  "mimeType": result.mime_type, "byteSha256": result.byte_sha256,
                                  "byteRef": f"sources/{identity}/original",
                                  "parser": result.parser, "parserVersion": result.parser_version,
                                  "units": units, "overlays": [],
                                  "warnings": [gap.code for gap in result.gaps],
                                  "warningDetails": [{"code": gap.code, "page": gap.location.page} for gap in result.gaps]})


def source_fingerprint(sources: list[Source]) -> str:
    payload = [source.model_dump(mode="json", by_alias=True, exclude={"units": {"__all__": {"represented_fact_ids", "disposition"}}})
               for source in sources]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def normalization_input(request: GuiNormalizeRequest, rules: Rules, *, transform=None, max_bytes=CONTENT_INPUT_BYTES, return_canonical=False) -> str:
    payload = request.model_dump(mode="json", by_alias=True)
    payload["assessmentInstructions"] = (
        "missingSurname is true only with explicit source evidence of absence, false for a supported surname or explicit mononym, null otherwise. "
        "sourceObservedAt may come only from an explicit dated statement in the source, at its original precision, with its literal evidence span. "
        "No source observation means null; file metadata and formattingAsOf do not supply it. "
        "Retain candidate contacts and other details with exact evidence in privateDetails (a legacy descriptive field). All employment shares this result."
        " Supply literalEvidence for every employment fact and exact source/unit references. "
        "Keep global skills separate from job/subproject skills. Keep conflicting claims separate, without asserting personal leadership. "
        "Set present=true only for explicit ongoing work; a missing end date alone is not present. Preserve incomplete/unknown period text."
    )
    return content_input("normalize_semantics", payload, rules, transform=transform, max_bytes=max_bytes, return_canonical=return_canonical)


def validate_span(span: EvidenceSpan, sources: list[Source]) -> Evidence:
    source = next((source for source in sources if source.id == span.source_id and source.revision == span.source_revision), None)
    unit = next((unit for unit in source.units if unit.id == span.unit_id and unit.revision == span.unit_revision), None) if source else None
    if unit is None or span.text not in unit.text:
        raise NormalizationFailure("INVALID_SOURCE_EVIDENCE")
    return Evidence.model_validate(span.model_dump(by_alias=True, exclude={"text"}))


def literal_contains(value: str, source: str) -> bool:
    return " ".join(value.split()) in " ".join(source.split())


def supported_text(value: str, spans: list[EvidenceSpan], sources: list[Source]) -> bool:
    if any(literal_contains(value.casefold(), span.text.casefold()) for span in spans):
        return True
    if len(spans) < 2:
        return False
    located = []
    for span in spans:
        source = next((source for source in sources if source.id == span.source_id and source.revision == span.source_revision), None)
        unit = next((unit for unit in source.units if unit.id == span.unit_id and unit.revision == span.unit_revision), None) if source else None
        if unit is None or span.text.strip() != unit.text.strip() or unit.location.kind != "page":
            return False
        located.append(unit)
    # Consecutive complete PDF units on the same page prove a wrapped source continuation.
    if any(a.source_id != b.source_id or a.source_revision != b.source_revision
           or first.order + 1 != second.order or first.location != second.location
           for a, b, first, second in zip(spans, spans[1:], located, located[1:])):
        return False
    return literal_contains(value.casefold(), "\n".join(unit.text for unit in located).casefold())


def normalize_candidate(request: GuiNormalizeRequest, proposal: GuiSemanticProposal, rules: Rules) -> GuiNormalizedResult:
    sources = [source.model_copy(deep=True) for source in request.sources]
    for source in sources:
        for unit in source.units:unit.represented_fact_ids = []
    facts: list[RecoveryFact] = []
    field_refs: dict[str, list[str]] = {}
    all_refs = [Evidence.model_validate({"sourceId": source.id, "sourceRevision": source.revision,
                                       "unitId": unit.id, "unitRevision": unit.revision})
                for source in sources for unit in source.units if unit.text.strip()]

    def add_fact(fact):
        facts.append(fact)
        for evidence in fact.evidence:
            unit = next(unit for source in sources if source.id == evidence.source_id
                        for unit in source.units if unit.id == evidence.unit_id)
            if fact.id not in unit.represented_fact_ids:
                unit.represented_fact_ids.append(fact.id)

    def add_text(field_id: str, value: SupportedText, category: str):
        refs = [validate_span(span, sources) for span in value.evidence]
        # PDF line wraps may differ from the supported field's display spacing.
        if value.text and (not refs or not supported_text(value.text, value.evidence, sources)):
            raise NormalizationFailure("UNSUPPORTED_CANDIDATE_VALUE")
        if not value.text:
            if value.evidence:
                raise NormalizationFailure("EMPTY_VALUE_HAS_EVIDENCE")
            field_refs[field_id] = []
            return
        fact_id = _id("fact", field_id, value.text, *[f"{ref.source_id}:{ref.unit_id}" for ref in refs])
        fact = CandidateFact.model_validate({"id": fact_id, "revision": request.revision, "kind": "candidate_detail",
                                            "value": {"field": category, "text": value.text, "fieldId": field_id},
                                            "evidence": [ref.model_dump(by_alias=True) for ref in refs],
                                            "origin": "source", "importance": "normal", "jobId": None, "subprojectId": None})
        add_fact(fact)
        field_refs[field_id] = [fact_id]

    for key in ("name", "title", "location"):
        add_text(f"candidate/{key}", getattr(proposal.candidate, key), key)
    row_groups = [("education", proposal.education, ("institution", "qualification", "specialty", "date_text")),
                  ("certification", proposal.certifications, ("name", "issuer", "date_text")),
                  ("language", proposal.languages, ("name", "proficiency"))]
    copied_groups = {}
    for kind, rows, keys in row_groups:
        output = []
        if len({row.id for row in rows}) != len(rows):
            raise NormalizationFailure("DUPLICATE_DETAIL_ID")
        for row in rows:
            values = [getattr(row, key) for key in keys]
            stable_id = _id(kind, *[value.text for value in values],
                            *[f"{span.source_id}:{span.unit_id}" for value in values for span in value.evidence])
            if not any(value.text for value in values):
                raise NormalizationFailure("EMPTY_DETAIL_ROW")
            for key, value in zip(keys, values):
                alias = "dateText" if key == "date_text" else key
                add_text(f"{kind}:{stable_id}/{alias}", value, kind)
            output.append(row.model_copy(update={"id": stable_id}, deep=True))
        copied_groups[kind] = output
    for index, item in enumerate(proposal.private_details):
        add_text(f"private/{item.kind}/{index}", item.value, "private_metadata")
    name = proposal.name_assessment.model_copy(update={"revision": request.revision}, deep=True)
    refs = [validate_span(span, sources) for span in name.evidence]
    if name.missing_surname is not None and not refs:
        raise NormalizationFailure("NAME_ASSESSMENT_NEEDS_EVIDENCE")
    name_id = _id("fact", "name-assessment", source_fingerprint(request.sources))
    add_fact(NameAssessmentFact.model_validate({"id": name_id, "revision": request.revision,
              "kind": "name_assessment", "value": name.model_dump(by_alias=True),
              "evidence": [ref.model_dump(by_alias=True) for ref in refs or all_refs],
              "origin": "source", "importance": "normal", "jobId": None, "subprojectId": None}))
    observation = proposal.observation_assessment.model_copy(update={"revision": request.revision}, deep=True)
    observed_refs = [validate_span(observation.evidence, sources)] if observation.evidence else []
    if observation.source_observed_at and observation.source_observed_at.upper() > request.formatting_as_of.upper():
        raise NormalizationFailure("SOURCE_OBSERVATION_AFTER_FORMATTING_DATE")
    observation_id = _id("fact", "source-observation", source_fingerprint(request.sources))
    add_fact(ObservationFact.model_validate({"id": observation_id, "revision": request.revision,
              "kind": "source_observation", "value": observation.model_dump(by_alias=True),
              "evidence": [ref.model_dump(by_alias=True) for ref in observed_refs or all_refs],
              "origin": "source", "importance": "normal", "jobId": None, "subprojectId": None}))
    return GuiNormalizedResult.model_validate({"sources": [source.model_dump(by_alias=True) for source in sources],
        "facts": [fact.model_dump(by_alias=True) for fact in facts], "candidate": proposal.candidate.model_dump(by_alias=True),
        "education": [row.model_dump(by_alias=True) for row in copied_groups["education"]],
        "certifications": [row.model_dump(by_alias=True) for row in copied_groups["certification"]],
        "languages": [row.model_dump(by_alias=True) for row in copied_groups["language"]],
        "privateDetails": [row.model_dump(by_alias=True) for row in proposal.private_details],
        "nameAssessment": name.model_dump(by_alias=True), "observationAssessment": observation.model_dump(by_alias=True),
        "sourceObservedAt": observation.source_observed_at.model_dump(by_alias=True) if observation.source_observed_at else None,
        "fieldFactIds": field_refs, "sourceFingerprint": source_fingerprint(request.sources),
        "rulesRevision": rules.revision, "semanticProposal": proposal.model_dump(by_alias=True)})


GUI_NORMALIZATION_CONTRACTS = {
    "gui_normalize_request": GuiNormalizeRequest,
    "gui_semantic_proposal": GuiSemanticProposal,
    "gui_normalized_result": GuiNormalizedResult,
}


def public_context_facts(facts: list[RecoveryFact]) -> list[RecoveryFact]:
    return [fact for fact in facts if not isinstance(fact, (NameAssessmentFact, ObservationFact))]
