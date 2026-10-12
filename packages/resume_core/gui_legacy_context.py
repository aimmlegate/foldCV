"""Explicit read-only migration history and private-fact scope filtering."""

from .gui_normalization import public_context_facts
from .gui_migration import history
from .models.recovery import SourceContext
from .privacy import private_output_text


def public_workspace_facts(workspace):
    owner=workspace.project or workspace.pre_draft
    private=set()
    if workspace.legacy_data:
        private.update(ref for block in workspace.legacy_data.blocks if block.kind=='contact' for ref in block.state.fact_ids)
        private.update(ref for item in workspace.legacy_data.unmapped_text if item.original_kind in {'contact','personal','meta'} for ref in item.fact_ids)
    return [fact for fact in public_context_facts(owner.facts) if fact.id not in private and not private_output_text(fact.model_dump_json(by_alias=True))]


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
