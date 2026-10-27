"""Synthetic current-content, history and version boundaries for portable files."""

import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'services/api/src'))
from packages.resume_core.gui_archive import open_archive,export_archive
from packages.resume_core.archive_zip import read_zip,write_zip,json_bytes,digest,ArchiveFailure
from packages.resume_core.gui_legacy_context import migration_context,public_workspace_facts
from packages.resume_core.gui_rendering import render_input
from tests.recovery.generation_fixtures import frozen_now,render_workspace
from tests.recovery.test_gui_mutations import restore
from tests.recovery.test_gui_archive import EXAMPLES


def legacy_v3(change=lambda project:None):
    old=read_zip((EXAMPLES/'legacy_workspace_v4.foldcv').read_bytes());project=json.loads(old['project.json']);change(project)
    files={'project.json':json_bytes(project),**{source['byteRef']:old[source['byteRef']] for source in project['sources']}}
    manifest={'schemaVersion':3,'appVersion':'0.1.0','rendererVersion':'1.0.0','projectId':project['projectId'],'entries':[{'path':path,'role':'project' if path=='project.json' else 'source_original','sha256':digest(data),'uncompressedSize':len(data)} for path,data in files.items()]}
    return write_zip({'manifest.json':json_bytes(manifest),**files})


def alter(data,path,change):
    files=read_zip(data);value=json.loads(files[path]);change(value);files[path]=json_bytes(value)
    manifest=json.loads(files['manifest.json'])
    for item in manifest['entries']:
        item['sha256']=digest(files[item['path']]);item['uncompressedSize']=len(files[item['path']])
    files['manifest.json']=json_bytes(manifest);return write_zip(files)


def v2(view=True,observed=False):
    text='Alex Example\nEngineer\nExample Works service Python\n2025-02-03\n'
    source={'file':'synthetic.txt','sha256':digest(text.encode()),'pages':[{'page':1,'text':text}],'warnings':[]}
    units=[{'id':'u1','page':1,'text':text}];statement=lambda text:{'text':text,'sources':['u1']}
    job={'id':'job_1','company':statement('Example Works'),'period':statement('2021–present'),'role':statement('Engineer'),'start':'2021','end':None,'technologies':[{'name':'Python','sources':['u1']}]}
    if observed:job.update(observed_at='2025-02-03',observed_sources=['u1'])
    archive={'schema_version':2,'as_of':'2026-10-11','source_snapshot':'original.txt','source':source,'units':units,'classifications':{'u1':{'category':'task','importance':'essential','job_id':'job_1'}},'jobs':[job],'global_technologies':[]}
    raw=json_bytes(archive);files={'archive.json':raw,'source.json':json_bytes(source),'original.txt':text.encode()}
    selected={'schema_version':2,'template':'generic-v1','archive_sha256':digest(raw),'candidate':{'name':statement('Alex Example'),'title':statement('Engineer'),'summary':statement('Saved profile')},
        'projects':[{'id':'job_1','company':statement('Saved company'),'role':statement('Saved role'),'period':statement('Old free label'),'description':statement('Whole context. Another sentence.'),'tasks':[statement('Task one'),statement('Task two')],'results':[statement('Result one')],'stack':statement('Python')}],
        'earlier_experience':[],'focus':[{'label':statement('Python'),'duration':statement('99 years')},{'label':statement('Unknown label')}],
        'sidebar':[{'title':' education ','items':[statement('School, course, date unsplit')]},{'title':'ЯЗЫКИ','items':[statement('English working proficiency')]},{'title':'CERTIFICATIONS','items':[statement('Saved certificate')]},{'title':'Other','items':[statement('Unmapped sidebar')]}],
        'skill_groups':[{'title':'Tools','items':statement('Python, Docker')}],'achievements':[statement('Unmapped achievement')],'coverage':{'u1':{'decision':'shown'}}}
    if view:files['view.json']=json_bytes(selected)
    return files,archive,selected


def test_standalone_v3_never_infers_identity_language_observation_or_splits_prose():
    workspace,_,_=open_archive(legacy_v3(),'v3',frozen_now());doc=workspace.project.document
    assert doc.candidate.name.text==doc.candidate.title.text==doc.candidate.location.text==''
    assert workspace.editorial_plan.source_language=='mixed' and workspace.editorial_plan.profile_language is None and workspace.editorial_plan.rules_revision is None
    assert workspace.source_observed_at is None and doc.jobs[0].context.text and doc.jobs[0].tasks.text==doc.jobs[0].results.text==doc.jobs[0].stack.text==''
    assert all(not block.state.locked for block in workspace.project.views)


