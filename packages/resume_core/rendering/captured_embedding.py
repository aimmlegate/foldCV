"""Embed exact selected captured fonts without reading application or host assets."""

from io import BytesIO
from pathlib import PurePosixPath
import uuid
from zipfile import BadZipFile,ZipFile,ZipInfo,ZIP_DEFLATED

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from lxml import etree

from ..rich_limits import DOCX_BYTES
from ..templates.compiler import sha256
from .template import RenderFailure


REL_NS='http://schemas.openxmlformats.org/package/2006/relationships'
TYPE_NS='http://schemas.openxmlformats.org/package/2006/content-types'
FONT_TYPE='application/vnd.openxmlformats-officedocument.obfuscatedFont'
FACE_TAGS=('embedRegular','embedBold','embedItalic','embedBoldItalic')
SETTINGS_PREFIX=('writeProtection','view','zoom','removePersonalInformation','removeDateAndTime',
    'doNotDisplayPageBoundaries','displayBackgroundShape','printPostScriptOverText',
    'printFractionalCharacterWidth','printFormsData')


def obfuscate_font(content,key):
    if len(content)<32:raise RenderFailure('FONT_MISMATCH')
    mask=key.bytes[::-1]
    return bytes(value^mask[index%16] for index,value in enumerate(content[:32]))+content[32:]


def xml(content):
    parser=etree.XMLParser(resolve_entities=False,no_network=True)
    root=etree.fromstring(content,parser)
    if root.getroottree().docinfo.doctype:raise RenderFailure('RICH_RENDER_FAILED')
    return root


def set_setting(settings,name,value,preceding):
    for child in list(settings):
        if child.tag==qn('w:'+name):settings.remove(child)
    child=OxmlElement('w:'+name);child.set(qn('w:val'),value)
    allowed={qn('w:'+tag) for tag in preceding}
    index=next((index for index,existing in enumerate(settings) if existing.tag not in allowed),len(settings))
    settings.insert(index,child)


def embed_captured_fonts(raw,selections):
    if not 0<len(raw)<=DOCX_BYTES:raise RenderFailure('RENDER_OUTPUT_LIMIT')
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos=archive.infolist();names=[info.filename for info in infos]
            if len(set(names))!=len(names) or any(name.startswith('/') or '\\' in name
                    or '..' in PurePosixPath(name).parts for name in names):
                raise RenderFailure('RICH_RENDER_FAILED')
            if sum(info.file_size for info in infos)>DOCX_BYTES:raise RenderFailure('RENDER_OUTPUT_LIMIT')
            parts={name:archive.read(name) for name in names}
        table=xml(parts['word/fontTable.xml']);settings=xml(parts['word/settings.xml'])
        types=xml(parts['[Content_Types].xml'])
        rel_path='word/_rels/fontTable.xml.rels'
        relationships=xml(parts[rel_path]) if rel_path in parts else etree.Element('{'+REL_NS+'}Relationships')
        if (table.tag!=qn('w:fonts') or settings.tag!=qn('w:settings')
                or types.tag!='{'+TYPE_NS+'}Types' or relationships.tag!='{'+REL_NS+'}Relationships'):
            raise RenderFailure('RICH_RENDER_FAILED')
        identifiers={child.get('Id') for child in relationships}
        if len(identifiers)!=len(relationships) or any(not identifier for identifier in identifiers):
            raise RenderFailure('RICH_RENDER_FAILED')
        faces={};fonts={}
        for selected in selections:
            font=selected.font;rights=font.embedding_rights
            if (sha256(font.content)!=font.sha256 or len(font.content)<32 or rights&~0x030E
                    or rights&0x0202 or rights&0x000C in {0x0004,0x000C}):
                raise RenderFailure('FONT_MISMATCH')
            face=(font.family.casefold(),font.bold,font.italic)
            if face in faces and faces[face].sha256!=font.sha256:raise RenderFailure('FONT_MISMATCH')
            faces.setdefault(face,font);fonts.setdefault(font.sha256,font)
        if sum(len(font.content) for font in fonts.values())+sum(map(len,parts.values()))>DOCX_BYTES:
            raise RenderFailure('RENDER_OUTPUT_LIMIT')
        for face,font in sorted(faces.items()):
            found=[node for node in table if (node.get(qn('w:name')) or '').casefold()==face[0]]
            if len(found)>1:raise RenderFailure('FONT_MISMATCH')
            node=found[0] if found else OxmlElement('w:font')
            if not found:node.set(qn('w:name'),font.family);table.append(node)
            tag=FACE_TAGS[int(font.bold)+2*int(font.italic)]
            if node.find(qn('w:'+tag)) is not None:raise RenderFailure('FONT_MISMATCH')
            key=uuid.UUID(hex=font.sha256[:32]);target='fonts/'+font.sha256+'.odttf'
            embedded=obfuscate_font(font.content,key)
            if 'word/'+target in parts and parts['word/'+target]!=embedded:raise RenderFailure('FONT_MISMATCH')
            parts['word/'+target]=embedded
            identifier='rIdFoldCVCapturedFont1';index=1
            while identifier in identifiers:
                index+=1;identifier='rIdFoldCVCapturedFont'+str(index)
            identifiers.add(identifier)
            etree.SubElement(relationships,'{'+REL_NS+'}Relationship',Id=identifier,
                Type=RELATIONSHIP_TYPE.FONT,Target=target)
            child=OxmlElement('w:'+tag);child.set(qn('r:id'),identifier)
            child.set(qn('w:fontKey'),'{'+str(key).upper()+'}');child.set(qn('w:subsetted'),'0')
            later={qn('w:'+value) for value in FACE_TAGS[FACE_TAGS.index(tag)+1:]}
            position=next((index for index,existing in enumerate(node) if existing.tag in later),len(node))
            node.insert(position,child)
        declarations=[node for node in types if node.get('Extension','').lower()=='odttf']
        if len(declarations)>1 or any(node.get('ContentType')!=FONT_TYPE for node in declarations):
            raise RenderFailure('FONT_MISMATCH')
        if not declarations:etree.SubElement(types,'{'+TYPE_NS+'}Default',Extension='odttf',ContentType=FONT_TYPE)
        set_setting(settings,'embedTrueTypeFonts','1',SETTINGS_PREFIX)
        set_setting(settings,'saveSubsetFonts','0',(*SETTINGS_PREFIX,'embedTrueTypeFonts','embedSystemFonts'))
        for path,root in [('word/fontTable.xml',table),('word/settings.xml',settings),
                ('[Content_Types].xml',types),(rel_path,relationships)]:
            parts[path]=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
        if sum(map(len,parts.values()))>DOCX_BYTES:raise RenderFailure('RENDER_OUTPUT_LIMIT')
        output=BytesIO()
        with ZipFile(output,'w') as archive:
            for path,content in parts.items():
                info=ZipInfo(path,date_time=(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED
                archive.writestr(info,content)
        if len(output.getvalue())>DOCX_BYTES:raise RenderFailure('RENDER_OUTPUT_LIMIT')
        return output.getvalue()
    except (BadZipFile,KeyError,ValueError,etree.XMLSyntaxError,OSError):
        raise RenderFailure('RICH_RENDER_FAILED') from None
