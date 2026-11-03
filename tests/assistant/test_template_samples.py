"""TS4b: a sample DOCX or PDF read once by the extraction worker, its summary in memory (three at most), and the run
that reads it. The summary builder is lane C's; these tests stand in for it."""

from pathlib import Path

from packages.resume_core.extraction.models import ExtractResult
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from resume_api.assistant import template_tools
from tests.assistant.support import assistant_app
from tests.assistant.template_support import (TBASE, template_conversation, template_finish, template_start,
    upload_sample, using)

TEXT = BUNDLED_TEMPLATE.read_text(encoding='utf-8')
FIXTURES = Path('tests/fixtures/synthetic/import')


def stub_summary(result):
    assert isinstance(result, ExtractResult)
    return {'name': 'fixture', 'pages': 1, 'unitCount': len(result.units), 'listed': 0, 'units': [], 'gaps': []}


def test_the_worker_reads_a_docx_and_a_pdf_and_the_reply_names_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(template_tools, 'summarize', stub_summary)
    with assistant_app(tmp_path) as (client, _application, _runtime):
        for name in ('rich.docx', 'mixed-columns.pdf'):
            reply = upload_sample(client, (FIXTURES / name).read_bytes(), name)
            assert reply.status_code == 201, reply.text[:300]
            body = reply.json()
            assert set(body) == {'sampleId', 'name', 'pages', 'unitCount'} and body['name'] == name
            assert body['unitCount'] > 0 and body['sampleId'].startswith('sample_')
        # A damaged DOCX ends in the worker; a text file is not a sample.
        damaged = upload_sample(client, b'PK\x03\x04' + b'\0' * 64, 'broken.docx')
        assert damaged.status_code == 422 and damaged.json()['error']['code'].startswith('EXTRACT_')
        text = upload_sample(client, b'plain text', 'notes.txt')
        assert (text.status_code, text.json()['error']['code']) == (422, 'EXTRACT_UNSUPPORTED')
        large = upload_sample(client, b'%PDF-' + b'0' * (10 * 1024 * 1024), 'large.pdf')
        assert (large.status_code, large.json()['error']['code']) == (413, 'INPUT_TOO_LARGE')
        pasted = client.post(TBASE + '/samples', files={'paste': ('pasted.txt', b'%PDF-1.4', 'text/plain')})
        assert pasted.status_code == 422


def test_three_samples_are_kept_and_a_run_reads_its_own(tmp_path, monkeypatch):
    async def extracted(_data, name, _pasted, _files):
        return ExtractResult.model_construct(units=[])

    def summary(_result):
        return {'name': 'x', 'pages': 2, 'unitCount': 7, 'listed': 1, 'units': [{'column': 0, 'group': 0, 'heading': 1,
            'style': 'Heading 1', 'size': 14.0, 'bold': True, 'list': None, 'text': 'Опыт'}], 'gaps': []}
    monkeypatch.setattr(template_tools, 'run_extract', extracted)
    monkeypatch.setattr(template_tools, 'summarize', summary)
    seen = {}

    async def steps(tools, value, _cancel, _emit):
        seen['prompt'] = value.prompt
        seen['sample'] = await tools.call('read_sample')
        return 'Готово.'
    with assistant_app(tmp_path) as (client, application, runtime):
        using(runtime, steps)
        ids = [upload_sample(client, b'PK\x03\x04 docx', f'sample-{index}.docx').json()['sampleId'] for index in range(4)]
        assert list(application.state.template_assistant.scope.samples) == ids[1:]
        cid = template_conversation(client)
        refused = template_start(client, cid, TEXT, sample_id=ids[0], status=404)
        assert refused['error']['code'] == 'SAMPLE_NOT_FOUND'
        assert client.get(TBASE + f'/conversations/{cid}/messages').json()['runs'] == []
        run = template_start(client, cid, TEXT, sample_id=ids[3])
        assert template_finish(client, run)[0]['state'] == 'completed'
        assert seen['sample'] == summary(None)
        assert '"name":"sample-3.docx"' in seen['prompt'] and 'Опыт' not in seen['prompt']
        monkeypatch.setattr(template_tools, 'summarize', lambda _result: {'units': ['x' * 40000]})
        oversized = upload_sample(client, b'%PDF-1.7', 'big.pdf')
        assert (oversized.status_code, oversized.json()['error']['code']) == (422, 'EXTRACT_TEXT_LIMIT')
        scope = application.state.template_assistant.scope
    # Samples live in memory only and go with the service.
    assert scope.samples == {}