@pytest.mark.parametrize('date,created,expected,notice', [('2020',None,'2020',False),(None,'2024-02-03T23:00:00-05:00','2024-02-03',False),(None,'','2026-10-11',True)])
def test_v3_formatting_date_keeps_precision_or_local_created_date_without_source_observation(date,created,expected,notice):
    from packages.resume_core.dates import partial_date
    def change(project):
        project['asOf']=partial_date(date).model_dump(by_alias=True) if date else None
        if created is not None:project['createdAt']=created
    workspace,_,_=open_archive(legacy_v3(change),'dated',frozen_now())
    from packages.resume_core.gui_migration import date_text
    assert date_text(workspace.formatting_as_of)==expected and workspace.source_observed_at is None
    assert ('legacy_formatting_date_unavailable' in workspace.migration_notices)==notice


def test_v3_generated_profile_previous_preserves_origin_stamps_and_job_history_only():
    def change(project):
        profile=next(block for block in project['views'] if block['kind']=='profile');profile['state']['origin']='generated';profile['previous']['origin']='generated'
        from copy import deepcopy
        job=next(block for block in project['views'] if block['kind']=='job_prose');job['previous']=deepcopy(job['state']);job['revision']=2
    workspace,_,_=open_archive(legacy_v3(change),'generated',frozen_now())
    assert workspace.project.document.profile.text.origin=='generated' and workspace.undo_slots['profile'].record.text.origin=='generated'
    assert all(stamp.origin=='model' for stamp in workspace.undo_slots['profile'].fact_stamps)
    previous=workspace.undo_slots['profile'].record.text.text;restore(workspace,'profile');assert workspace.project.document.profile.text.text==previous
    assert 'legacy_job_undo_history_only' in workspace.migration_notices


def test_multiple_profiles_merge_visible_saved_order_and_never_create_single_profile_undo():
    def change(project):
        from copy import deepcopy
        profile=next(block for block in project['views'] if block['kind']=='profile');profile['state']['text']='First visible'
        hidden=deepcopy(profile);hidden['id']='hidden_profile';hidden['visible']=False;hidden['state']['text']='Hidden profile'
        last=deepcopy(profile);last['id']='last_profile';last['state']['text']='Last visible'
        project['views']+=[hidden,last]
    workspace,_,_=open_archive(legacy_v3(change),'merged',frozen_now())
    assert workspace.project.document.profile.text.text=='First visible\n\nLast visible' and workspace.undo_slots['profile'] is None
    assert any(block.state.text=='Hidden profile' and not block.visible for block in workspace.legacy_data.blocks)


def test_single_hidden_profile_keeps_text_and_visibility():
    def change(project):next(block for block in project['views'] if block['kind']=='profile')['visible']=False
    workspace,_,_=open_archive(legacy_v3(change),'hidden',frozen_now())
    assert workspace.project.document.profile.text.text and not workspace.project.document.profile.visible
    assert any(item.record_id=='profile' and item.reason=='hidden' for item in workspace.source_exclusions)


def test_ambiguous_job_prose_keeps_history_and_empty_context_without_positional_binding():
    def change(project):
        from copy import deepcopy
        block=next(block for block in project['views'] if block['kind']=='job_prose');other=deepcopy(block);other['id']='ambiguous_prose';project['views'].append(other)
    workspace,_,_=open_archive(legacy_v3(change),'ambiguous',frozen_now())
    first=workspace.project.document.jobs[0]
    assert first.context.text=='' and 'legacy_ambiguous_job_prose' in workspace.migration_notices
    assert len([item for item in workspace.legacy_data.unmapped_text if item.original_kind=='unmapped_job_prose'])>=2


def test_v4_presentation_unsplit_rows_and_unapplied_forms_remain_separate_from_current_document():
    data=(EXAMPLES/'legacy_workspace_v4.foldcv').read_bytes()
    def change(raw):raw['editor']['presentation']['languages']=['English — working proficiency'];raw['manualForm']['name']='Unapplied name';raw['manualForm']['education']='Unapplied school';raw['editor']['presentationDrafts']={'name':'Unapplied draft name'}
    data=alter(data,'project.json',lambda raw:next(block for block in raw['views'] if block['kind']=='education')['state'].update(text='Saved school, course and date'))
    workspace,_,_=open_archive(alter(data,'workspace.json',change),'v4-content',frozen_now());doc=workspace.project.document
    assert doc.candidate.name.text=='Мария Примерова' and doc.languages[0].legacy_text.text=='English — working proficiency' and doc.languages[0].name.text==''
    assert doc.education[0].legacy_text.text and doc.education[0].institution.text==''
    context=migration_context(workspace);assert any(item.text=='Unapplied name' for item in context.legacy_text)
    rendered=json.dumps(render_input(workspace)[0].model_dump(by_alias=True),ensure_ascii=False)
    assert 'Unapplied name' not in rendered and 'Unapplied school' not in rendered


