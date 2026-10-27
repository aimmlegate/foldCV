"""The resume heading (rich_identity) is a projection of the candidate record: reads never rewrite the saved project."""

import hashlib
from types import SimpleNamespace

from packages.resume_core.rich_identity import resume_identity
from packages.resume_core.templates.compiler import canonical
from tests.projects.support import v2_app
from tests.support.rich import without_sources
from tests.templates.storage_fixtures import workspace as papers

PROJECT = 'template-project'


def with_candidate(name='Anna Stone', title='Platform engineer', *, label='Old manual label', manual=False):
    workspace, sources = papers()
    candidate = next(record for record in without_sources().project.facts.records if record.kind == 'candidate')
    candidate.name.raw_text = candidate.name.value = name
    candidate.title.raw_text = candidate.title.value = title
    data = workspace.model_dump(by_alias=True)
    data['project']['facts']['records'].append(candidate.model_dump(by_alias=True))
    data['title'], data['titleManuallySet'] = label, manual
    return type(workspace).model_validate(data), sources


def listed_heading(client):
    entry = next(item for item in client.get('/v2/projects').json()['entries'] if item['projectId'] == PROJECT)
    return entry['title'], entry['subtitle']


def heading(client):
    response = client.get('/v2/projects/' + PROJECT).json()
    entry = next(item for item in client.get('/v2/projects').json()['entries'] if item['projectId'] == PROJECT)
    return (response['identity']['title'], response['identity']['subtitle']), (entry['title'], entry['subtitle']), response


def renamed(repository, name, title, identifier):
    def build(workspace):
        changed = workspace.model_copy(deep=True)
        record = next(record for record in changed.project.facts.records if record.kind == 'candidate')
        record.name.raw_text = record.name.value = name
        record.title.raw_text = record.title.value = title
        return changed
    return repository.mutate(PROJECT, base_revision=repository.read(PROJECT).project_revision, client_mutation_id=identifier,
        request_sha256=hashlib.sha256(canonical([identifier, name, title])).hexdigest(), action_id=identifier, kind='edit',
        build=build)


def test_resume_identity_uses_candidate_name_and_profession_with_safe_missing_values():
    workspace = without_sources()
    candidate = next(record for record in workspace.project.facts.records if record.kind == 'candidate')
    candidate.name.raw_text = '  Anna\n Stone  '
    candidate.title.raw_text = ' Platform  engineer '
    assert resume_identity(workspace).model_dump() == {'title': 'Anna Stone', 'subtitle': 'Platform engineer'}
    candidate.name.raw_text = ' \n '
    assert resume_identity(workspace).title == 'Резюме без имени'
    candidate.title.raw_text = ''
    assert resume_identity(workspace).subtitle == ''
    workspace.project.facts.records = [record for record in workspace.project.facts.records if record.kind != 'candidate']
    assert resume_identity(workspace).model_dump() == {'title': 'Резюме без имени', 'subtitle': ''}
    assert resume_identity(SimpleNamespace(project=None, title='original.txt')).title == 'original.txt'


def test_the_heading_follows_the_candidate_and_reading_it_never_rewrites_the_saved_workspace(tmp_path):
    with v2_app(tmp_path, [with_candidate()]) as (client, application):
        path = application.state.projects.repository.open(PROJECT).directory / 'workspace.json'
        original = path.read_bytes()
        shown, listed, response = heading(client)
        assert shown == listed == ('Anna Stone', 'Platform engineer')
        assert response['workspace']['title'] == 'Old manual label' and path.read_bytes() == original
    with v2_app(tmp_path) as (client, _application):
        assert heading(client)[:2] == (shown, listed) and path.read_bytes() == original


def test_a_manual_title_wins_over_the_candidate_name_and_keeps_the_profession(tmp_path):
    with v2_app(tmp_path, [with_candidate(label='  Chosen\n label ', manual=True)]) as (client, _application):
        shown, listed, _response = heading(client)
        assert shown == listed == ('Chosen label', 'Platform engineer')


def test_candidate_changes_and_their_undo_change_the_heading_without_a_cached_title(tmp_path):
    from tests.repository.support import history
    with v2_app(tmp_path, [with_candidate()]) as (client, application):
        repository = application.state.projects.repository
        assert heading(client)[0] == ('Anna Stone', 'Platform engineer')
        renamed(repository, 'Changed Name', 'New Role', 'candidate-1')
        shown, listed, _response = heading(client)
        assert shown == listed == ('Changed Name', 'New Role')
        history(repository, 'undo', identifier='undo-1', expected='candidate-1')
        shown, listed, _response = heading(client)
        assert shown == listed == ('Anna Stone', 'Platform engineer')


def test_the_listing_heading_follows_a_commit_made_outside_the_edit_routes(tmp_path):
    with v2_app(tmp_path, [with_candidate()]) as (client, application):
        assert heading(client)[1] == ('Anna Stone', 'Platform engineer')
        renamed(application.state.projects.repository, 'Changed Name', 'New Role', 'candidate-1')
        assert listed_heading(client) == ('Changed Name', 'New Role')
