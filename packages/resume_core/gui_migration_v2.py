"""Direct selected-view mapping for the preserved experimental v2 format."""

from .gui_archive_zip import ArchiveFailure,parse_json,digest,safe_path
from .gui_migration import (empty_workspace,blank_document,field,job_record,legacy_row,history,finish_document,stable,date_text)
from .dates import partial_date
from .models.contracts import Source,TextFact,TechnologyFact,Job
from .models.recovery import LegacyData
from .technologies import CATALOG,canonical_id


def exact(value,keys):return isinstance(value,dict) and set(value)==set(keys)


def checked_v2(archive,view=None):
    from .gui_migration_v4 import private_keys
    if not exact(archive,{'schema_version','as_of','source_snapshot','source','units','classifications','jobs','global_technologies'}) or archive['schema_version']!=2 or private_keys(archive):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
    partial_date(archive['as_of'])
    if not safe_path(archive['source_snapshot']) or '/' in archive['source_snapshot']:raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
    source=archive['source']
    if not exact(source,{'file','sha256','pages','warnings'}) or not isinstance(source['file'],str) or not isinstance(source['warnings'],list) or not all(isinstance(item,str) for item in source['warnings']) or not isinstance(source['pages'],list):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
    pages={}
    for page in source['pages']:
        if not exact(page,{'page','text'}) or type(page['page']) is not int or page['page']<1 or not isinstance(page['text'],str) or page['page'] in pages:raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
        pages[page['page']]=page['text']
    if not isinstance(archive['units'],list) or not isinstance(archive['jobs'],list) or not isinstance(archive['classifications'],dict) or not isinstance(archive['global_technologies'],list):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
    ids=set()
    for unit in archive['units']:
        if not exact(unit,{'id','page','text'}) or not isinstance(unit['id'],str) or not unit['id'] or unit['id'] in ids or type(unit['page']) is not int or unit['page'] not in pages or not isinstance(unit['text'],str) or unit['text'] not in pages[unit['page']]:raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
        ids.add(unit['id'])
    def cited(item):
        if not exact(item,{'text','sources'}) or not isinstance(item['text'],str) or not isinstance(item['sources'],list) or not all(isinstance(ref,str) and ref in ids for ref in item['sources']):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
    def tech(item):
        if not isinstance(item,dict) or not {'name','sources'}<=item.keys() or not item.keys()<={'name','sources','start','end','duration_eligible'} or not isinstance(item['name'],str):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
        cited({'text':item['name'],'sources':item['sources']})
        if 'start' in item and not isinstance(item['start'],str) or 'end' in item and item['end'] is not None and not isinstance(item['end'],str) or 'duration_eligible' in item and type(item['duration_eligible']) is not bool:raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
    job_ids=set()
    for job in archive['jobs']:
        required={'id','company','period','role','start','end','technologies'}
        if not isinstance(job,dict) or not required<=job.keys() or not job.keys()<=required|{'observed_at','observed_sources'} or not isinstance(job['id'],str) or not job['id'] or job['id'] in job_ids or not isinstance(job['technologies'],list):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
        for key in ['company','period','role']:cited(job[key])
        partial_date(job['start'])
        if job['end'] is not None:partial_date(job['end'])
        for item in job['technologies']:tech(item)
        if job.get('observed_at') is not None:partial_date(job['observed_at'])
        if 'observed_sources' in job and (not isinstance(job['observed_sources'],list) or not set(job['observed_sources'])<=ids):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
        job_ids.add(job['id'])
    for item in archive['global_technologies']:tech(item)
    categories={'identity','profile','job_header','period','role','task','result','stack','education','course','language','location','preferences','contacts','personal','meta'}
    for id,item in archive['classifications'].items():
        if id not in ids or not exact(item,{'category','importance','job_id'}) or item['category'] not in categories or item['importance'] not in {'essential','supporting','administrative'} or item['job_id'] is not None and item['job_id'] not in job_ids:raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
    if view is not None:
        if not isinstance(view,dict) or private_keys(view) or view.get('schema_version')!=2 or view.get('template')!='generic-v1' or not isinstance(view.get('candidate'),dict):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
        for key in ['name','title','summary']:cited(view['candidate'][key])
        for key in ['projects','earlier_experience','focus','sidebar','skill_groups']:
            if not isinstance(view.get(key),list):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
        selected=set();early=set()
        for job in view['projects']:
            if not isinstance(job,dict) or job.get('id') not in job_ids or job['id'] in selected:raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
            selected.add(job['id'])
            for key in ['company','period','role','stack','description']:
                if job.get(key) is not None:cited(job[key])
            for key in ['tasks','results']:
                if not isinstance(job.get(key),list):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
                for item in job[key]:cited(item)
        for item in view['earlier_experience']:
            if not isinstance(item,dict) or not isinstance(item.get('job_ids'),list) or not set(item['job_ids'])<=job_ids or early&set(item['job_ids']):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
            early.update(item['job_ids']);cited(item['summary'])
        if selected&early or selected|early!=job_ids or set(archive['classifications'])!=ids:raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
        for item in view['focus']:
            cited(item['label'])
            if item.get('duration') is not None:cited(item['duration'])
        for item in view['sidebar']:
            if not isinstance(item.get('title'),str) or not isinstance(item.get('items'),list):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
            for statement in item['items']:cited(statement)
        for item in view['skill_groups']:
            if not isinstance(item.get('title'),str):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
            cited(item['items'])
        for item in view.get('achievements',[]):cited(item)
        evidence={unit['id']:{'page':unit['page'],'quote':unit['text']} for unit in archive['units']}
        if 'evidence' in view and view['evidence']!=evidence or not isinstance(view.get('coverage'),dict) or set(view['coverage'])!=ids:raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
        for item in view['coverage'].values():
            if not isinstance(item,dict) or not {'decision'}<=item.keys() or not item.keys()<={'decision','reason'} or item['decision'] not in {'shown','condensed','archive_only','duplicate','metadata','excluded'} or 'reason' in item and not isinstance(item['reason'],str):raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
    return archive


