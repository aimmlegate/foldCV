"""Read-only navigation identity from the current working candidate."""

from .models.contracts import Wire


class ResumeIdentity(Wire):
    title: str
    subtitle: str


def resume_identity(workspace):
    if workspace.project is None:
        return ResumeIdentity(title=workspace.title, subtitle="")
    candidate = next((record for record in workspace.project.facts.records if record.kind == "candidate"), None)
    def compact(text):
        return " ".join(text.split())[:200]
    return ResumeIdentity(title=compact(candidate.name.raw_text) if candidate and candidate.name.raw_text.strip()
        else "Резюме без имени", subtitle=compact(candidate.title.raw_text) if candidate else "")


def display_identity(workspace):
    """The name the list and the header show. A manual title wins over the candidate name."""
    identity = resume_identity(workspace)
    if workspace.title_manually_set and workspace.title.strip():
        return identity.model_copy(update={'title': ' '.join(workspace.title.split())[:200]})
    return identity
