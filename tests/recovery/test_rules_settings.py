"""Saved editorial Markdown reaches later requests without rewriting the document."""

from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'services/api/src'))
import pytest
from packages.resume_core.rules import RulesStore
from packages.resume_core.preferences import PreferencesStore
from tests.recovery.test_project_store import created,service
from tests.recovery.test_gui_projects import finish
from tests.recovery.test_gui_rewriting import request
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.candidate_fixtures import ROOT


@pytest.mark.asyncio
async def test_rules_save_leaves_current_document_and_checkpoints_then_next_rewrite_captures_new_revision(tmp_path):
    store,id=await created(tmp_path);store.preferences=PreferencesStore(store.rules.root);store.preferences.save_analysis(False)
    before=store.read(id);current=store.rules.load();saved=store.rules.save(current.markdown.replace('15 years','20 years'),current.revision)
    assert saved.revision==2 and store.read(id).model_dump()==before.model_dump()
    provider=CreationProvider();store.provider_factory=lambda:(provider,'fixture')
    result=await store.rewrite(id,request(store.read(id),['profile/text'],rules=saved))
    assert result.status=='applied' and len(provider.calls)==1
    assert provider.calls[0]['rulesUsed']['revision']==2 and provider.calls[0]['rulesUsed']['sha256']==saved.sha256
    assert '20 years' in provider.calls[0]['rulesUsed']['markdown']
    assert next(op for op in reversed(store.read(id).project.operations) if op.kind=="rewrite_prose").rules_used==saved


@pytest.mark.asyncio
async def test_restarted_rules_revision_reaches_both_creation_prompts_and_presets_without_save_inference(tmp_path):
    store=service(tmp_path);current=store.rules.load();markdown=current.markdown.replace('15 years','20 years').replace('Сократи выбранный текст','Сократи выбранный текст точно')
    saved=store.rules.save(markdown,current.revision);assert RulesStore(store.rules.root).load()==saved
    provider=CreationProvider();reopened=service(tmp_path,provider)
    selected=await reopened.select((ROOT/'E1.txt').read_bytes(),'pasted.txt',True);assert provider.calls==[]
    after=await finish(reopened,selected.project_id,reopened.start(selected.project_id));assert after.generations[-1].status=='completed'
    assert len(provider.calls)==2 and all(call['rulesUsed']['revision']==2 and call['rulesUsed']['markdown']==saved.markdown for call in provider.calls)
    assert all(op.rules_used==saved for op in after.project.operations)
