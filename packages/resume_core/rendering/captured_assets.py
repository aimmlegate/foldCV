"""Decode used captured assets without consulting application or system assets."""

import base64
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import struct
from types import MappingProxyType
from typing import Mapping

from fontTools.ttLib import TTFont,TTLibError
from PIL import Image,UnidentifiedImageError

from ..rich_limits import IMAGE_PIXELS
from ..templates.store import verify_package
from .template import RenderFailure


@dataclass(frozen=True)
class CapturedFont:
    asset_id: str
    sha256: str
    content: bytes
    family: str
    full_name: str
    typographic_family: str
    weight: int
    bold: bool
    italic: bool
    units_per_em: int
    embedding_rights: int


@dataclass(frozen=True)
class CapturedLogo:
    asset_id: str
    sha256: str
    content: bytes
    width: int
    height: int


@dataclass(frozen=True)
class CapturedAssets:
    fonts: Mapping[str,CapturedFont]
    logo: CapturedLogo | None

    def materialize(self,worker_directory):
        directory=Path(worker_directory)
        if directory.is_symlink() or not directory.is_dir():raise RenderFailure('ASSET_UNAVAILABLE')
        root=directory/'captured-assets'
        try:
            root.mkdir(mode=0o700)
            paths={}
            for font in self.fonts.values():
                path=root/(font.sha256+'.ttf')
                if path not in paths.values():path.write_bytes(font.content);path.chmod(0o600)
                paths[font.asset_id]=path
            if self.logo is not None:
                path=root/(self.logo.sha256+'.png');path.write_bytes(self.logo.content);path.chmod(0o600)
                paths[self.logo.asset_id]=path
            return paths
        except OSError:
            raise RenderFailure('ASSET_UNAVAILABLE') from None


def font_name(table,identifier):
    ranked=[]
    for record in table.names:
        if record.nameID!=identifier:continue
        if record.platformID==3 and record.langID==0x0409:rank=0
        elif record.platformID==0 and record.langID==0:rank=1
        elif record.platformID==1 and record.langID==0:rank=2
        elif record.isUnicode():rank=3
        else:continue
        ranked.append(((rank,record.platformID,record.langID),record.toUnicode()))
    if not ranked:raise ValueError('font has no supported name record')
    chosen=min(key for key,_value in ranked)
    values={value for key,value in ranked if key==chosen}
    if len(values)!=1:raise ValueError('font name records conflict')
    value=values.pop()
    if not value.strip() or any(ord(character)<32 for character in value):raise ValueError('invalid font name')
    return value


def validate_truetype_headers(font):
    head,hhea,maxp=font['head'],font['hhea'],font['maxp']
    if (head.tableVersion!=1.0 or head.magicNumber!=0x5F0F3CF5
            or head.indexToLocFormat not in {0,1} or head.glyphDataFormat!=0):
        raise ValueError('unsupported TrueType font header')
    if (hhea.tableVersion!=0x00010000 or hhea.metricDataFormat!=0
            or any(getattr(hhea,'reserved'+str(index))!=0 for index in range(4))):
        raise ValueError('unsupported horizontal metrics header')
    if (maxp.tableVersion!=0x00010000 or maxp.numGlyphs<1 or maxp.maxZones not in {1,2}
            or not 1<=hhea.numberOfHMetrics<=maxp.numGlyphs):
        raise ValueError('unsupported TrueType glyph metrics')


def decode_font(asset,declaration):
    if (asset.role!='font' or asset.mime_type!='font/ttf' or declaration.embedding!='allowed'):
        raise RenderFailure('FONT_UNAVAILABLE')
    content=base64.b64decode(asset.bytes_base64,validate=True)
    if content[:4] not in {b'\x00\x01\x00\x00',b'true'}:
        raise RenderFailure('FONT_MISMATCH')
    try:
        with TTFont(BytesIO(content),checkChecksums=2,lazy=False) as font:
            if not {'head','hhea','hmtx','maxp','cmap','name','OS/2','glyf','loca'}<=set(font.keys()):
                raise ValueError('font has no TrueType outline tables')
            font.ensureDecompiled(recurse=True)
            validate_truetype_headers(font)
            rights=font['OS/2'].fsType
            if (rights&~0x030E or rights&0x0202 or rights&0x000C==0x0004
                    or rights&0x000C==0x000C):
                raise ValueError('font does not permit editable outline embedding')
            family=font_name(font['name'],1);full_name=font_name(font['name'],4)
            font_name(font['name'],2)
            typographic_family=(font_name(font['name'],16)
                if any(record.nameID==16 for record in font['name'].names) else family)
            weight=font['OS/2'].usWeightClass
            if not 1<=weight<=1000 or 'fvar' in font:
                raise ValueError('unsupported static font weight')
            bold,italic=bool(font['OS/2'].fsSelection&0x20),bool(font['OS/2'].fsSelection&0x01)
            if (bold!=bool(font['head'].macStyle&1) or italic!=bool(font['head'].macStyle&2)):
                raise ValueError('font style flags conflict')
            units=font['head'].unitsPerEm
            if not 16<=units<=16384 or not font.getBestCmap():
                raise ValueError('font identity or metrics are invalid')
            return CapturedFont(asset.id,asset.sha256,content,family,full_name,typographic_family,
                weight,bold,italic,units,rights)
    except (TTLibError,ValueError,KeyError,IndexError,struct.error,AssertionError,OverflowError,UnicodeError):
        raise RenderFailure('FONT_MISMATCH') from None


def decode_logo(asset):
    if asset.role!='logo' or asset.mime_type!='image/png':raise RenderFailure('ASSET_MISMATCH')
    content=base64.b64decode(asset.bytes_base64,validate=True)
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format!='PNG' or image.width*image.height>IMAGE_PIXELS:raise ValueError('invalid logo')
            image.verify()
        with Image.open(BytesIO(content)) as image:
            image.load();width,height=image.size
        return CapturedLogo(asset.id,asset.sha256,content,width,height)
    except (OSError,ValueError,UnidentifiedImageError,Image.DecompressionBombError):
        raise RenderFailure('ASSET_MISMATCH') from None


def load_captured_assets(package,font_tokens,logo_asset_id=None):
    verify_package(package)
    assets={asset.id:asset for asset in package.assets}
    declarations={asset.id:asset for asset in package.definition.assets}
    fonts={};faces={};decoded={}
    for token in sorted(set(font_tokens)):
        identifier=package.recipe.style.fonts.get(token)
        if identifier is None or identifier not in assets:raise RenderFailure('FONT_UNAVAILABLE')
        if identifier not in decoded:decoded[identifier]=decode_font(assets[identifier],declarations[identifier])
        font=decoded[identifier]
        face=(font.family.casefold(),font.bold,font.italic)
        if face in faces and faces[face]!=font.sha256:raise RenderFailure('FONT_MISMATCH')
        faces[face]=font.sha256;fonts[token]=font
    logo=None
    if logo_asset_id is not None:
        if logo_asset_id not in assets:raise RenderFailure('ASSET_UNAVAILABLE')
        logo=decode_logo(assets[logo_asset_id])
    return CapturedAssets(MappingProxyType(fonts),logo)
