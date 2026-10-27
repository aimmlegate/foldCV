"""Explicit legacy document mapping; no prose parsing or model work."""

from datetime import datetime
import hashlib
from pydantic import Field

from .dates import partial_date
from .archive_zip import ArchiveFailure
from .gui_drafting import _field, _record
from .gui_mutations import checkpoint
from .gui_projection import compatibility_views
from .gui_refresh import refresh, validate_focus
from .gui_selection import normalized_text
from .models.contracts import Wire
from .models.recovery import (WorkspaceV5, ProjectV4, Document, GuiOperation, Rules,
    LegacyData, LegacyText, LegacyRender, FactStamp, record_slot, authored_fields)


class LegacyPresentation(Wire):
    name: str
    title: str
    source_language: str
    job_prose_blocks: dict[str,str]
    languages: list[str] = Field(default_factory=list)


def stable(kind,key):return 'legacy-'+kind+'-'+hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]


def empty_workspace(id,title,formatting,created,revision=1,document_revision=1):
    return WorkspaceV5.model_validate({'schemaVersion':5,'projectId':id,'projectRevision':revision,'documentRevision':document_revision,
        'title':title,'titleManuallySet':False,'createdAt':created,'updatedAt':created,'project':None,
        'preDraft':{'sources':[],'facts':[],'operations':[],'renders':[],'selectedInput':'file','selectedSourceId':None,
            'extractedText':'','warnings':[],'extractionFingerprint':None},
        'formattingAsOf':formatting.model_dump(by_alias=True),'sourceObservedAt':None,'rulesUsed':None,'editorialPlan':None,
        'annotations':[],'relatedUpdateSuggestions':[],'derivedState':None,'undoSlots':{},'editSessions':{},'mutationReplay':[],
        'generations':[],'sourceExclusions':[],'migrationNotices':[],'legacyData':None})


def formatting_date(project,clock,notices):
    if project.as_of:return project.as_of.model_copy(deep=True)
    try:return partial_date(datetime.fromisoformat(project.created_at.replace('Z','+00:00')).date().isoformat())
    except ValueError:
        notices.append('legacy_formatting_date_unavailable')
        return partial_date(clock.date().isoformat())


def blank_document():
    return {'candidate':_record('candidate','candidate',name=_field('candidate/name'),title=_field('candidate/title'),location=_field('candidate/location')),
        'profile':_record('profile','profile',text=_field('profile/text')),'jobs':[],'education':[],'certifications':[],'languages':[],
        'skillsFocus':_record('skills-focus','skills-focus',skillsText=_field('skills-focus/skillsText'),focusFieldId='skills-focus/focus',focus=[]),
        'earlyCareer':_record('early-career','early-career',text=_field('early-career/text'),representedJobIds=[])}


def field(id,text='',refs=(),origin='migration'):
    value=_field(id,normalized_text(text),list(dict.fromkeys(refs)));value['origin']=origin;return value


def date_text(value):
    if value is None:return ''
    return f'{value.year:04}' + (f'-{value.month:02}' if value.month is not None else '') + (f'-{value.day:02}' if value.day is not None else '')


def job_record(job,context='',refs=(),visible=True,origin='migration'):
    slot='job:'+job.id
    periods=[]
    for index,period in enumerate(job.periods):
        id=stable('period',job.id+':'+str(index));prefix=slot+'/period:'+id
        periods.append({'id':id,'startText':field(prefix+'/startText',date_text(period.start),job.fact_ids),
            'endText':field(prefix+'/endText',date_text(period.end),job.fact_ids),'present':period.end is None})
    result=_record('job',job.id,employer=field(slot+'/employer',job.employer,job.fact_ids),role=field(slot+'/role',job.role,job.fact_ids),
        periodsFieldId=slot+'/periods',periods=periods,context=field(slot+'/context',context,refs,origin),tasks=field(slot+'/tasks'),
        results=field(slot+'/results'),stack=field(slot+'/stack'),subprojectIds=[sub.id for sub in job.subprojects])
    result['visible']=visible;return result


def legacy_row(kind,id,text,refs=(),visible=True):
    slot=kind+':'+id
    names={'education':['institution','qualification','specialty','dateText'],'certification':['name','issuer','dateText'],'language':['name','proficiency']}[kind]
    value=_record(kind,id,**{name:field(slot+'/'+name) for name in names},legacyText=field(slot+'/legacyText',text,refs))
    value['visible']=visible;return value


def history(kind,key,text,refs=(),visible=True,label=None,evidence=()):
    return LegacyText(id=stable('text',kind+':'+key),originalKind=kind,label=label or kind,text=text,visible=visible,
        factIds=list(dict.fromkeys(refs)),evidence=list(evidence))


