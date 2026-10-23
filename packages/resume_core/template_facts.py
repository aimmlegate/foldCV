"""Human authority and relation-aware edits over generic semantic records."""

from __future__ import annotations

import uuid

from .models.rich_facts import RecordTombstone
from .models.template_facts import EffectiveExtensionValue, ManualEditScope, Relation, WorkingFactsV2


def extension_record(facts,record_id,*,active=True):
    return next((r for r in facts.extensions if r.id==record_id and (r.active or not active)),None)


def extension_cell(record,field_key):
    return next((c for c in record.cells if c.field_key==field_key),None) if record else None


def revise_cell(record,cell):
    record.revision=max(record.revision,cell.revision)+1
    cell.revision=record.revision


def set_human_cell(record,field_key,text):
    cell=extension_cell(record,field_key)
    if cell is None: raise ValueError('extension cell missing')
    cell.raw_input=text;cell.typed_value=None;cell.state='human_raw';cell.origin='human'
    cell.user_corrected=True;cell.manual_scope_id=None
    revise_cell(record,cell)
    return cell


def human_edit(facts: WorkingFactsV2,record_id,field_key,text):
    result=facts.model_copy(deep=True)
    record=extension_record(result,record_id)
    if record is None: raise ValueError('extension record missing')
    set_human_cell(record,field_key,text)
    result.revision+=1
    return WorkingFactsV2.model_validate(result.model_dump(by_alias=True))


def ambiguous_edit(facts: WorkingFactsV2,cell_ids,text,action_id,block_ids,*,scope_id=None):
    result=facts.model_copy(deep=True);targets=set(cell_ids)
    found={c.id:(r,c) for r in result.extensions if r.active for c in r.cells if c.id in targets}
    if set(found)!=targets or not targets: raise ValueError('ambiguous edit references missing cells')
    scope=ManualEditScope(id=scope_id or 'manual-'+uuid.uuid4().hex,actionId=action_id,rawInput=text,
        cellIds=list(cell_ids),blockIds=block_ids)
    result.manual_scopes.append(scope)
    for record,cell in found.values():
        cell.raw_input='';cell.typed_value=None;cell.state='pending_manual';cell.origin='human'
        cell.user_corrected=True;cell.manual_scope_id=scope.id;revise_cell(record,cell)
    result.revision+=1
    return WorkingFactsV2.model_validate(result.model_dump(by_alias=True))


def effective_extension_values(facts, record_ids=None):
    scopes = {scope.id: scope for scope in facts.manual_scopes}
    selected = set(record_ids) if record_ids is not None else None
    result = []
    for record in facts.extensions:
        if not record.active or selected is not None and record.id not in selected:
            continue
        for cell in record.cells:
            if cell.state == 'uncertain':
                continue
            result.append(EffectiveExtensionValue(recordId=record.id, semanticType=record.semantic_type,
                cell=cell.model_copy(deep=True), manualScope=scopes[cell.manual_scope_id].model_copy(deep=True)
                if cell.manual_scope_id is not None else None))
    return result


def replace_effective_relation(facts,relation):
    for index,current in enumerate(facts.relations):
        if current.id==relation.id:
            facts.relations[index]=relation
            break
    else: raise ValueError('effective relation missing')
    record=extension_record(facts,relation.subject_id,active=False)
    if record:
        record.relations=[relation if r.id==relation.id else r for r in record.relations]
        record.revision+=1


def move_owned(facts: WorkingFactsV2,record_id,new_owner,*,supported_owner_ids):
    result=facts.model_copy(deep=True)
    if new_owner not in set(supported_owner_ids): return result
    if new_owner not in {r.id for r in result.records}|{r.id for r in result.extensions if r.active}:
        raise ValueError('destination owner missing')
    builtin=next((r for r in result.records if r.id==record_id),None)
    owner=next((r for r in result.records if r.id==new_owner),None)
    relations=[r for r in result.relations if r.active and r.subject_id==record_id and r.kind=='owned_by']
    if not relations and builtin is not None and hasattr(builtin,'job_id'):
        relation=Relation(id='relation-'+uuid.uuid4().hex,kind='owned_by',subjectId=record_id,
            targetId=getattr(builtin,'subproject_id',None) or builtin.job_id or new_owner,revision=1,active=True)
        result.relations.append(relation);relations=[relation]
    if builtin is not None and owner is not None and hasattr(builtin,'job_id'):
        if owner.kind=='employment':
            builtin.job_id=owner.id
            if hasattr(builtin,'subproject_id'): builtin.subproject_id=None
        elif owner.kind=='subproject' and hasattr(builtin,'subproject_id'):
            builtin.job_id=owner.job_id;builtin.subproject_id=owner.id
        else: return facts.model_copy(deep=True)
        builtin.revision+=1
    if len(relations)>1: raise ValueError('ambiguous effective owner')
    for relation in relations:
        updated=relation.model_copy(deep=True);updated.target_id=new_owner;updated.revision+=1
        replace_effective_relation(result,updated)
    if relations: result.revision+=1
    return WorkingFactsV2.model_validate(result.model_dump(by_alias=True))


def delete_subject(facts: WorkingFactsV2,record_id,action_id,*,order=None):
    result=facts.model_copy(deep=True)
    current={r.id for r in result.records}|{r.id for r in result.extensions if r.active}
    if record_id not in current: raise ValueError('fact deletion target missing')
    removed={record_id}
    while True:
        descendants={r.subject_id for r in result.relations if r.active and r.target_id in removed and r.kind in {'owned_by','extension_of'}}
        descendants.update(r.id for r in result.records if getattr(r,'job_id',None) in removed or getattr(r,'subproject_id',None) in removed)
        extra=descendants-removed
        if not extra: break
        removed.update(extra)
    if order is None:
        order={r.id:i for i,r in enumerate([*result.records,*result.extensions])}
    revisions={r.id:r.revision for r in [*result.records,*result.extensions]}
    result.records=[r for r in result.records if r.id not in removed]
    if result.builtin_manual_scopes:
        from .rich_fields import builtin_cell_values
        remaining = builtin_cell_values(result.records)
        result.builtin_manual_scopes = {cell: scope for cell, scope in result.builtin_manual_scopes.items() if cell in remaining}
    for record in result.extensions:
        if record.id in removed: record.active=False;record.revision+=1
    for identifier in removed:
        result.tombstones.append(RecordTombstone(recordId=identifier,revision=revisions[identifier]+1,
            actionId=action_id,orderIndex=order[identifier]))
    for relation in list(result.relations):
        if relation.active and (relation.subject_id in removed or relation.target_id in removed):
            updated=relation.model_copy(deep=True);updated.active=False;updated.revision+=1
            replace_effective_relation(result,updated)
    result.revision+=1
    return WorkingFactsV2.model_validate(result.model_dump(by_alias=True))
