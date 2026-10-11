"""Reject misleading source matches and render only checked archives."""

import importlib.util
import json
from datetime import date
from pathlib import Path
import sys

import pytest

import test_policy
from archive import source_units
from check_archive import check, dates_in, observation_supported
from extract import extract


@pytest.fixture
def case():
    example = test_policy.PolicyTests("test_valid_case")
    example.setUp()
    try:
        yield example
    finally:
        example.doCleanups()


def replace_unit(case, uid, text):
    texts = [text if unit['id'] == uid else unit['text'] for unit in case.archive['units']]
    snapshot = case.folder / case.archive['source_snapshot']
    snapshot.write_text('\n\n'.join(texts))
    case.archive['source'] = extract(snapshot)
    case.archive['units'] = source_units(case.archive['source'])
    (case.folder / 'source.json').write_text(json.dumps(case.archive['source']))


@pytest.mark.parametrize('text', ['marketing 2020', 'мартынов 2020', 'maybe 2020', 'marching 2020'])
def test_month_names_do_not_match_word_prefixes(text):
    assert dates_in(text) == set()


@pytest.mark.parametrize(('text', 'month'), [
    ('January 2020', '01'), ('Jan. 2020', '01'), ('марта 2020', '03'),
    ('Mar 2020', '03'), ('May 2020', '05'), ('сентября 2020', '09'), ('Sept. 2020', '09'),
])
def test_complete_month_names_and_abbreviations_remain_supported(text, month):
    assert dates_in(text) == {'2020-' + month}


@pytest.mark.parametrize('bound', ['job', 'technology'])
def test_year_substring_cannot_support_normalized_date(case, bound):
    replace_unit(case, 'u0003', 'Reference 120203; December 2022')
    job = case.archive['jobs'][0]
    job['start'] = '2020' if bound == 'job' else '2022-12'
    if bound == 'technology':
        job['technologies'][0].update(start='2020', sources=['u0003'])
    case.finish()
    with pytest.raises(ValueError, match='normalized start|unsupported subproject date'):
        check(case.view, case.archive, case.path)


@pytest.mark.parametrize('text', ['March 2023; team of 2', 'March 2023; team of 12',
                                 'March 2023; version 120203', '2023-03-12'])
def test_unrelated_number_cannot_support_observation_day(text):
    assert not observation_supported(text, date(2023, 3, 2))


@pytest.mark.parametrize('text', ['2 марта 2023', '02 March 2023', 'March 2, 2023',
                                 '02.03.2023', '2/3/2023', '2023-03-02'])
def test_complete_observation_dates_are_supported(text):
    assert observation_supported(text, date(2023, 3, 2))


def test_archive_rejects_unrelated_observation_day(case):
    replace_unit(case, 'u0003', 'January 2020 — present. March 2023; team of 2')
    case.archive['jobs'][0].update(end=None, observed_at='2023-03-02', observed_sources=['u0003'])
    case.finish()
    with pytest.raises(ValueError, match='observation date not supported'):
        check(case.view, case.archive, case.path)


@pytest.mark.parametrize(('name', 'text'), [('Redis', 'redistribute'), ('PHP', 'PHPUnit'),
                                          ('C++', 'C++Builder'), ('.NET', 'ASP.NETCore')])
def test_technology_substring_is_not_visible_coverage(case, name, text):
    case.archive['global_technologies'] = [{'name': name, 'sources': ['u0004']}]
    case.view['candidate']['summary']['text'] += ' ' + text
    case.finish()
    with pytest.raises(ValueError, match='Technologies not displayed'):
        check(case.view, case.archive, case.path)
    case.view['archived_technologies'] = [{'name': name, 'reason': 'Keep in the archive.'}]
    check(case.view, case.archive, case.path)


@pytest.mark.parametrize('name', ['Redis', 'PHP', 'C++', '.NET', 'Node.js'])
def test_punctuated_technology_names_can_be_displayed(case, name):
    case.archive['global_technologies'] = [{'name': name, 'sources': ['u0004']}]
    case.view['candidate']['summary']['text'] += ' (' + name + ').'
    case.finish()
    check(case.view, case.archive, case.path)


@pytest.mark.parametrize('outside', [False, True])
def test_snapshot_symlink_is_rejected_even_when_bytes_match(case, outside):
    snapshot = case.folder / case.archive['source_snapshot']
    target = (case.folder.parent if outside else case.folder) / 'copy.txt'
    target.write_bytes(snapshot.read_bytes())
    snapshot.unlink()
    snapshot.symlink_to(target)
    with pytest.raises(ValueError, match='regular file inside the case folder'):
        check(case.view, case.archive, case.path)


def test_snapshot_resolved_path_cannot_escape_through_parent_link(case):
    outside = case.folder.parent / 'outside'
    outside.mkdir()
    (outside / 'copy.txt').write_bytes((case.folder / case.archive['source_snapshot']).read_bytes())
    (case.folder / 'linked').symlink_to(outside, target_is_directory=True)
    case.archive['source_snapshot'] = 'linked/copy.txt'
    case.finish()
    with pytest.raises(ValueError, match='regular file inside the case folder'):
        check(case.view, case.archive, case.path)


@pytest.mark.parametrize('version', [2, '2', None])
def test_render_cli_requires_archive_check_for_every_version(case, monkeypatch, version):
    path = Path(__file__).resolve().parents[1] / 'scripts/render.py'
    spec = importlib.util.spec_from_file_location('archive_render', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if version is None:
        case.view.pop('schema_version')
    else:
        case.view['schema_version'] = version
    view_path = case.folder / 'view.json'
    view_path.write_text(json.dumps(case.view))
    output = case.folder / 'output.pdf'
    monkeypatch.setattr(sys, 'argv', [str(path), str(view_path), str(output), '--source',
                                    str(case.folder / 'source.json'), '--archive', str(case.path)])
    monkeypatch.setattr(module, 'render', lambda data, target: target.write_bytes(b'checked'))
    if version is None:
        with pytest.raises(ValueError, match='Version 2 required'):
            module.main()
        assert not output.exists()
    else:
        module.main()
        assert output.read_bytes() == b'checked'
        case.view['coverage'].pop('u0004')
        view_path.write_text(json.dumps(case.view))
        output.unlink()
        with pytest.raises(ValueError, match='Coverage must account'):
            module.main()
        assert not output.exists()
