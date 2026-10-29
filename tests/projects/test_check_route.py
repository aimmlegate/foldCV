"""POST /v2/projects/{id}/check: the assistant's deterministic check over the committed workspace, behind the editor
token, with no write and no model call."""

from packages.resume_core.assistant_compiler import container_text
from tests.projects.support import Editor, v2_app
from tests.support.foundation import ForbiddenContentProvider
from tests.templates.storage_fixtures import workspace as papers
from tests.templates.test_template_preparation import command


def stored(application, project_id):
    return (application.state.projects.repository.root / 'projects' / project_id / 'workspace.json').read_bytes()


def test_a_clean_project_reports_nothing_and_writes_nothing(tmp_path):
    value, sources = papers()
    with v2_app(tmp_path, [(value, sources)], content_provider=ForbiddenContentProvider()) as (client, application):
        editor = Editor(client, value.project_id)
        before = stored(application, value.project_id)
        report = editor.call('post', '/check', {'editorToken': editor.token})
        assert report['emptyBlocks'] == [] and report['linksWithoutTarget'] == [] and report['openImportIssues'] == []
        assert report['projectRevision'] == editor.revision
        assert report['documentRevision'] == editor.response['workspace']['documentRevision']
        assert 'semanticReview' not in report
        assert stored(application, value.project_id) == before
        assert editor.call('get', '')['workspace']['projectRevision'] == editor.revision


def test_the_check_reads_the_committed_state_after_an_edit(tmp_path):
    value, sources = papers()
    with v2_app(tmp_path, [(value, sources)]) as (client, _application):
        editor = Editor(client, value.project_id)
        first = editor.workspace().project.document.regions[2].blocks[0]
        length = len(container_text(first.content).encode('utf-16-le')) // 2
        emptied = command(editor.workspace(), start=0, end=length, text='')
        emptied.client_mutation_id = emptied.capture.action_id = 'empty-first'
        editor.edit(emptied.model_dump(mode='json', by_alias=True))
        report = editor.call('post', '/check', {'editorToken': editor.token})
        assert report['emptyBlocks'] == [first.id]
        assert report['projectRevision'] == editor.revision == 2


def test_open_import_issues_are_named_with_their_blocks_and_retired_ones_are_not(tmp_path):
    from tests.templates.test_materialize import issue_workspace
    value, sources = issue_workspace()
    retired = value.project.import_issues[1]
    retired.state, retired.retired_by_action = 'retired', 'human-edit'
    with v2_app(tmp_path, [(value, sources)]) as (client, _application):
        editor = Editor(client, value.project_id)
        report = editor.call('post', '/check', {'editorToken': editor.token})
        active = value.project.import_issues[0]
        assert report['openImportIssues'] == [{'id': active.id, 'blockIds': list(active.block_ids)}]


def test_the_check_needs_the_current_editor_token(tmp_path):
    value, sources = papers()
    with v2_app(tmp_path, [(value, sources)]) as (client, _application):
        first = Editor(client, value.project_id)
        unknown = first.refused('post', '/check', {'editorToken': 'not-a-token'}, 409)
        assert unknown['error']['code'] == 'EDITOR_TOKEN_UNKNOWN'
        Editor(client, value.project_id)
        replaced = first.refused('post', '/check', {'editorToken': first.token}, 409)
        assert replaced['error']['code'] == 'EDITOR_REPLACED'
        assert first.refused('post', '/check', {}, 422)['error']['code']
