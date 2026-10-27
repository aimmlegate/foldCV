"""The bounded ZIP codec (archive_zip): unsafe structure and explicit capacity failures, without filesystem extraction."""

from io import BytesIO
import struct
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from packages.resume_core import archive_zip as codec
from packages.resume_core.template_archive import archive_payload_v7
from tests.templates.storage_fixtures import workspace as papers


@pytest.mark.parametrize('name', ['../outside', '/outside', 'a\\b', 'a:b', 'a//b', 'a/./b', 'a/../b', 'a/constructor/b',
    'a/__proto__/b', 'a.', 'a ', 'a\x00b'])
def test_unsafe_names_are_rejected_before_write(name):
    with pytest.raises(codec.ArchiveFailure):
        codec.write_zip({'manifest.json': b'{}', name: b'private'})


@pytest.mark.parametrize('change', ['flags', 'symlink', 'offset', 'crc', 'count', 'central_name', 'trailing', 'compression'])
def test_malformed_zip_structure_or_crc_is_rejected(change):
    data = bytearray(codec.write_zip({'a.txt': b'data', 'b.txt': b'data'}))
    central = struct.unpack_from('<I', data, len(data) - 6)[0]
    if change == 'flags':
        struct.pack_into('<H', data, central + 8, 1)
    elif change == 'symlink':
        struct.pack_into('<I', data, central + 38, 0xa000 << 16)
    elif change == 'offset':
        struct.pack_into('<I', data, central + 42, 1)
    elif change == 'crc':
        data[35] ^= 1
    elif change == 'count':
        struct.pack_into('<H', data, len(data) - 12, 1)
    elif change == 'central_name':
        data[central + 46] = ord('x')
    elif change == 'trailing':
        data += b'x'
    else:
        struct.pack_into('<H', data, central + 10, 12)
    with pytest.raises(codec.ArchiveFailure):
        codec.read_zip(bytes(data))


def test_case_and_unicode_aliases_reject_before_decode():
    for names in [('A.txt', 'a.txt'), ('é.txt', 'é.txt')]:
        with pytest.raises(codec.ArchiveFailure):
            codec.write_zip({name: b'data' for name in names})


def test_deflate_ratio_and_lied_expansion_size_reject_bounded_inflate():
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr('a.txt', b'a' * 100000)
        archive.writestr('b.txt', b'other')
    with pytest.raises(codec.ArchiveFailure):
        codec.read_zip(output.getvalue())
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr('a.txt', bytes(range(256)) * 20)
        archive.writestr('b.txt', b'other')
    data = bytearray(output.getvalue())
    central = struct.unpack_from('<I', data, len(data) - 6)[0]
    struct.pack_into('<I', data, central + 24, 100)
    struct.pack_into('<I', data, 22, 100)
    with pytest.raises(codec.ArchiveFailure):
        codec.read_zip(bytes(data))


@pytest.mark.parametrize('data', [b'{"key":1,"key":2}', b'{"value":NaN}', b'{"value":Infinity}', b'\xff', b'[' * 2000 + b']' * 2000])
def test_invalid_json_duplicate_keys_nonfinite_utf8_or_depth_reject(data):
    with pytest.raises(codec.ArchiveFailure):
        codec.parse_json(data)


@pytest.mark.parametrize('limit,code', [('MAX_ENTRY', 'ARCHIVE_ENTRY_SIZE_LIMIT'), ('MAX_TOTAL', 'ARCHIVE_EXPANDED_LIMIT'),
    ('MAX_ARCHIVE', 'ARCHIVE_SIZE_LIMIT'), ('MAX_JSON', 'ARCHIVE_JSON_LIMIT')])
def test_capacity_failures_of_a_v7_export_are_explicit_and_keep_the_workspace(monkeypatch, limit, code):
    workspace, originals = papers()
    before = workspace.model_dump()
    monkeypatch.setattr(codec, limit, 10)
    with pytest.raises(codec.ArchiveFailure, match=code):
        codec.write_zip(archive_payload_v7(workspace, originals, {}))
    assert workspace.model_dump() == before


def test_the_entry_bound_accepts_48_files_then_rejects_one_more_original_without_loss():
    workspace, originals = papers()
    source = workspace.project.sources[0]

    def add_source(identifier):
        extra = source.model_copy(deep=True)
        extra.id, extra.byte_ref = identifier, 'sources/' + identifier + '.txt'
        workspace.project.sources.append(extra)
        originals[identifier] = originals[source.id]
    for index in range(codec.MAX_ENTRIES - len(archive_payload_v7(workspace, originals, {}))):
        add_source('extra-' + str(index))
    assert len(codec.read_zip(codec.write_zip(archive_payload_v7(workspace, originals, {})))) == codec.MAX_ENTRIES
    add_source('extra-limit')
    before = workspace.model_dump()
    # The V7 manifest model bounds its entries, so the payload refuses before the codec counts files.
    with pytest.raises(codec.ArchiveFailure, match='ARCHIVE_CAPACITY_LIMIT'):
        codec.write_zip(archive_payload_v7(workspace, originals, {}))
    with pytest.raises(codec.ArchiveFailure, match='ARCHIVE_ENTRY_LIMIT'):
        codec.write_zip({str(index) + '.txt': b'x' for index in range(codec.MAX_ENTRIES + 1)})
    assert workspace.model_dump() == before