def legacy_source(archive,content,ref=None):
    source_id='legacy_source_'+digest(content)[:24]
    facts=[];units=[]
    for index,unit in enumerate(archive['units']):
        id='legacy_unit_'+unit['id'];fid='legacy_fact_'+unit['id'];choice=archive['classifications'].get(unit['id'],{})
        units.append({'id':id,'revision':1,'order':index,'text':unit['text'],'location':{'kind':'page','index':unit['page']-1,'row':None,'column':None},'disposition':'unresolved','representedFactIds':[fid]})
        facts.append(TextFact(id=fid,revision=1,kind='text',value={'text':unit['text']},origin='source',importance={'essential':'essential','administrative':'minor'}.get(choice.get('importance'),'normal'),
            jobId=choice.get('job_id'),subprojectId=None,evidence=[{'sourceId':source_id,'sourceRevision':1,'unitId':id,'unitRevision':1}]))
    source=Source(id=source_id,revision=1,originalName=archive['source']['file'],mimeType='application/octet-stream',byteSha256=digest(content),byteRef='sources/'+source_id+'/original',parser='legacy-v2',parserVersion='2',units=units,overlays=[],warnings=archive['source']['warnings'])
    for job_id,technologies in [(job['id'],job['technologies']) for job in archive['jobs']]+[(None,archive['global_technologies'])]:
        for index,item in enumerate(technologies):
            catalog=canonical_id(item['name'])
            if catalog is None or item.get('duration_eligible',True) is False or not item['sources']:continue
            fid=stable('technology',str(job_id)+':'+str(index));refs=[{'sourceId':source_id,'sourceRevision':1,'unitId':'legacy_unit_'+key,'unitRevision':1} for key in item['sources']]
            facts.append(TechnologyFact(id=fid,revision=1,kind='technology',value={'canonicalId':catalog,'display':item['name'],'scope':'job' if job_id else 'global'},origin='source',importance='normal',jobId=job_id,subprojectId=None,evidence=refs))
            for unit in source.units:
                if unit.id in {ref['unitId'] for ref in refs}:unit.represented_fact_ids.append(fid)
    jobs=[Job(id=job['id'],employer=job['company']['text'],role=job['role']['text'],periods=[{'start':partial_date(job['start']).model_dump(by_alias=True),
        'end':partial_date(job['end']).model_dump(by_alias=True) if job['end'] is not None else None}],subprojects=[],factIds=[fact.id for fact in facts if fact.job_id==job['id']]) for job in archive['jobs']]
    return source,facts,jobs


