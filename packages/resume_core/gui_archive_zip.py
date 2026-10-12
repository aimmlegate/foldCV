"""Bounded ZIP structure checks shared by all portable-project versions."""

import hashlib
import json
import struct
import unicodedata
import zlib
from io import BytesIO
from zipfile import ZipFile, ZIP_STORED

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_TOTAL = 60 * 1024 * 1024
MAX_ENTRY = 32 * 1024 * 1024
MAX_JSON = 16 * 1024 * 1024
MAX_ENTRIES = 48


class ArchiveFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def safe_path(value):
    return isinstance(value,str) and 0 < len(value) <= 240 and not value.startswith('/') and not any(char in value for char in '\\:') and not any(ord(char)<32 or ord(char)==127 for char in value) and all(
        part and part not in {'.','..','__proto__','prototype','constructor'} and not part.endswith(('.', ' ')) for part in value.split('/'))


def alias(value):return unicodedata.normalize('NFC',value).casefold()


def digest(value):return hashlib.sha256(value).hexdigest()


def parse_json(data):
    if data is None or len(data)>MAX_JSON:raise ArchiveFailure('ARCHIVE_JSON_LIMIT')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError()
            result[key]=value
        return result
    def invalid(_value):raise ValueError()
    try:
        value=json.loads(data.decode('utf-8','strict'),object_pairs_hook=pairs,parse_constant=invalid)
        pending=[(value,0)]
        while pending:
            item,depth=pending.pop()
            if depth>128:raise ValueError()
            if isinstance(item,dict):pending.extend((entry,depth+1) for entry in item.values())
            elif isinstance(item,list):pending.extend((entry,depth+1) for entry in item)
        return value
    except (ValueError,UnicodeError,RecursionError):raise ArchiveFailure('ARCHIVE_INVALID_JSON') from None


def json_bytes(value):
    try:data=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
    except (ValueError,UnicodeError,RecursionError):raise ArchiveFailure('ARCHIVE_INVALID_JSON') from None
    if len(data)>MAX_JSON:raise ArchiveFailure('ARCHIVE_JSON_LIMIT')
    return data


def read_zip(data):
    def invalid():raise ArchiveFailure('ARCHIVE_INVALID_ZIP')
    if not isinstance(data,bytes) or len(data)<22 or len(data)>MAX_ARCHIVE:raise ArchiveFailure('ARCHIVE_SIZE_LIMIT')
    try:
        end=len(data)-22
        signature,disk,central_disk,disk_count,count,central_size,central_offset,comment=struct.unpack_from('<IHHHHIIH',data,end)
        if signature!=0x06054b50 or disk or central_disk or comment or disk_count!=count or not 2<=count<=MAX_ENTRIES or central_offset+central_size!=end:invalid()
        names=set();entries=[];central=central_offset;local=0;total=0
        for _ in range(count):
            if central+46>end:invalid()
            values=struct.unpack_from('<IHHHHHHIIIHHHHHII',data,central)
            sig,_made,_needed,flags,method,_time,_date,crc,compressed,expanded,name_len,extra_len,comment_len,start_disk,_internal,external,offset=values
            next=central+46+name_len+extra_len+comment_len
            if sig!=0x02014b50 or next>end or flags or method not in {0,8} or extra_len or comment_len or start_disk or _internal or external>>16 & 0xf000==0xa000 or offset!=local or not name_len:invalid()
            if expanded>MAX_ENTRY or compressed>MAX_ARCHIVE or method==0 and compressed!=expanded or (expanded if compressed==0 else expanded/compressed)>200:invalid()
            name=data[central+46:central+46+name_len].decode('utf-8','strict')
            if not safe_path(name) or alias(name) in names:invalid()
            names.add(alias(name))
            if local+30+name_len>central_offset:invalid()
            head=struct.unpack_from('<IHHHHHIIIHH',data,local)
            if head[0]!=0x04034b50 or (head[2],head[3],head[6],head[7],head[8],head[9],head[10])!=(flags,method,crc,compressed,expanded,name_len,0):invalid()
            if data[local+30:local+30+name_len]!=data[central+46:central+46+name_len]:invalid()
            begin=local+30+name_len;local=begin+compressed
            total+=expanded
            if local>central_offset or total>MAX_TOTAL:raise ArchiveFailure('ARCHIVE_EXPANDED_LIMIT')
            entries.append((name,begin,compressed,expanded,crc,method));central=next
        if central!=end or local!=central_offset:invalid()
        result={}
        for name,begin,compressed,expanded,crc,method in entries:
            value=data[begin:begin+compressed]
            if method==8:
                inflater=zlib.decompressobj(-15);parts=[];written=0
                for offset in range(0,len(value),1024):
                    chunk=inflater.decompress(value[offset:offset+1024],expanded-written+1)
                    written+=len(chunk)
                    if written>expanded or inflater.unconsumed_tail:invalid()
                    parts.append(chunk)
                if not inflater.eof or inflater.unused_data:invalid()
                value=b''.join(parts)
            if len(value)!=expanded or zlib.crc32(value)&0xffffffff!=crc:invalid()
            result[name]=value
        return result
    except ArchiveFailure:raise
    except (struct.error,UnicodeError,zlib.error,ValueError,OverflowError):raise ArchiveFailure('ARCHIVE_INVALID_ZIP') from None


def write_zip(files):
    if not 2<=len(files)<=MAX_ENTRIES:raise ArchiveFailure('ARCHIVE_ENTRY_LIMIT')
    if len({alias(name) for name in files})!=len(files) or any(not safe_path(name) for name in files):raise ArchiveFailure('ARCHIVE_INVALID_PATH')
    if any(len(data)>MAX_ENTRY for data in files.values()):raise ArchiveFailure('ARCHIVE_ENTRY_SIZE_LIMIT')
    if sum(map(len,files.values()))>MAX_TOTAL:raise ArchiveFailure('ARCHIVE_EXPANDED_LIMIT')
    output=BytesIO()
    with ZipFile(output,'w',compression=ZIP_STORED,allowZip64=False) as archive:
        for name,data in files.items():archive.writestr(name,data)
    value=output.getvalue();read_zip(value);return value
