"""Retain the old workspace envelope's rejection rules on Python import."""

import re
from .gui_archive_zip import ArchiveFailure,safe_path
from .extraction.models import ExtractResult
from .models.contracts import BlockState,Review,MetricValue,LeadershipValue
from .normalization import FactSheet
from .drafting import DraftResult
from .rewriting import RewriteResult,RewriteIssue


def require(ok):
    if not ok:raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')

def shape(value,required,optional=()):
    require(isinstance(value,dict) and set(required)<=value.keys() and value.keys()<=set(required)|set(optional))

def strings(value):return isinstance(value,dict) and all(isinstance(key,str) and isinstance(item,str) for key,item in value.items())
def string_list(value):return isinstance(value,list) and all(isinstance(item,str) for item in value)


def manual(value):
    shape(value,['name','title','asOf','education','language','languages','skills','employment','metrics','leadership'])
    require(all(isinstance(value[key],str) for key in ['name','title','asOf','education']) and value['language'] in {'ru','en','mixed'})
    require(string_list(value['languages']) and string_list(value['skills']))
    for key in ['employment','metrics','leadership']:require(isinstance(value[key],list))
    for job in value['employment']:
        shape(job,['id','employer','role','start','end','description','subprojects'])
        require(all(isinstance(job[key],str) for key in ['id','employer','role','start','end','description']) and isinstance(job['subprojects'],list))
        for sub in job['subprojects']:
            shape(sub,['id','name','start','end','description']);require(strings(sub))
    for item in value['metrics']:
        shape(item,['id','jobId','number','upperNumber','comparator','unit','period','baseline','result','scope','attribution','qualifiers'])
        require(isinstance(item['id'],str) and (item['jobId'] is None or isinstance(item['jobId'],str)))
        MetricValue.model_validate({key:entry for key,entry in item.items() if key not in {'id','jobId'}})
    for item in value['leadership']:
        shape(item,['id','jobId','action','attribution','teamSize','teamUnit','teamBaseline'])
        require(isinstance(item['id'],str) and isinstance(item['jobId'],str))
        LeadershipValue.model_validate({key:entry for key,entry in item.items() if key not in {'id','jobId'}})


def imported(entry):
    shape(entry,['result','overlays']);result=ExtractResult.model_validate(entry['result']);require(strings(entry['overlays']))
    require(sum(len(text.encode('utf-8')) for text in entry['overlays'].values())<=1024*1024)
    for key,text in entry['overlays'].items():
        require(len(text.encode('utf-8'))<=64*1024 and (key in {'unit:'+unit.id for unit in result.units} or re.fullmatch(r'gap:(0|[1-9]\d*)',key) and int(key[4:])<len(result.gaps)))
    return result


def coverage(value):
    shape(value,['decisions','acknowledgments'])
    require(isinstance(value['decisions'],list) and isinstance(value['acknowledgments'],list))
    for item in value['decisions']:
        shape(item,['targetKind','targetId','disposition','reason','dependency'])
        require(item['targetKind'] in {'unit','fact','job'} and item['disposition'] in {'shown','condensed','archived','duplicate','unresolved','excluded'} and isinstance(item['targetId'],str) and isinstance(item['dependency'],str) and (item['reason'] is None or isinstance(item['reason'],str)))
    for item in value['acknowledgments']:
        shape(item,['issueId','dependency']);require(strings(item))


