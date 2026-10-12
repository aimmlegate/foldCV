"""Read-only compatibility views derived from the single authored Document."""

from .gui_derived import digest
from .models.contracts import Block
from .models.recovery import authored_fields, record_slot


def compatibility_views(document, facts):
    revisions = {fact.id: fact.revision for fact in facts}
    kinds = {"candidate": "contact", "profile": "profile", "job": "job_prose", "education": "education",
             "certification": "education", "language": "education", "skills-focus": "skills", "early-career": "early_career"}
    views = []
    for record in document.records():
        fields = authored_fields(record)
        text = "\n".join(field.text for field in fields if field.text.strip())
        ids = sorted({id for field in fields for id in field.fact_ids if id in revisions})
        views.append(Block(id=record_slot(record), kind=kinds[record.kind], revision=record.revision,
            state={"text": text, "origin": "generated", "locked": False, "factIds": ids,
                "factRevisions": {id: revisions[id] for id in ids}}, previous=None, visible=record.visible,
            status="ready" if text else "empty", dependencyHash=digest(record.model_dump(mode="json", by_alias=True)),
            contentPolicyVersion="gui-document-v1"))
    return views
