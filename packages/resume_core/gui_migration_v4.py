"""Validate old workspace envelopes and retain uncommitted input as history."""

import re
from .archive_zip import ArchiveFailure,digest,parse_json,json_bytes
from .gui_migration import empty_workspace,migrate_v3,history
from .gui_normalization import canonical_source,source_fingerprint
from .extraction.models import ExtractResult
from .models.recovery import LegacyData
from .dates import partial_date
from . import gui_legacy_validation as validation

ROOT_KEYS={'schemaVersion','editor','importState','importOriginals','facts','manualForm','assertionDraft','factEdits','rewriteInstruction','preEditorSourceText','renderBinding','legacy'}
EDITOR_REQUIRED={'working','presentation','presentationDrafts','presentationUndo','stage','panel','selectedId','drafts','factDrafts','structuredDrafts','errors','undo','rewriteProposal','rewriteIssues','rewriteIssueDetails','workingIssues','sourceText','dirty'}
EDITOR_OPTIONAL={'standaloneAcknowledgments','standaloneDecisions'}
CREDENTIAL=re.compile(r'^(secret|password|token|api[_-]?key|authorization|cookie|credential|session|home|cwd|workspace|config[_-]?path)$',re.I)


def private_keys(value):
    if isinstance(value,list):return any(private_keys(item) for item in value)
    if isinstance(value,dict):return any(CREDENTIAL.fullmatch(key) or private_keys(item) for key,item in value.items())
    return False


def exact(value,keys):return isinstance(value,dict) and set(value)==set(keys)

def strings(value):return isinstance(value,dict) and all(isinstance(key,str) and isinstance(item,str) for key,item in value.items())


def validate_envelope(raw,project):
    if not exact(raw,ROOT_KEYS) or raw['schemaVersion']!=4 or private_keys(raw):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    if not strings(raw['importOriginals']) or not strings(raw['factEdits']) or any(not isinstance(raw[key],str) for key in ['assertionDraft','rewriteInstruction','preEditorSourceText']):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    if raw['renderBinding'] is not None and (not isinstance(raw['renderBinding'],str) or not re.fullmatch('[a-f0-9]{64}',raw['renderBinding'])):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    imported=raw['importState']
    if not exact(imported,{'entries','selectedId','pending','error'}) or not isinstance(imported['entries'],list) or len(imported['entries'])>10 or imported['pending'] is not False or imported['error'] is not None:raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    if imported['selectedId'] is not None and not any(isinstance(entry,dict) and isinstance(entry.get('result'),dict) and entry['result'].get('sourceId')==imported['selectedId'] for entry in imported['entries']):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    validation.require(len({entry.get('result',{}).get('sourceId') for entry in imported['entries'] if isinstance(entry,dict)})==len(imported['entries']))
    fact=raw['facts']
    if not exact(fact,{'view','assertions','corrections'}) or not strings(fact['corrections']) or not isinstance(fact['assertions'],list) or not exact(fact['view'],{'sheet','pending','stale','error'}):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    if fact['view']['pending'] is not False or fact['view']['error'] is not None or type(fact['view']['stale']) is not bool:raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    if fact['view']['sheet'] is not None:
        from .normalization import FactSheet
        sheet=FactSheet.model_validate(fact['view']['sheet'])
        by_id={value.id:value.model_dump(mode='json',by_alias=True) for value in sheet.facts}
        if any(not isinstance(value,dict) or value.get('origin')!='user' or value.get('kind')!='text' or by_id.get(value.get('id'))!=value for value in fact['assertions']) or any(sheet.user_corrections.get(source)!=user for source,user in fact['corrections'].items()):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    elif fact['assertions'] or fact['corrections']:raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    manual=raw['manualForm']
    validation.manual(manual)
    if not exact(manual,{'name','title','asOf','education','language','languages','skills','employment','metrics','leadership'}) or any(not isinstance(manual[key],str) for key in ['name','title','asOf','education']) or manual['language'] not in {'ru','en','mixed'} or any(not isinstance(manual[key],list) for key in ['languages','skills','employment','metrics','leadership']):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    editor=raw['editor']
    if (project is None)!=(editor is None):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    if editor is not None:
        if not isinstance(editor,dict) or not EDITOR_REQUIRED<=editor.keys() or not editor.keys()<=EDITOR_REQUIRED|EDITOR_OPTIONAL or editor['stage'] not in {'import','editor','export'} or editor['panel'] not in {'preview','sources','checks'} or type(editor['dirty']) is not bool or editor['sourceText']!=raw['preEditorSourceText']:raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
        if any(not strings(editor[key]) for key in ['drafts','factDrafts','structuredDrafts','errors']):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
        if not isinstance(editor['undo'],dict) or not isinstance(editor['workingIssues'],list):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
        block_ids={block.id for block in project.views};fact_ids={fact.id for fact in project.facts}
        if editor['selectedId'] is not None and editor['selectedId'] not in block_ids or not set(editor['drafts'])<=block_ids or not set(editor['undo'])<=block_ids or not set(editor['factDrafts'])<=fact_ids:raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
        for block_id,cp in editor['undo'].items():
            from .models.contracts import BlockState
            if not isinstance(cp,dict) or 'state' not in cp or type(cp.get('revision')) is not int:raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
            state=BlockState.model_validate(cp['state'])
            if not set(state.fact_ids)<=fact_ids or cp['revision']>next(block.revision for block in project.views if block.id==block_id):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
        validation.editor_details(editor,project)