def editor_details(editor,project):
    from .gui_migration import LegacyPresentation
    manual_fields={'name','title'}
    require(strings(editor['presentationDrafts']) and editor['presentationDrafts'].keys()<=manual_fields)
    for key in ['presentation','presentationUndo']:
        if editor[key] is not None:
            presentation=LegacyPresentation.model_validate(editor[key]);bindings=presentation.job_prose_blocks
            require(presentation.source_language in {'ru','en','mixed'} and set(bindings)=={job.id for job in project.employment} and len(set(bindings.values()))==len(bindings) and all(any(block.id==id and block.kind=='job_prose' for block in project.views) for id in bindings.values()))
    blocks={block.id for block in project.views}
    for key in ['rewriteIssues','rewriteIssueDetails']:
        require(isinstance(editor[key],dict) and editor[key].keys()<=blocks)
        for items in editor[key].values():
            require(isinstance(items,list))
            if key=='rewriteIssues':require(string_list(items))
            else:
                for item in items:RewriteIssue.model_validate(item)
    require(string_list(editor['workingIssues']))
    if editor['rewriteProposal'] is not None:
        shape(editor['rewriteProposal'],['result','before']);require(isinstance(editor['rewriteProposal']['before'],str));RewriteResult.model_validate(editor['rewriteProposal']['result'])
    coverage({'decisions':editor.get('standaloneDecisions',[]),'acknowledgments':editor.get('standaloneAcknowledgments',[])})
    for cp in editor['undo'].values():
        shape(cp,['state','revision','visible','status','dependencyHash','review','issues','issueDetails','coverage','manualEducation'],['standaloneDecisions','standaloneAcknowledgments'])
        require(type(cp['revision']) is int and cp['revision']>=1 and type(cp['visible']) is bool and cp['status'] in {'empty','running','proposed','ready','stale','error'} and isinstance(cp['dependencyHash'],str) and re.fullmatch('[a-f0-9]{64}',cp['dependencyHash']) and string_list(cp['issues']) and isinstance(cp['issueDetails'],list) and (cp['manualEducation'] is None or isinstance(cp['manualEducation'],str)))
        BlockState.model_validate(cp['state']);Review.model_validate(cp['review'])
        for issue in cp['issueDetails']:RewriteIssue.model_validate(issue)
        if cp['coverage'] is not None:coverage(cp['coverage'])
        coverage({'decisions':cp.get('standaloneDecisions',[]),'acknowledgments':cp.get('standaloneAcknowledgments',[])})
    working=editor['working']
    if working is None:return
    shape(working,['transportVersion','sources','sheet','priorSheet','sourceReviewStale','manual','draft'],['structuredCorrections','coverage'])
    require(working['transportVersion']==1 and isinstance(working['sources'],list) and type(working['sourceReviewStale']) is bool)
    require(not editor.get('standaloneDecisions') and not editor.get('standaloneAcknowledgments') and all(not cp.get('standaloneDecisions') and not cp.get('standaloneAcknowledgments') for cp in editor['undo'].values()))
    manual(working['manual']);FactSheet.model_validate(working['sheet'])
    if working['priorSheet'] is not None:FactSheet.model_validate(working['priorSheet'])
    if working['draft'] is not None:DraftResult.model_validate(working['draft'])
    if 'structuredCorrections' in working:require(strings(working['structuredCorrections']))
    if 'coverage' in working:coverage(working['coverage'])
    sources={source.id:source for source in project.sources}
    require(len(working['sources'])==len(sources))
    seen=set()
    for value in working['sources']:
        shape(value,['entry','originalRef']);require(safe_path(value['originalRef']));result=imported(value['entry']);source=sources.get(result.source_id)
        require(source is not None and result.source_id not in seen and source.byte_sha256==result.byte_sha256 and source.original_name==result.original_name and source.parser==result.parser and source.parser_version==result.parser_version and len(source.units)==len(result.units))
        require(all(unit.id==f'view_{source.id}_{old.id}' and unit.text==old.text for unit,old in zip(source.units,result.units)))
        seen.add(result.source_id)
    facts={fact.id:fact for fact in project.facts}
    for job in working['manual']['employment']:
        for key,text in [('fact_user_manual_job_'+job['id'],job['description']),*[('fact_user_manual_sub_'+sub['id'],sub['description']) for sub in job['subprojects']]]:
            fact=facts.get(key);require(fact is not None and fact.kind=='text' and fact.value.text==text.strip())