def observation(archive,workspace,source,facts):
    from .models.recovery import ObservationFact
    candidates=[]
    for job in archive['jobs']:
        text=job.get('observed_at')
        if not text:continue
        unit=next((unit for unit in source.units if unit.id in {'legacy_unit_'+ref for ref in job.get('observed_sources',[])} and text in unit.text),None)
        value=partial_date(text)
        if unit and value.upper()<=workspace.formatting_as_of.upper():candidates.append((value,text,unit))
    if candidates and len({date_text(value) for value,_text,_unit in candidates})==1:
        value,text,unit=candidates[0];ref={'sourceId':source.id,'sourceRevision':source.revision,'unitId':unit.id,'unitRevision':unit.revision}
        fid=stable('observation',source.id)
        facts.append(ObservationFact(id=fid,revision=1,kind='source_observation',value={'sourceObservedAt':value.model_dump(by_alias=True),'evidence':{**ref,'text':text},'revision':1},origin='source',importance='normal',jobId=None,subprojectId=None,evidence=[ref]))
        unit.represented_fact_ids.append(fid);workspace.source_observed_at=value


def migrate_v2_archive(files,id,clock):
    archive=parse_json(files.get('archive.json'));view=parse_json(files['view.json']) if 'view.json' in files else None
    checked_v2(archive,view)
    allowed={'archive.json','source.json','units.txt','view.json',archive['source_snapshot']}
    if not set(files)<=allowed or parse_json(files.get('source.json'))!=archive['source']:raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
    content=files.get(archive['source_snapshot'])
    if content is None or digest(content)!=archive['source']['sha256'] or view and view.get('archive_sha256')!=digest(files['archive.json']):raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
    source,facts,jobs=legacy_source(archive,content)
    workspace=empty_workspace(id,archive['source']['file'],partial_date(archive['as_of']),clock.isoformat())
    observation(archive,workspace,source,facts)
    workspace.migration_notices=['portable_project_imported','legacy_v2_imported','imported_locks_ignored']
    text_history=[];legacy=LegacyData(blocks=[],proposals=[],review=None,renders=[],unmappedText=text_history)
    if view is None:
        workspace.pre_draft.sources=[source];workspace.pre_draft.facts=facts;workspace.pre_draft.selected_source_id=source.id
        workspace.pre_draft.extracted_text='\n\n'.join(unit.text for unit in source.units)
        from .gui_normalization import source_fingerprint
        workspace.pre_draft.extraction_fingerprint=source_fingerprint([source]);workspace.legacy_data=legacy
        return workspace,{source.id:content},{}
    doc=blank_document()
    refs=lambda item:['legacy_fact_'+id for id in item['sources']]
    for key in ['name','title']:doc['candidate'][key]=field('candidate/'+key,view['candidate'][key]['text'],refs(view['candidate'][key]))
    doc['profile']['text']=field('profile/text',view['candidate']['summary']['text'],refs(view['candidate']['summary']))
    by_job={job.id:job for job in jobs}
    for selected in view['projects']:
        job=by_job[selected['id']];record=job_record(job)
        for old,new in [('company','employer'),('role','role'),('description','context'),('stack','stack')]:
            if selected.get(old) is not None:record[new]=field('job:'+job.id+'/'+new,selected[old]['text'],refs(selected[old]))
        for key in ['tasks','results']:record[key]=field('job:'+job.id+'/'+key,'\n'.join(item['text'] for item in selected[key]),[ref for item in selected[key] for ref in refs(item)])
        if selected.get('period') is not None:text_history.append(history('legacy_period_label',job.id,selected['period']['text'],refs(selected['period'])));workspace.migration_notices.append('legacy_period_label')
        doc['jobs'].append(record)
    doc['earlyCareer']['text']=field('early-career/text','\n\n'.join(item['summary']['text'] for item in view['earlier_experience']),[ref for item in view['earlier_experience'] for ref in refs(item['summary'])])
    doc['earlyCareer']['representedJobIds']=[job_id for item in view['earlier_experience'] for job_id in item['job_ids']]
    skills=[item['title']+': '+item['items']['text'] for item in view['skill_groups']]
    skill_refs=[ref for item in view['skill_groups'] for ref in refs(item['items'])]
    from .gui_drafting import available_focus_ids
    available=available_focus_ids();seen=set();removed=[]
    for index,item in enumerate(view['focus']):
        label=item['label']['text'];matches=[entry.canonical_id for entry in CATALOG if label.strip().casefold() in {alias.casefold() for alias in entry.aliases}]
        catalog=matches[0] if len(matches)==1 else stable('unknown-focus',label)
        reason='unknown-ID' if len(matches)!=1 else 'duplicate' if catalog in seen else 'missing-logo' if catalog not in available else 'capacity' if len(doc['skillsFocus']['focus'])>=8 else None
        seen.add(catalog)
        if reason:
            skills.append(label);skill_refs.extend(refs(item['label']));removed.append({'catalogId':catalog,'reason':reason})
        else:doc['skillsFocus']['focus'].append({'id':stable('focus',str(index)+':'+label),'catalogId':catalog,'display':field('skills-focus/focus:'+str(index),label,refs(item['label'])),'factIds':list(dict.fromkeys([*refs(item['label']),*(fact.id for fact in facts if isinstance(fact,TechnologyFact) and fact.value.canonical_id==catalog and any(ref.unit_id in {'legacy_unit_'+key for key in item['label']['sources']} for ref in fact.evidence))]))})
        if item.get('duration') is not None:text_history.append(history('legacy_focus_duration',str(index),item['duration']['text'],refs(item['duration'])));workspace.migration_notices.append('legacy_duration_not_reused')
    doc['skillsFocus']['skillsText']=field('skills-focus/skillsText','\n\n'.join(skills),skill_refs)
    section={'ОБРАЗОВАНИЕ':('education','education'),'EDUCATION':('education','education'),'ЯЗЫКИ':('languages','language'),'LANGUAGES':('languages','language'),'СЕРТИФИКАТЫ':('certifications','certification'),'CERTIFICATIONS':('certifications','certification')}
    for index,item in enumerate(view['sidebar']):
        target=section.get(item['title'].strip().upper())
        for ordinal,value in enumerate(item['items']):
            key=str(index)+':'+str(ordinal)
            if target:doc[target[0]].append(legacy_row(target[1],stable(target[1],key),value['text'],refs(value)))
            else:text_history.append(history('unmapped_sidebar',key,value['text'],refs(value),label=item['title']));workspace.migration_notices.append('legacy_unmapped_sidebar')
    for index,item in enumerate(view.get('achievements',[])):text_history.append(history('unmapped_achievement',str(index),item['text'],refs(item)));workspace.migration_notices.append('legacy_unmapped_achievement')
    for unit in archive['units']:
        if archive['classifications'][unit['id']]['category'] in {'contacts','personal','meta'}:text_history.append(history('contact',unit['id'],unit['text'],['legacy_fact_'+unit['id']]))
    language=view.get('source_language','mixed')
    if language not in {'ru','en','mixed'}:raise ArchiveFailure('ARCHIVE_LEGACY_INVALID')
    if 'source_language' not in view:workspace.migration_notices.append('legacy_language_unknown')
    legacy.unmapped_text=text_history
    workspace=finish_document(workspace,doc,jobs,facts,[source],[],legacy,language)
    if removed:
        from .models.recovery import Annotation
        from .gui_reconciliation import result_dependencies
        from .rules import captured_rules,DEFAULT_RULES
        deps=result_dependencies(workspace,captured_rules(DEFAULT_RULES,1));deps.rules_sha256=None
        workspace.annotations.append(Annotation(id=stable('annotation','focus'),type='warning',code='focus_entry_removed',anchor={'kind':'section','sectionId':'skills-focus'},
            dependencies=deps,factIds=[],reason='Legacy focus entries could not be retained as logos.',evidence=[],resolved=False,updateSuggestionId=None,removedFocus=removed))
    workspace.title=doc['candidate']['name']['text'] or workspace.title
    workspace.migration_notices=list(dict.fromkeys(workspace.migration_notices))
    return workspace,{source.id:content},{}