@pytest.mark.parametrize('bad',['manual','presentation','undo','unknown','credentials','draft','render_binding'])
def test_v4_retains_old_invalid_envelope_rejections(bad):
    def change(raw):
        if bad=='manual':raw['manualForm']['employment']=[{'id':'bad'}]
        elif bad=='presentation':raw['editor']['presentation']['jobProseBlocks']={}
        elif bad=='undo':raw['editor']['undo']['profile']['visible']='true'
        elif bad=='unknown':raw['schemaVersion']=5
        elif bad=='credentials':raw['editor']['password']='secret'
        elif bad=='draft':raw['editor']['drafts']['missing']='Unapplied'
        else:raw['renderBinding']='0'*64
    with pytest.raises(ArchiveFailure):open_archive(alter((EXAMPLES/'legacy_workspace_v4.foldcv').read_bytes(),'workspace.json',change),'invalid',frozen_now())


def test_v2_direct_fields_sidebar_exact_titles_focus_and_old_duration_history():
    files,_,_=v2();workspace,_,_=open_archive(write_zip(files),'v2',frozen_now());doc=workspace.project.document;job=doc.jobs[0]
    assert job.id=='job_1' and job.employer.text=='Saved company' and job.role.text=='Saved role' and job.periods[0].start_text.text=='2021' and job.periods[0].present
    assert job.context.text=='Whole context. Another sentence.' and job.tasks.text=='Task one\nTask two' and job.results.text=='Result one' and job.stack.text=='Python'
    assert doc.skills_focus.skills_text.text=='Tools: Python, Docker\n\nUnknown label' and [item.catalog_id for item in doc.skills_focus.focus]==['python']
    assert doc.education[0].legacy_text.text=='School, course, date unsplit' and doc.languages[0].legacy_text.text=='English working proficiency' and doc.certifications[0].legacy_text.text=='Saved certificate'
    history={item.text for item in workspace.legacy_data.unmapped_text};assert {'Old free label','99 years','Unmapped sidebar','Unmapped achievement'}<=history
    assert workspace.source_observed_at is None and workspace.editorial_plan.origin=='migration'
    focus=next(value for value in workspace.derived_state.values if value.field_id==doc.skills_focus.focus[0].display.field_id)
    assert focus.months_min is None and focus.display is None


def test_v2_without_selected_view_stays_predraft_with_originals_and_facts():
    files,_,_=v2(False);workspace,originals,_=open_archive(write_zip(files),'v2-input',frozen_now())
    assert workspace.project is None and workspace.pre_draft.facts and workspace.pre_draft.extracted_text and workspace.generations==[]
    assert list(originals.values())==[files['original.txt']]


def test_v2_observation_requires_explicit_literal_evidence_and_recomputes_duration():
    files,_,_=v2(observed=True);workspace,_,_=open_archive(write_zip(files),'observed',frozen_now())
    assert workspace.source_observed_at.year==2025 and workspace.source_observed_at.month==2
    focus=workspace.project.document.skills_focus.focus[0];derived=next(value for value in workspace.derived_state.values if value.field_id==focus.display.field_id)
    assert derived.months_min is not None and '99' not in (derived.display or '')


def test_v2_explicit_early_job_membership_keeps_summary_without_age_inference():
    files,_,view=v2();view['projects']=[];view['earlier_experience']=[{'job_ids':['job_1'],'summary':{'text':'Saved earlier summary','sources':['u1']}}];files['view.json']=json_bytes(view)
    workspace,_,_=open_archive(write_zip(files),'early',frozen_now())
    assert workspace.project.document.jobs==[] and workspace.project.document.early_career.represented_job_ids==['job_1']
    assert workspace.editorial_plan.jobs[0].disposition=='early-career'


