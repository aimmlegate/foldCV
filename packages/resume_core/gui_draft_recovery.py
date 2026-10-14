"""Keep content problems visible without rejecting an imported document."""

from .models.recovery import Annotation
from .normalization import _id


class DraftWarnings:
    def __init__(self, request, rules):
        self.request, self.rules = request, rules
        self.marks = {}

    def add(self, code, field_id=None, reason="Review the imported content and its source references."):
        key = (code, field_id)
        self.marks[key] = Annotation(id=_id("annotation", self.request.project_id, code, field_id or "document"),
            type="warning", code=code, anchor={"kind": "field", "fieldId": field_id, "range": None}
            if field_id else {"kind": "document"},
            dependencies={"projectRevision": self.request.project_revision,
                "documentRevision": self.request.document_revision, "rulesSha256": self.rules.sha256,
                "sourceFingerprint": self.request.normalized.source_fingerprint,
                "dependencyFingerprint": self.request.normalized.source_fingerprint},
            factIds=[], reason=reason, evidence=[], resolved=False, updateSuggestionId=None, removedFocus=[])


def literal_prose(facts):
    parts = []
    for fact in facts:
        if fact.kind == "text":
            parts.append(fact.value.text)
        elif fact.kind == "technology":
            parts.append(fact.value.display)
        elif fact.kind in {"metric", "leadership"}:
            parts.extend(span.text for span in getattr(fact, "literal_evidence", []))
    return "\n".join(dict.fromkeys(part for part in parts if part.strip()))


def fill_literal(field, facts):
    field.text = literal_prose(facts)
    if field.text:
        field.fact_ids = [fact.id for fact in facts if literal_prose([fact])]
        field.evidence = [ref for fact in facts if fact.id in field.fact_ids for ref in fact.evidence]
        field.origin = "source"