def migrate_v4_workspace(raw,project,manifest,entries,files,id,clock):
    from .gui_archive import original_bytes
    validate_envelope(raw,project)
    if project and ((project.template.package_sha256 if project.template else None)!=manifest.template_package_sha256 or ('1.0.0' if project.template else None)!=manifest.renderer_version):raise ArchiveFailure('ARCHIVE_TEMPLATE_INVALID')
    render_paths={entry.path for entry in entries.values() if entry.role=='render'}
    if render_paths:
        from .rendering.models import RenderRequest
        if project is None or raw['editor']['presentation'] is None or render_paths!={'renders/preview.pdf','renders/resume.docx','renders/request.json'}:raise ArchiveFailure('ARCHIVE_RENDER_INVALID')
        request=RenderRequest.model_validate(parse_json(files['renders/request.json']))
        presentation=raw['editor']['presentation'];binding=digest(json_bytes({'project':parse_json(files['project.json']),'presentation':presentation}))
        if raw['renderBinding']!=binding or request.base_revision!=project.revision or request.document.candidate.name!=presentation['name'] or request.document.candidate.title!=presentation['title'] or request.snapshot.template_package_sha256!=manifest.template_package_sha256 or not files['renders/preview.pdf'].startswith(b'%PDF') or not files['renders/resume.docx'].startswith(b'PK'):raise ArchiveFailure('ARCHIVE_RENDER_INVALID')
    elif raw['renderBinding'] is not None:raise ArchiveFailure('ARCHIVE_RENDER_INVALID')
    referenced={source.byte_ref for source in project.sources} if project else set()
    originals=original_bytes(project,entries,files) if project else {}
    extra_sources=[];ids=set()
    selected=None
    def imported(entry,ref):
        nonlocal selected
        if not exact(entry,{'result','overlays'}):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
        result=validation.imported(entry);content=files.get(ref)
        if ref not in entries or entries[ref].role!='source_original' or content is None or len(content)!=result.byte_length or digest(content)!=result.byte_sha256 or not strings(entry['overlays']):raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
        source=canonical_source(result,source_id=result.source_id);source.byte_ref=ref
        referenced.add(ref)
        if source.id in originals and originals[source.id]!=content:raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
        originals[source.id]=content
        if source.id not in ids:extra_sources.append(source);ids.add(source.id)
        if result.source_id==raw['importState']['selectedId']:selected=source
    for entry in raw['importState']['entries']:
        result=entry.get('result') if isinstance(entry,dict) else None
        ref=raw['importOriginals'].get(result.get('sourceId')) if isinstance(result,dict) else None
        imported(entry,ref)
    if set(raw['importOriginals'])!={entry['result']['sourceId'] for entry in raw['importState']['entries']}:raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
    working=raw['editor'].get('working') if raw['editor'] else None
    if working is not None:
        if not isinstance(working,dict) or not isinstance(working.get('sources'),list):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
        for value in working['sources']:
            if not exact(value,{'entry','originalRef'}):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
            imported(value['entry'],value['originalRef'])
    legacy=raw['legacy']
    if legacy is not None:
        from .gui_migration_v2 import checked_v2
        if not exact(legacy,{'format','archive','originalRef','originalName','originalSha256','view'}) or legacy['format']!='v2':raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
        archive=legacy['archive'];checked_v2(archive,legacy['view'])
        ref=legacy['originalRef'];content=files.get(ref)
        if ref not in entries or entries[ref].role!='source_original' or content is None or digest(content)!=legacy['originalSha256'] or legacy['originalSha256']!=archive['source']['sha256']:raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
        referenced.add(ref)
        from .gui_migration_v2 import legacy_source
        source,_facts,_jobs=legacy_source(archive,content,ref)
        if not any(digest(value)==digest(content) for value in originals.values()):
            for unit in source.units:
                unit.id=source.id+'_'+unit.id;unit.represented_fact_ids=[]
            extra_sources.append(source);originals[source.id]=content
    if referenced!={entry.path for entry in entries.values() if entry.role=='source_original'}:raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
    if project:
        workspace=migrate_v3(project,id,clock,raw['editor']['presentation'],raw)
        current_ids={source.id for source in workspace.project.sources}
        for source in extra_sources:
            if source.id not in current_ids:
                source.byte_ref='sources/'+digest(source.id.encode())+'/original'
                workspace.project.sources.append(source)
        # Unsubmitted forms remain readable text; accepted project content has precedence.
        if raw['manualForm']['education']:
            workspace.legacy_data.unmapped_text.append(history('unapplied_education','manual',raw['manualForm']['education']))
        for key,text in raw['editor']['presentationDrafts'].items():
            if isinstance(text,str) and text:workspace.legacy_data.unmapped_text.append(history('unapplied_presentation',key,text))
    else:
        workspace=empty_workspace(id,'Новое резюме',partial_date(clock.date().isoformat()),clock.isoformat())
        workspace.migration_notices=['portable_project_imported','legacy_workspace_imported']
        workspace.pre_draft.sources=extra_sources;workspace.pre_draft.selected_source_id=selected.id if selected else None
        workspace.pre_draft.extracted_text=''.join(unit.text for unit in selected.units) if selected else ''
        workspace.pre_draft.extraction_fingerprint=source_fingerprint([selected]) if selected else None
        workspace.legacy_data=LegacyData(blocks=[],proposals=[],review=None,renders=[],unmappedText=[history('unapplied_input','input',raw['preEditorSourceText'])] if raw['preEditorSourceText'] else [])
    # Keep unsent forms readable without giving them precedence over accepted content.
    def retain(value,path):
        if isinstance(value,str) and value:workspace.legacy_data.unmapped_text.append(history('unapplied_form',path,value,label=path))
        elif isinstance(value,list):
            for index,item in enumerate(value):retain(item,path+'/'+str(index))
        elif isinstance(value,dict):
            for key,item in value.items():
                if key not in {'id','jobId','language','sources','evidence','coverage','archive_sha256','schema_version','template'}:retain(item,path+'/'+key)
    for key in ['manualForm','assertionDraft','factEdits']:retain(raw[key],key)
    if raw['editor']:
        for key in ['factDrafts','structuredDrafts']:retain(raw['editor'][key],key)
        if raw['editor']['rewriteProposal']:retain(raw['editor']['rewriteProposal']['result']['replacementText'],'unapplied_rewrite')
    for entry in raw['importState']['entries']:retain(entry['overlays'],'unapplied_overlay/'+entry['result']['sourceId'])
    if legacy and legacy['view']:retain(legacy['view'],'legacy_selected_view')
    if any(item.original_kind.startswith('unapplied') for item in workspace.legacy_data.unmapped_text):workspace.migration_notices.append('legacy_unapplied_text')
    return workspace,originals
