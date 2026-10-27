"""POST /v1/rich/projects/template-input with an unreadable file: the exact bytes and the failure survive a restart, and
an import start is refused before any model call."""

from tests.projects.support import v2_app
from tests.support.generation import CreationProvider


def test_a_failed_extraction_keeps_the_original_and_its_warnings_and_refuses_the_import(tmp_path):
    provider = CreationProvider()
    with v2_app(tmp_path, template_import_call_cap=4, content_provider=provider) as (client, _application):
        created = client.post('/v1/rich/projects/template-input', files={'file': ('broken.pdf', b'broken PDF bytes', 'application/pdf')})
        assert created.status_code == 201, created.text[:300]
        workspace = created.json()['workspace']
        project, pre = workspace['projectId'], workspace['preDraft']
        assert pre['selectedInput'] == 'file' and 'NO_USABLE_TEXT' in pre['warnings']
    with v2_app(tmp_path, template_import_call_cap=4, content_provider=provider) as (client, _application):
        reopened = client.get('/v2/projects/' + project).json()['workspace']['preDraft']
        assert reopened['warnings'] == pre['warnings']
        original = client.get('/v2/projects/' + project + '/sources/' + pre['selectedSourceId'] + '/original')
        assert original.status_code == 200 and original.content == b'broken PDF bytes'
        started = client.post('/v2/projects/' + project + '/import', json={'kind': 'start', 'clientRequestId': 'import-1'})
        assert started.status_code == 202, started.text[:300]
        task = next(item for item in client.get('/v2/projects/' + project + '/tasks').json()['tasks'] if item['id'] == started.json()['id'])
        assert task['state'] == 'failed' and task['error'] == 'NO_USABLE_TEXT'
    assert provider.calls == []
