"""One source-preserving materialization for direct and queued import."""

from packages.resume_core.import_agent import assemble_agent_import, checksum
from packages.resume_core.import_diagnostics import source_warnings
from packages.resume_core.models.rich_workspace import RichWarning


def import_workspace(workspace, draft, rules):
    result = workspace.model_copy(deep=True)
    project = assemble_agent_import(result, draft)
    result.project, result.pre_draft = project, None
    result.project_revision, result.document_revision = project.revision, project.document.revision
    result.rules_used, result.source_observed_at = rules, None
    if not result.title_manually_set:
        result.title = draft.profile.name or result.title
    result.warnings = [w for w in result.warnings if w.code != "source_details_unresolved"]
    result.warnings.extend(w for w in source_warnings(project.sources) if w.code not in {old.code for old in result.warnings})
    if project.facts.extraction.status == "partial":
        result.warnings.append(RichWarning(id="warning_" + checksum(draft)[:24], code="source_details_unresolved",
            blockIds=[], recordIds=[], evidence=[]))
    return result
