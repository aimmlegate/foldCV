"""Portable snapshots and direct legacy current-content/history mapping."""

import json
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile

import pytest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"services/api/src"))
from packages.resume_core.gui_archive import export_archive,open_archive
from packages.resume_core.gui_archive_zip import ArchiveFailure,read_zip,write_zip,json_bytes,digest
from tests.recovery.generation_fixtures import render_workspace,frozen_now
from tests.recovery.candidate_fixtures import ROOT
from tests.recovery.test_gui_mutations import edit,restore

EXAMPLES=Path(__file__).resolve().parents[2]/'contracts/examples/recovery'


def test_v5_round_trip_keeps_current_text_sources_counters_and_both_restore_steps():
    workspace=render_workspace();baseline=workspace.project.document.profile.text.text
    edit(workspace,'profile/text','Saved prior',completion='slot');edit(workspace,'profile/text','Open current buffer',completion='paragraph')
    originals={source.id:(ROOT/'E1.txt').read_bytes() for source in workspace.project.sources}
    data=export_archive(workspace,originals,{})
    loaded,bytes,_=open_archive(data,'fresh-import',frozen_now())
    assert loaded.project_id==loaded.project.project_id=='fresh-import' and loaded.project.document==workspace.project.document
    assert (loaded.project_revision,loaded.document_revision)==(workspace.project_revision,workspace.document_revision)
    assert loaded.edit_sessions==workspace.edit_sessions and loaded.undo_slots==workspace.undo_slots and loaded.mutation_replay==[] and bytes==originals
    restore(loaded,'profile');assert loaded.project.document.profile.text.text=='Saved prior'
    restore(loaded,'profile');assert loaded.project.document.profile.text.text==baseline
    restore(loaded,'profile');assert loaded.project.document.profile.text.text==baseline


def test_valid_v4_fixture_maps_presentation_unsplit_jobs_and_profile_previous_without_locks():
    data=(EXAMPLES/'legacy_workspace_v4.foldcv').read_bytes();workspace,originals,_=open_archive(data,'fresh-v4',frozen_now())
    assert workspace.project.document.candidate.name.text=='Мария Примерова' and workspace.editorial_plan.source_language=='en'
    assert workspace.project.document.jobs[0].context.text and not workspace.project.document.jobs[0].tasks.text
    assert workspace.undo_slots['profile'] is not None and all(workspace.undo_slots['job:'+job.id] is None for job in workspace.project.document.jobs)
    assert any(block.state.locked for block in workspace.legacy_data.blocks)
    assert all(not block.state.locked for block in workspace.project.views)
    assert any(item.original_kind=='unapplied_draft' for item in workspace.legacy_data.unmapped_text)
    assert workspace.source_observed_at is None and originals


@pytest.mark.parametrize('kind',['path','hash','version','json','extra'])
def test_corrupt_or_unsupported_archive_fails_without_returning_partial_workspace(kind):
    workspace=render_workspace();originals={source.id:(ROOT/'E1.txt').read_bytes() for source in workspace.project.sources}
    files=read_zip(export_archive(workspace,originals,{}));manifest=json.loads(files['manifest.json'])
    if kind=='path':files['../external']=b'x'
    elif kind=='hash':files['workspace.json']+=b' '
    elif kind=='version':manifest['schemaVersion']=6;files['manifest.json']=json_bytes(manifest)
    elif kind=='json':files['manifest.json']=b'{"schemaVersion":5,"schemaVersion":6}'
    else:files['unlisted.txt']=b'x'
    with pytest.raises(ArchiveFailure):open_archive(write_zip(files),'new',frozen_now())