def migration_plan(workspace,language='mixed'):
    document=workspace.project.document
    early=set(document.early_career.represented_job_ids)
    return {'origin':'migration','revision':1,'rulesRevision':None,'formattingAsOf':workspace.formatting_as_of.model_dump(by_alias=True),
        'sourceLanguage':language,'profileLanguage':None,
        'jobs':[{'jobId':job.id,'disposition':'early-career' if job.id in early else 'detailed','factIds':job.fact_ids} for job in workspace.project.employment],
        'focus':[{'catalogId':entry.catalog_id,'display':entry.display.text,'factIds':entry.fact_ids} for entry in document.skills_focus.focus],
        'technologyGroups':[],'factIds':[fact.id for fact in workspace.project.facts if fact.job_id is not None]}


def finish_document(workspace,document,jobs,facts,sources,operations,legacy,language):
    workspace.project=ProjectV4(schemaVersion=4,projectId=workspace.project_id,revision=workspace.project_revision,
        asOf=workspace.source_observed_at,createdAt=workspace.created_at,document=Document.model_validate(document),employment=jobs,
        views=[],template=None,review={'decisions':[],'acknowledgments':[]},proposals=[],sources=sources,facts=facts,operations=operations,renders=[])
    workspace.pre_draft=None;workspace.legacy_data=legacy
    workspace.undo_slots={record_slot(record):None for record in workspace.project.document.records()}
    from .models.recovery import EditorialPlan,SourceExclusion
    workspace.editorial_plan=EditorialPlan.model_validate(migration_plan(workspace,language))
    for record in workspace.project.document.records():
        if not record.visible and record.kind!='candidate':
            ids={ref for value in authored_fields(record) for ref in value.fact_ids}
            workspace.source_exclusions.append(SourceExclusion(id=stable('exclusion',record_slot(record)),recordId=record_slot(record),
                sourceIds=list({ref.source_id for fact in facts if fact.id in ids for ref in fact.evidence}),factIds=sorted(ids),reason='hidden',revision=workspace.document_revision))
    removed=validate_focus(workspace)
    workspace.project.views=compatibility_views(workspace.project.document,workspace.project.facts)
    refresh(workspace,[],removed)
    return workspace


