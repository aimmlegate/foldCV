"""ZIP structure and explicit capacity failures without filesystem extraction."""

from io import BytesIO
from pathlib import Path
import sys
import struct
from zipfile import ZipFile,ZIP_DEFLATED
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'services/api/src'))
from packages.resume_core import archive_zip as codec
from packages.resume_core.gui_archive import export_archive,open_archive
from tests.recovery.generation_fixtures import render_workspace,frozen_now
from tests.recovery.candidate_fixtures import ROOT


@pytest.mark.parametrize('name',['../outside','/outside','a\\b','a:b','a//b','a/./b','a/../b','a/constructor/b','a/__proto__/b','a.','a ','a\x00b'])
def test_unsafe_names_are_rejected_before_write(name):
    with pytest.raises(codec.ArchiveFailure):codec.write_zip({'manifest.json':b'{}',name:b'private'})


@pytest.mark.parametrize('change',['flags','symlink','offset','crc','count','central_name','trailing','compression'])
def test_malformed_zip_structure_or_crc_is_rejected(change):
    data=bytearray(codec.write_zip({'a.txt':b'data','b.txt':b'data'}));central=struct.unpack_from('<I',data,len(data)-6)[0]
    if change=='flags':struct.pack_into('<H',data,central+8,1)
    elif change=='symlink':struct.pack_into('<I',data,central+38,0xa000<<16)
    elif change=='offset':struct.pack_into('<I',data,central+42,1)
    elif change=='crc':data[35]^=1
    elif change=='count':struct.pack_into('<H',data,len(data)-12,1)
    elif change=='central_name':data[central+46]=ord('x')
    elif change=='trailing':data+=b'x'
    else:struct.pack_into('<H',data,central+10,12)
    with pytest.raises(codec.ArchiveFailure):codec.read_zip(bytes(data))


def test_case_and_unicode_aliases_reject_before_decode():
    for names in [('A.txt','a.txt'),('é.txt','e\u0301.txt')]:
        with pytest.raises(codec.ArchiveFailure):codec.write_zip({name:b'data' for name in names})


def test_deflate_ratio_and_lied_expansion_size_reject_bounded_inflate():
    output=BytesIO()
    with ZipFile(output,'w',compression=ZIP_DEFLATED) as archive:
        archive.writestr('a.txt',b'a'*100000);archive.writestr('b.txt',b'other')
    with pytest.raises(codec.ArchiveFailure):codec.read_zip(output.getvalue())
    output=BytesIO()
    with ZipFile(output,'w',compression=ZIP_DEFLATED) as archive:
        archive.writestr('a.txt',bytes(range(256))*20);archive.writestr('b.txt',b'other')
    data=bytearray(output.getvalue());central=struct.unpack_from('<I',data,len(data)-6)[0]
    struct.pack_into('<I',data,central+24,100);struct.pack_into('<I',data,22,100)
    with pytest.raises(codec.ArchiveFailure):codec.read_zip(bytes(data))


@pytest.mark.parametrize('limit,code',[('MAX_ENTRY','ARCHIVE_ENTRY_SIZE_LIMIT'),('MAX_TOTAL','ARCHIVE_EXPANDED_LIMIT'),('MAX_ARCHIVE','ARCHIVE_SIZE_LIMIT'),('MAX_JSON','ARCHIVE_JSON_LIMIT')])
def test_capacity_failures_are_explicit_and_keep_current_workspace(monkeypatch,limit,code):
    workspace=render_workspace();before=workspace.model_dump();originals={source.id:(ROOT/'E1.txt').read_bytes() for source in workspace.project.sources}
    monkeypatch.setattr(codec,limit,10)
    with pytest.raises(codec.ArchiveFailure,match=code):export_archive(workspace,originals,{})
    assert workspace.model_dump()==before


def test_47_payload_bound_accepts_boundary_then_rejects_extra_original_without_loss():
    workspace=render_workspace();source=workspace.project.sources[0];content=(ROOT/'E1.txt').read_bytes();originals={source.id:content}
    for index in range(45):
        extra=source.model_copy(deep=True);extra.id='extra-'+str(index);extra.byte_ref='sources/'+extra.id+'/original';workspace.project.sources.append(extra);originals[extra.id]=content
    data=export_archive(workspace,originals,{});assert len(codec.read_zip(data))==48
    before=workspace.model_dump();extra=source.model_copy(deep=True);extra.id='extra-limit';extra.byte_ref='sources/extra-limit/original';workspace.project.sources.append(extra);originals[extra.id]=content
    with pytest.raises(codec.ArchiveFailure,match='ARCHIVE_ENTRY_LIMIT'):export_archive(workspace,originals,{})
    assert len(workspace.project.sources)==47 and workspace.project.document.model_dump()==before['project']['document']


@pytest.mark.parametrize('data',[b'{"key":1,"key":2}',b'{"value":NaN}',b'{"value":Infinity}',b'\xff',b'['*2000+b']'*2000])
def test_invalid_json_duplicate_keys_nonfinite_utf8_or_depth_reject(data):
    with pytest.raises(codec.ArchiveFailure):codec.parse_json(data)
