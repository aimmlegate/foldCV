"""Rename and archive flags update the registry and write no journal line (plan SR04)."""

from tests.projects.support import Editor, v2_app
from tests.templates.storage_fixtures import workspace as papers


PROJECT = 'template-project'


def journal_bytes(repository):
    path = repository.open(PROJECT).directory / 'history.jsonl'
    return path.read_bytes() if path.is_file() else None


def test_rename_and_archive_flags_do_not_journal(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        service = application.state.projects
        editor = Editor(client, PROJECT)
        before = journal_bytes(service.repository)
        renamed = editor.call('post', '/rename', {'editorToken': editor.token, 'baseRevision': editor.revision,
            'title': 'Manual title'})
        assert renamed['workspace']['title'] == 'Manual title'
        assert renamed['workspace']['titleManuallySet'] is True
        assert renamed['identity']['title'] == 'Manual title'
        listed = client.get('/v2/projects').json()
        entry = next(item for item in listed['entries'] if item['projectId'] == PROJECT)
        assert entry['title'] == 'Manual title' and entry['archived'] is False
        archived = client.post('/v2/projects/' + PROJECT + '/catalog/archive', json={})
        assert archived.status_code == 200, archived.text[:300]
        assert next(item for item in archived.json()['entries'] if item['projectId'] == PROJECT)['archived'] is True
        restored = client.post('/v2/projects/' + PROJECT + '/restore', json={})
        assert next(item for item in restored.json()['entries'] if item['projectId'] == PROJECT)['archived'] is False
        service.set_formatting_date(PROJECT, {'precision': 'day', 'year': 2026, 'month': 1, 'day': 2})
        current = service.repository.read(PROJECT)
        assert current.formatting_as_of.year == 2026 and current.formatting_as_of.month == 1
        assert journal_bytes(service.repository) == before
