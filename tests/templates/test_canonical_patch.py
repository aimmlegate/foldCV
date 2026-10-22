"""Exact structural patches reject ambiguity and avoid unchanged large payloads."""

from copy import deepcopy
import random

import pytest

from packages.resume_core.canonical_patch import apply_patch, build_patch
from packages.resume_core.templates.compiler import canonical, sha256


def wire(steps):
    return [step.model_dump(mode='json', by_alias=True) for step in steps]


def test_one_character_edit_keeps_large_provenance_and_unrelated_blocks_out_of_patch():
    before = {'document': [{'id': str(index), 'text': 'A' * 10000, 'provenance': 'P' * (1024 * 1024) if index == 0 else ''}
        for index in range(120)], 'bigInteger': 9007199254740993, 'float': 1e+30}
    after = deepcopy(before); after['document'][0]['text'] = 'A😀' + 'A' * 9998
    patch = build_patch(before, after)
    assert len(canonical(wire(patch))) < 300
    assert wire(patch) == [{'kind': 'splice_text', 'pointer': '/document/0/text',
        'beforeTextHash': sha256(('A' * 10000).encode()), 'start': 1, 'end': 2, 'text': '😀'}]
    assert apply_patch(before, patch) == after and before['document'][0]['text'] == 'A' * 10000


@pytest.mark.parametrize(('before', 'after'), [
    ({'a/~': {'': [1, 2, 3]}}, {'a/~': {'': [0, 1, 3, 4]}}),
    ({'a': 'A😀B'}, {'a': 'A😎C'}),
    ({'a': [1, 1, 2]}, {'a': [1, 2, 1]}),
    ({'a': [{'id': 'a', 'text': 'old'}, {'id': 'b'}]}, {'a': [{'id': 'b'}, {'id': 'a', 'text': 'new'}]}),
    ({'a': [{'id': 'x'}, {'id': 'x', 'value': 1}]}, {'a': [{'id': 'x', 'value': 2}, {'id': 'x'}]}),
    ({'a': [False, 1.0, 1]}, {'a': [1, True, None]}),
    ({'a': [0, 1, 2, 3]}, {'a': [1, 3, 2, 0]}),
    ({'a': []}, {'a': [1, {'id': 'new'}]}),
    ({'a': [1]}, {'a': []}),
])
def test_forward_inverse_are_exact_and_deterministic(before, after):
    patch = build_patch(before, after)
    assert canonical(apply_patch(before, patch)) == canonical(after)
    assert wire(patch) == wire(build_patch(before, after))
    assert canonical(apply_patch(after, build_patch(after, before))) == canonical(before)


def test_array_reorder_tie_and_changed_explicit_ids_have_fixed_structural_output():
    before = {'a': [{'id': 'a', 'text': 'old'}, {'id': 'b'}]}
    after = {'a': [{'id': 'b'}, {'id': 'a', 'text': 'new'}]}
    assert wire(build_patch(before, after)) == [
        {'kind': 'remove', 'pointer': '/a/0'},
        {'kind': 'insert', 'pointer': '/a/1', 'valueWire': '{"id":"a","text":"new"}'}]
    assert [step['kind'] for step in wire(build_patch({'a': [{'id': 'old'}]}, {'a': [{'id': 'new'}]}))] == ['remove', 'insert']


@pytest.mark.parametrize('steps', [
    [{'kind': 'set', 'pointer': '', 'valueWire': '{}'}],
    [{'kind': 'set', 'pointer': 'a', 'valueWire': '1'}],
    [{'kind': 'set', 'pointer': '/a~2', 'valueWire': '1'}],
    [{'kind': 'set', 'pointer': '/a/-', 'valueWire': '1'}],
    [{'kind': 'set', 'pointer': '/a/01', 'valueWire': '1'}],
    [{'kind': 'set', 'pointer': '/missing/child', 'valueWire': '1'}],
    [{'kind': 'insert', 'pointer': '/a', 'valueWire': '1'}],
    [{'kind': 'remove', 'pointer': '/missing'}],
    [{'kind': 'set', 'pointer': '/a', 'valueWire': '{"x":1,"x":2}'}],
    [{'kind': 'set', 'pointer': '/a', 'valueWire': '{ "x":1}'}],
    [{'kind': 'set', 'pointer': '/a', 'valueWire': 'NaN'}],
    [{'kind': 'set', 'pointer': '/a', 'valueWire': '1e999'}],
    [{'kind': 'set', 'pointer': '/a', 'valueWire': '"\\ud800"'}],
    [{'kind': 'set', 'pointer': '/a/0/x', 'valueWire': '1'}, {'kind': 'remove', 'pointer': '/a/0'}],
    [{'kind': 'set', 'pointer': '/a', 'valueWire': '[]'}, {'kind': 'insert', 'pointer': '/a/0', 'valueWire': '1'}],
    [{'kind': 'set', 'pointer': '/a/0/x', 'valueWire': '1'}, {'kind': 'set', 'pointer': '/a/0/x', 'valueWire': '2'}],
    [{'kind': 'remove', 'pointer': '/a/0'}, {'kind': 'remove', 'pointer': '/a/0'}],
    [{'kind': 'insert', 'pointer': '/a/0', 'valueWire': '{}'}, {'kind': 'set', 'pointer': '/a/0/x', 'valueWire': '1'}],
    [{'kind': 'insert', 'pointer': '/a/0', 'valueWire': '1'}, {'kind': 'insert', 'pointer': '/a/0', 'valueWire': '2'}],
])
def test_invalid_patch_cannot_modify_the_base(steps):
    before = {'a': [{'x': 0}, {'x': 0}]}
    original = deepcopy(before)
    with pytest.raises((ValueError, UnicodeError)):
        apply_patch(before, steps)
    assert before == original


@pytest.mark.parametrize(('start', 'end', 'digest'), [(1, 2, None), (0, 4, '0' * 64), (0, 5, None)])
def test_text_splice_checks_utf16_and_exact_hash(start, end, digest):
    with pytest.raises(ValueError):
        apply_patch({'a': '😀AB'}, [{'kind': 'splice_text', 'pointer': '/a',
            'beforeTextHash': digest or sha256('😀AB'.encode()), 'start': start, 'end': end, 'text': 'x'}])


def test_seeded_array_edits_round_trip_without_unbounded_alignment():
    randomizer = random.Random(405)
    for _ in range(100):
        before = {'a': [{'id': str(index), 'text': str(index)} for index in range(8)]}
        after = deepcopy(before)
        randomizer.shuffle(after['a'])
        after['a'] = after['a'][:randomizer.randrange(9)]
        after['a'].insert(randomizer.randrange(len(after['a']) + 1), {'id': 'new', 'text': 'new'})
        for value in after['a']:
            value['text'] += '😀'
        assert apply_patch(before, build_patch(before, after)) == after
