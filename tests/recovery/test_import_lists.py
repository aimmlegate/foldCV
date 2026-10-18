"""List repair must preserve wording, field bindings and source evidence."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from packages.resume_core.import_lists import format_import_lists
from packages.resume_core.models.rich_document import RichDocumentV1


def fixture(texts, *, pages=None):
    units, blocks = [], []
    for index, value in enumerate(texts):
        unit = SimpleNamespace(id=f'u{index}', text=value, location=SimpleNamespace(kind='page', index=(pages or [0] * len(texts))[index]),
            structure=SimpleNamespace(bounds=[50, 10 + index * 15, 400, 20 + index * 15], group=1, bold=False))
        units.append(unit)
        blocks.append({'id':f'b{index}', 'revision':1, 'type':'paragraph', 'props':{}, 'children':[],
            'content':[{'type':'text','text':value,'styles':{}}], 'provenance':[{'kind':'source','id':f's{index}',
                'evidence':[{'sourceId':'source','sourceRevision':1,'unitId':unit.id,'unitRevision':1,'text':value}]}]})
    return [SimpleNamespace(id='source',units=units)], blocks


def format_blocks(sources, blocks):
    return format_import_lists({'main':blocks},sources,lambda kind,key:kind+str(key))['main']


def text(block):
    return ''.join(s['text'] for s in block['content'])


def test_pdf_list_continuations_join_with_hanging_item_and_keep_field_bindings_and_evidence():
    sources, blocks = fixture(['- Built a service for multiple\n','customers using PostgreSQL.\n','Duties:\n','- Next item.\n'])
    blocks[1]['content']=[{'type':'text','text':'customers using ','styles':{}},
        {'type':'fact_field','text':'PostgreSQL','recordId':'technology','fieldKey':'display','bindingId':'binding',
         'syncedFactRevision':1,'styles':{}},{'type':'text','text':'.\n','styles':{}}]
    blocks[1]['provenance'].append({'kind':'field_binding','id':'field','recordId':'technology','fieldKey':'display'})
    source_text=[u.text for u in sources[0].units]
    result=format_blocks(sources,blocks)
    assert [text(b) for b in result]==['Built a service for multiple customers using PostgreSQL.','Duties:\n','Next item.']
    assert result[0]['type']=='bullet_list'
    assert next(s for s in result[0]['content'] if s['type']=='fact_field')['bindingId']=='binding'
    assert {s['unitId'] for p in result[0]['provenance'] if p['kind']=='source' for s in p['evidence']}=={'u0','u1'}
    assert [u.text for u in sources[0].units]==source_text


@pytest.mark.parametrize('boundary',['page','column','gap','group','bold','missing_geometry'])
def test_unproven_pdf_continuations_stay_separate(boundary):
    sources,blocks=fixture(['- Retain this item\n','Separate line\n'])
    unit=sources[0].units[1]
    if boundary=='page':unit.location.index=1
    if boundary=='column':unit.structure.bounds=[80,25,420,35]
    if boundary=='gap':unit.structure.bounds=[50,60,400,70]
    if boundary=='group':unit.structure.group=2
    if boundary=='bold':unit.structure.bold=True
    if boundary=='missing_geometry':unit.structure.bounds=None
    result=format_blocks(sources,blocks)
    assert len(result)==2 and text(result[1])=='Separate line\n'


def test_multiple_source_items_split_and_keep_explicit_number_starts_and_wrapped_words():
    sources,blocks=fixture(['5. First numbered\nwrapped sentence\n7) Second numbered\n'])
    result=format_blocks(sources,blocks)
    assert [text(b) for b in result]==['First numbered wrapped sentence','Second numbered']
    assert [b['props']['start'] for b in result]==[5,7]
    assert all(b['type']=='numbered_list' for b in result)
    assert len({b['id'] for b in result})==2


@pytest.mark.parametrize('value',['-X --option\n','-20 percent\n','2020. Employment\n','0. code index\n','Well-known system\n'])
def test_commands_dates_and_hyphenated_prose_are_not_list_markers(value):
    sources,blocks=fixture([value]);before=deepcopy(blocks)
    assert format_blocks(sources,blocks)==before


def test_a_bound_number_or_nested_children_cannot_be_discarded_by_marker_cleanup():
    sources,blocks=fixture(['5. Result\n'])
    blocks[0]['content']=[{'type':'fact_field','text':'5','recordId':'claim','fieldKey':'value','bindingId':'number',
        'syncedFactRevision':1,'styles':{}},{'type':'text','text':'. Result\n','styles':{}}]
    before=deepcopy(blocks);assert format_blocks(sources,blocks)==before
    sources,blocks=fixture(['- Parent\n- Another\n'])
    blocks[0]['children']=[{'id':'child','type':'paragraph','revision':1,'props':{},'provenance':[],
        'content':[{'type':'text','text':'Child','styles':{}}],'children':[]}]
    result=format_blocks(sources,blocks)
    assert len(result)==1 and len(result[0]['children'])==1


def test_native_word_bullet_style_does_not_need_a_literal_marker_and_preserves_manual_breaks():
    sources,blocks=fixture(['Native Word item\nmanual break\n'])
    sources[0].units[0].structure.list_level=0
    sources[0].units[0].structure.style='List Bullet'
    result=format_blocks(sources,blocks)
    assert result[0]['type']=='bullet_list'
    assert text(result[0])=='Native Word item\nmanual break\n'


def test_literal_nested_lists_keep_their_authored_indentation_instead_of_becoming_flat_items():
    sources,blocks=fixture(['- Parent\n  - Child\n    - Grandchild\n- Next\n'])
    before=deepcopy(blocks)
    assert format_blocks(sources,blocks)==before