def test_legacy_contact_category_does_not_filter_content_facts():
    def change(project):
        from copy import deepcopy
        block=deepcopy(next(block for block in project['views'] if block['kind']=='profile'));block.update(id='private_contact',kind='contact');block['state']['text']='private@example.invalid';project['views'].append(block)
    workspace,_,_=open_archive(legacy_v3(change),'private',frozen_now());private={ref for block in workspace.legacy_data.blocks if block.kind=='contact' for ref in block.state.fact_ids}
    assert private and private <= {fact.id for fact in public_workspace_facts(workspace)}
    assert 'private@example.invalid' in {item.text for item in migration_context(workspace).legacy_text}


@pytest.mark.parametrize('bad',['fact_ref','evidence','annotation','rules','project_version','session','observation'])
def test_v5_valid_hash_cannot_hide_invalid_references_versions_or_session_ownership(bad):
    from tests.recovery.candidate_fixtures import ROOT
    from tests.recovery.test_gui_mutations import edit
    workspace=render_workspace()
    from packages.resume_core.rules import captured_rules,DEFAULT_RULES
    workspace.rules_used=captured_rules(DEFAULT_RULES,1)
    edit(workspace,'profile/text','Open session');originals={source.id:(ROOT/'E1.txt').read_bytes() for source in workspace.project.sources}
    def change(raw):
        if bad=='fact_ref':raw['project']['document']['profile']['text']['factIds']=['missing']
        elif bad=='evidence':raw['project']['facts'][0]['evidence'][0]['unitId']='missing'
        elif bad=='annotation':raw['annotations'][0]['factIds']=['missing']
        elif bad=='rules':raw['rulesUsed']['sha256']='0'*64
        elif bad=='project_version':raw['project']['schemaVersion']=5
        elif bad=='session':raw['editSessions']['profile']['baseline']['record']=raw['project']['document']['candidate']
        else:raw['sourceObservedAt']={'year':2026,'month':1,'day':1,'precision':'day'}
    with pytest.raises(ArchiveFailure):open_archive(alter(export_archive(workspace,originals,{}),'workspace.json',change),'invalid',frozen_now())


def test_explicit_legacy_block_and_fact_exclusions_win_over_visible_state():
    def change(project):
        profile=next(block for block in project['views'] if block['kind']=='profile');ref=profile['state']['factIds'][0]
        fact=next(fact for fact in project['facts'] if fact['id']==ref)
        project['review']['decisions']=[{'targetKind':'block','targetId':profile['id'],'disposition':'excluded','reason':'Saved omission','targetRevision':profile['revision']},{'targetKind':'fact','targetId':ref,'disposition':'excluded','reason':'Saved omission','targetRevision':fact['revision']}]
    workspace,_,_=open_archive(legacy_v3(change),'excluded',frozen_now())
    assert not workspace.project.document.profile.visible and any(item.reason=='deleted' and item.fact_ids for item in workspace.source_exclusions)


def test_v3_historical_render_stays_separate_from_new_v4_render_metadata():
    def change(project):
        from packages.resume_core.rendering.template import PACKAGE_SHA256
        project['template']={'id':'generic','version':'1.0.0','packageSha256':PACKAGE_SHA256,'contentPolicyVersion':'1.0.0','assets':[]}
        block=project['views'][0]
        project['renders']=[{'id':'old-render','projectRevision':project['revision'],'templateId':'generic','templateVersion':'1.0.0','rendererVersion':'1.0.0','snapshotSha256':'0'*64,'blocks':[{'blockId':block['id'],'blockRevision':block['revision'],'text':block['state']['text']}],'docx':{'path':'renders/resume.docx','sha256':'0'*64,'size':20},'pdf':None}]
    workspace,_,_=open_archive(legacy_v3(change),'render-history',frozen_now())
    assert workspace.project.renders==[] and len(workspace.legacy_data.renders)==1 and not workspace.legacy_data.renders[0].artifact_available
    assert workspace.legacy_data.renders[0].record.id=='old-render' and 'documentRevision' not in workspace.legacy_data.renders[0].record.model_dump(by_alias=True)


def test_untrusted_legacy_template_asset_claim_rejects_even_without_packaged_assets():
    def change(project):
        from packages.resume_core.rendering.template import PACKAGE_SHA256
        project['template']={'id':'generic','version':'1.0.0','packageSha256':PACKAGE_SHA256,'contentPolicyVersion':'1.0.0','assets':[{'path':'unknown.png','sha256':'0'*64,'size':1}]}
    with pytest.raises(ArchiveFailure,match='ARCHIVE_TEMPLATE_INVALID'):open_archive(legacy_v3(change),'bad-template',frozen_now())
