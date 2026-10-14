"""Explicit read-only legacy history and content context."""

from .gui_normalization import public_context_facts
from .gui_migration import history
from .models.recovery import SourceContext


def public_workspace_facts(workspace):
    owner=workspace.project or workspace.pre_draft
    return public_context_facts(owner.facts)


def migration_context(workspace):
    items=[]
    if workspace.legacy_data:
        items.extend(workspace.legacy_data.unmapped_text)
        for block in workspace.legacy_data.blocks:
            items.append(history('legacy_'+block.kind,block.id,block.state.text,block.state.fact_ids,block.visible,label=block.kind))
            if block.previous:items.append(history('legacy_previous_'+block.kind,block.id,block.previous.text,block.previous.fact_ids,block.visible,label='Previous '+block.kind))
        for proposal in workspace.legacy_data.proposals:
            items.append(history('unapplied_proposal',proposal.id,proposal.replacement_text,proposal.evidence_fact_ids,label='Unapplied proposal'))
    return SourceContext(projectId=workspace.project_id,documentRevision=workspace.document_revision,status='no-evidence',excerpts=[],annotations=[],legacyText=items)