def migrate_v3(project,id,clock,presentation=None,raw_workspace=None):
    notices=['portable_project_imported','legacy_project_imported','imported_locks_ignored']
    formatting=formatting_date(project,clock,notices)
    workspace=empty_workspace(id,project.sources[0].original_name if project.sources else 'Новое резюме',formatting,project.created_at or clock.isoformat(),project.revision,project.revision)
    workspace.migration_notices=notices
    doc=blank_document();text_history=[]
    facts={fact.id:fact for fact in project.facts};views=[block.model_copy(deep=True) for block in project.views]
    excluded_blocks={item.target_id for item in project.review.decisions if item.target_kind=='block' and item.disposition=='excluded' and any(block.id==item.target_id and block.revision==item.target_revision for block in views)}
    for block in views:
        if block.id in excluded_blocks:block.visible=False
    language='mixed';bindings={}
    if presentation is not None:
        presentation=LegacyPresentation.model_validate(presentation)
        if presentation.source_language not in {'ru','en','mixed'}:raise ArchiveFailure('ARCHIVE_INVALID_PRESENTATION')
        language=presentation.source_language;bindings=presentation.job_prose_blocks
        if set(bindings)!={job.id for job in project.employment} or len(set(bindings.values()))!=len(bindings) or any(
            not any(block.id==block_id and block.kind=='job_prose' for block in views) for block_id in bindings.values()):raise ArchiveFailure('ARCHIVE_INVALID_PRESENTATION')
        doc['candidate']['name']=field('candidate/name',presentation.name)
        doc['candidate']['title']=field('candidate/title',presentation.title)
        for index,text in enumerate(presentation.languages):
            doc['languages'].append(legacy_row('language',stable('language',str(index)+':'+text),text))
    else:notices.append('legacy_language_unknown')
    origin=lambda state:{'manual':'user','generated':'generated','source':'source'}[state.origin]
    def singleton(kind,target,name):
        blocks=[block for block in views if block.kind in kind]
        included=blocks if len(blocks)==1 else [block for block in blocks if block.visible]
        value=field(target+'/'+name,'\n\n'.join(block.state.text for block in included),[ref for block in included for ref in block.state.fact_ids],
            origin(included[0].state) if len(included)==1 else 'migration')
        record=doc['skillsFocus' if target=='skills-focus' else 'earlyCareer' if target=='early-career' else target]
        record[name]=value
        if len(blocks)==1:record['revision']=blocks[0].revision
        record['visible']=blocks[0].visible if len(blocks)==1 else bool(included) if blocks else True
        if len(blocks)>1:
            notices.append('legacy_merged_blocks')
            for block in blocks:
                if not block.visible:text_history.append(history(block.kind,block.id,block.state.text,block.state.fact_ids,False))
        return included
    profiles=singleton({'profile'},'profile','text')
    singleton({'skills','focus'},'skills-focus','skillsText')
    if any(block.kind=='focus' for block in views):notices.append('legacy_focus_to_text')
    early=singleton({'early_career'},'early-career','text')
    early_ids={facts[ref].job_id for block in early for ref in block.state.fact_ids if facts[ref].job_id is not None}
    doc['earlyCareer']['representedJobIds']=[job.id for job in project.employment if job.id in early_ids]
    bound=set()
    if not bindings:
        candidates={}
        for block in views:
            if block.kind=='job_prose':
                ids={facts[ref].job_id for ref in block.state.fact_ids if facts[ref].job_id is not None}
                if len(ids)==1:candidates.setdefault(next(iter(ids)),[]).append(block)
        bindings={job_id:blocks[0].id for job_id,blocks in candidates.items() if len(blocks)==1}
    for job in project.employment:
        if job.id in early_ids:continue
        block=next((block for block in views if block.id==bindings.get(job.id)),None)
        doc['jobs'].append(job_record(job,block.state.text if block else '',block.state.fact_ids if block else [],block.visible if block else True,origin(block.state) if block else 'migration'))
        if block:
            doc['jobs'][-1]['revision']=block.revision
            bound.add(block.id)
    for block in views:
        if block.kind=='education':
            row=legacy_row('education',block.id,block.state.text,block.state.fact_ids,block.visible);row['revision']=block.revision;doc['education'].append(row)
        elif block.kind=='contact':text_history.append(history('contact',block.id,block.state.text,block.state.fact_ids,block.visible))
        elif block.kind=='job_prose' and block.id not in bound:
            text_history.append(history('unmapped_job_prose',block.id,block.state.text,block.state.fact_ids,block.visible));notices.append('legacy_ambiguous_job_prose')
        if block.kind=='job_prose' and block.previous:notices.append('legacy_job_undo_history_only')
    if raw_workspace and raw_workspace.get('editor'):
        for block_id,text in raw_workspace['editor'].get('drafts',{}).items():
            if text:text_history.append(history('unapplied_draft',block_id,text));notices.append('legacy_unapplied_text')
    operations=[]
    for operation in project.operations:
        raw=operation.model_dump(by_alias=True);raw['projectId']=id
        operations.append(GuiOperation.model_validate(raw))
    historical_rules=next((operation.rules_used for operation in reversed(operations) if operation.rules_used),None)
    workspace.rules_used=historical_rules
    legacy=LegacyData(blocks=project.views,proposals=project.proposals,review=project.review,
        renders=[LegacyRender(record=record,artifactAvailable=False) for record in project.renders],unmappedText=text_history)
    sources=[source.model_copy(deep=True) for source in project.sources]
    for source in sources:source.byte_ref='sources/'+stable('source',source.id)+'/original'
    workspace=finish_document(workspace,doc,project.employment,project.facts,sources,operations,legacy,language)
    from .models.recovery import SourceExclusion
    for item in project.review.decisions:
        if item.disposition!='excluded' or item.target_kind=='block':continue
        refs=[item.target_id] if item.target_kind=='fact' and facts[item.target_id].revision==item.target_revision else [fact.id for fact in project.facts if any(ref.unit_id==item.target_id and ref.unit_revision==item.target_revision for ref in fact.evidence)] if item.target_kind=='source_unit' else []
        if refs:workspace.source_exclusions.append(SourceExclusion(id=stable('exclusion',item.target_kind+':'+item.target_id),recordId=stable('legacy-exclusion',item.target_id),sourceIds=list(dict.fromkeys(ref.source_id for fid in refs for ref in facts[fid].evidence)),factIds=refs,reason='deleted',revision=workspace.document_revision))
    if len([block for block in views if block.kind=='profile'])==1 and profiles[0].previous:
        block=profiles[0];previous=block.previous;cp=checkpoint(workspace,'profile')
        cp.record.text.text=normalized_text(previous.text);cp.record.text.origin=origin(previous);cp.record.text.fact_ids=previous.fact_ids[:];cp.record.text.evidence=[]
        cp.record.revision=max(1,block.revision-1);cp.project_revision=max(1,workspace.project_revision-1);cp.document_revision=max(1,workspace.document_revision-1)
        cp.facts=[facts[ref].model_copy(deep=True) for ref in previous.fact_ids if facts[ref].revision==previous.fact_revisions[ref]]
        cp.fact_stamps=[FactStamp(factId=ref,revision=previous.fact_revisions[ref],ownerSlotId='profile',origin='model' if previous.origin=='generated' else origin(previous),authoritativeRevision=cp.document_revision) for ref in previous.fact_ids]
        if len(cp.facts)!=len(previous.fact_ids):notices.append('legacy_prior_fact_values_unavailable')
        workspace.undo_slots['profile']=cp
    elif any(block.kind=='profile' and block.previous for block in views):notices.append('legacy_profile_undo_history_only')
    if doc['candidate']['name']['text']:workspace.title=doc['candidate']['name']['text']
    workspace.migration_notices=list(dict.fromkeys(notices));return workspace
