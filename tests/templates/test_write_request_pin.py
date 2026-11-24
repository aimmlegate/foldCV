"""The import's write request is pinned byte for byte (F6a): the editor's «Написать заново по резюме» shares its
checks and parts, and a change of them must not change what the import sends. The request is built for the stored
promotions run, the first call and the call after a refusal, in both envelope forms."""

import hashlib
import json

import pytest

from resume_api.importer import lite_import
from tests.templates.test_lite_import import StoredCalls, lite_run

SCHEMA_BOTH = 'cf3ffb4c60c1a3e6c5d8f39e24d0d4066f3add0964e616223f5c2fc2b4e0a3ef'
SCHEMA_SUMMARY = 'c71503202faab9d13c8504333c8af46a495a9407b45aab4f4ca2a54a8c3d729e'
PINNED = {
    (False, 'first'): ('4ea72890de1757cbdcb4111ada76a8ef7aed83823382f1a6900b44fa9b4a4668', SCHEMA_BOTH),
    (False, 'refused'): ('abe32f8b83218bb30d8226b0e90167430f1e0a0e3476eb83b9cd02b0f2d04159', SCHEMA_SUMMARY),
    (True, 'first'): ('3a608b7ec2e38a6bf25a45de5ca5b949bd06bd7322ebb8449646fc2e92221aed', SCHEMA_BOTH),
    (True, 'refused'): ('5c0e3aa998ce185412ca7580cef2c69fb6af45ea41dc45bed2497ab45ca25fa1', SCHEMA_SUMMARY),
}


@pytest.fixture(scope='module')
def promotions(tmp_path_factory):
    return lite_run(tmp_path_factory.mktemp('promotions-pin'), 'promotions')


class Seen(StoredCalls):
    def __init__(self, name):
        super().__init__(name)
        self.asked = []

    def call(self, kind, block, prompt, schema):
        if kind == 'write':
            self.asked.append((prompt, json.dumps(schema, ensure_ascii=False, sort_keys=True)))
        return super().call(kind, block, prompt, schema)


def asked(promotions, envelope):
    from packages.resume_core.importing.lite.scheme import Import
    fixture = promotions[0]
    calls = Seen('promotions')
    good = calls.replies[('write', 'write')][0]
    # The first summary mixes two alphabets, so code refuses it and asks once more.
    calls.replies[('write', 'write')] = [
        {'reply': {'summary': {'text': 'Руководитель группы разрабoтки.', 'lines': ['S2']},
                   'career_highlights': good['reply']['career_highlights']}, 'usage': [10, 0, 5]},
        {'reply': {'summary': good['reply']['summary']}, 'usage': [10, 0, 5]}]
    package = fixture.current().project.template_package
    Import(fixture.current().project.sources, calls, envelope=envelope, writing=lite_import.writing_rules(package)).run()
    return calls.asked


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize('envelope', [False, True])
def test_the_imports_write_request_and_schema_stay_byte_for_byte_the_same(promotions, envelope):
    (first, first_schema), (again, again_schema) = asked(promotions, envelope)
    assert (sha(first), sha(first_schema)) == PINNED[(envelope, 'first')]
    assert (sha(again), sha(again_schema)) == PINNED[(envelope, 'refused')]
