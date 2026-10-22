"""Clipboard authority depends on current cells and ownership, never source displays."""

from .models.template_clipboard import (ClipboardActiveCell,ClipboardFieldWitness,ClipboardOwnershipWitness,
    ClipboardRecordOwnership,ClipboardScopeWitness,ClipboardSourceWitness)
from .rich_fields import builtin_cell_values,field_key,working_field
from .template_identity import source_slice
from .template_scope_occurrences import active_scope_cells
from .templates.compiler import canonical,sha256


def fingerprint(value):
    return sha256(canonical(value))


def records(project):
    return {record.id:record for record in [*project.facts.records,*project.facts.extensions]
        if getattr(record,'active',True)}


def record_identity(project,identifier):
    record=records(project).get(identifier)
    if record is None:raise ValueError('clipboard record is missing or inactive')
    if hasattr(record,'semantic_type'):
        value={'id':record.id,'itemHandle':record.item_handle,'semanticType':record.semantic_type,
            'semanticSchemaHash':record.semantic_schema_hash,'active':record.active,
            'copyOfRecordId':record.copy_of_record_id}
    else:
        value={'id':record.id,'kind':record.kind,'active':True}
        identity=next((item for item in project.facts.builtin_identities if item.record_id==identifier),None)
        if identity is not None:
            value.update(itemHandle=identity.item_handle,semanticType=identity.semantic_type,
                semanticSchemaHash=identity.semantic_schema_hash)
    return fingerprint(value)


def builtin_owner(record):
    if not hasattr(record,'job_id') and not hasattr(record,'subproject_id'):return None
    return {'jobId':getattr(record,'job_id',None),'subprojectId':getattr(record,'subproject_id',None)}


def ownership_witness(project,identifier):
    type(project.facts).model_validate(project.facts.model_dump(mode='json',by_alias=True))
    current=records(project)
    if identifier not in current:raise ValueError('clipboard ownership subject is missing')
    edges={}
    for relation in project.facts.relations:
        if relation.active and relation.kind in {'owned_by','extension_of'}:
            edges.setdefault(relation.subject_id,[]).append(relation)
    relations,ancestors,visited={}, {},set()
    def visit(record_id,path):
        if record_id in path:raise ValueError('clipboard ownership cycle')
        if record_id not in current:raise ValueError('clipboard ownership target is missing')
        if record_id in visited:return
        record=current[record_id];owner=builtin_owner(record)
        if record_id!=identifier:
            ancestors[record_id]={'recordId':record_id,'recordIdentityHash':record_identity(project,record_id),
                'builtinOwner':owner}
        parents={value for value in (owner or {}).values() if value is not None}
        for relation in edges.get(record_id,[]):
            relations[relation.id]={'relationId':relation.id,'relationHash':fingerprint(relation)}
            parents.add(relation.target_id)
        for parent in sorted(parents):visit(parent,path|{record_id})
        visited.add(record_id)
    visit(identifier,set())
    return ClipboardOwnershipWitness(builtinOwner=builtin_owner(current[identifier]),
        relations=[relations[key] for key in sorted(relations)],ancestors=[ancestors[key] for key in sorted(ancestors)])


def field_witness(project,record_id,key,cell_id=None):
    record=records(project).get(record_id)
    if record is None:raise ValueError('clipboard field record is missing')
    cell=working_field(record,key)
    if cell is None:raise ValueError('clipboard field is missing')
    if hasattr(record,'semantic_type'):
        identifier=cell.id;effective=cell.model_dump(mode='json',by_alias=True)
    else:
        identifier=field_key(record_id,key)
        if identifier not in builtin_cell_values(project.facts.records):
            raise ValueError('clipboard field has no canonical builtin cell')
        effective={'cell':cell.model_dump(mode='json',by_alias=True),
            'manualScopeId':project.facts.builtin_manual_scopes.get(identifier)}
    if cell_id is not None and cell_id!=identifier:raise ValueError('clipboard canonical cell identity differs')
    return ClipboardFieldWitness(kind='field',recordId=record_id,recordIdentityHash=record_identity(project,record_id),
        cellId=identifier,fieldKey=key,effectiveCellHash=fingerprint(effective),ownership=ownership_witness(project,record_id))


def scope_witness(project,scope_id):
    scope=next((value for value in project.facts.manual_scopes if value.id==scope_id),None)
    active=active_scope_cells(project.facts).get(scope_id,set())
    if scope is None or not active:raise ValueError('clipboard scope is no longer active')
    indexed={identifier:(record.id,key) for identifier,(record,key,_value) in builtin_cell_values(project.facts.records).items()}
    indexed.update({cell.id:(record.id,cell.field_key) for record in project.facts.extensions if record.active for cell in record.cells})
    cells=[];owners={}
    for identifier in sorted(active):
        if identifier not in indexed:raise ValueError('clipboard scope cell is missing')
        record_id,key=indexed[identifier];field=field_witness(project,record_id,key,identifier)
        cells.append(ClipboardActiveCell(recordId=record_id,recordIdentityHash=field.record_identity_hash,
            cellId=identifier,fieldKey=key,
            effectiveCellHash=field.effective_cell_hash))
        owners[record_id]=ClipboardRecordOwnership(recordId=record_id,ownership=field.ownership)
    return ClipboardScopeWitness(kind='scope',scopeId=scope_id,scopeHash=fingerprint(scope),
        activeCells=cells,ownerships=[owners[key] for key in sorted(owners)])


def source_witness(project,span):
    source_slice(project.sources,span)
    return ClipboardSourceWitness(kind='source_span',span=span.model_copy(deep=True),spanHash=fingerprint(span))


def verify_witness(project,witness):
    if witness.kind=='field':
        current=field_witness(project,witness.record_id,witness.field_key,witness.cell_id)
    elif witness.kind=='scope':current=scope_witness(project,witness.scope_id)
    else:current=source_witness(project,witness.span)
    if current!=witness:raise ValueError('clipboard captured authority changed')


def verify_witnesses(project,witnesses,package_fingerprint):
    from .templates.store import verify_package
    if fingerprint(project.template_package)!=package_fingerprint:
        raise ValueError('clipboard captured package changed')
    verify_package(project.template_package)
    for witness in witnesses:verify_witness(project,witness)
