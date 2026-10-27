"""The run's tools: reads serve the pinned workspace while the user edits; pages, search, originals, skills, export."""

import asyncio
import json
import threading
import time
import zipfile
from io import BytesIO

import pytest

from packages.resume_core.assistant_store import AgentFailure
from packages.resume_core.models.template_render import TemplateRendererIdentity
from resume_api.assistant import context
from tests.assistant.support import PROJECT, Editor, assistant_app, base, conversation, finish, manual_edit, start
from tests.templates.storage_fixtures import workspace as papers

DOCX = b'PK\x03\x04synthetic-assistant-export'


def test_reads_serve_the_pinned_workspace_while_the_user_edits(tmp_path):
    read, edited, seen = threading.Event(), threading.Event(), []

    async def steps(tools, _value, cancel, _emit):
        seen.append((await tools.call('read_resume', {'page': 0}))['items'][0]['containers'][0]['text'])
        read.set()
        while not edited.is_set() and not cancel.is_set():
            await asyncio.sleep(0.01)
        seen.append((await tools.call('read_resume', {'page': 0}))['items'][0]['containers'][0]['text'])
        seen.append((await tools.call('find_text', {'query': 'Human'}))['matches'])
        return 'Готово.'
    with assistant_app(tmp_path, steps) as (client, _app, _runtime):
        run = start(client, conversation(client))
        deadline = time.monotonic() + 5
        while not read.is_set():
            assert time.monotonic() < deadline
            read.wait(0.01)
        editor = Editor(client, PROJECT)
        manual_edit(editor, text='Human')
        edited.set()
        finish(client, run)
        assert seen == ['Shared title', 'Shared title', []]
        assert editor.workspace().project.document.regions[2].blocks[0].content[0].text.startswith('Human')


def test_pages_hold_whole_entries_and_clip_an_oversized_one():
    entries = [{'id': f'entry-{index}', 'text': 'x' * 3000} for index in range(12)] + [{'id': 'huge', 'text': 'y' * 40000}]
    pages, page = [], 0
    while page is not None:
        value = context.paged(entries, page)
        assert len(context.json_text(value).encode()) <= context.limits.PAGE_BYTES
        pages.append(value['items'])
        page = value['nextPage']
    flat = [item for items in pages for item in items]
    assert [item['id'] for item in flat] == [entry['id'] for entry in entries]
    assert flat[-1]['clipped'] is True and 'yyyy' in flat[-1]['json']
    assert context.paged(entries, 1) == context.paged(entries, 1)
    with pytest.raises(AgentFailure):
        context.paged(entries, len(pages))


def test_search_gives_utf16_offsets_and_matching_facts():
    workspace, _sources = papers()
    data = workspace.model_dump(by_alias=True)
    data['project']['document']['regions'][2]['blocks'][0]['content'][0]['text'] = '😀 Shared title'
    from packages.resume_core.models.template_workspace import WorkspaceV7
    found = context.find(WorkspaceV7.model_validate(data), 'Shared')
    assert found['matches'][0] == {'blockId': 'block-paper-a', 'key': 'content', 'start': 3, 'end': 9, 'occurrences': 1}
    assert 'paper-a' in found['facts']


def test_an_original_with_no_extracted_text_is_reported_not_reconstructed():
    workspace, _sources = papers()
    source = workspace.project.sources[0]
    listed = context.source_entries(workspace, None)
    assert listed[0]['id'] == source.id and listed[0]['extractedText'] == 'available'
    empty = workspace.model_copy(deep=True)
    empty.project.sources[0].units = []
    assert context.source_entries(empty, source.id) == [{'sourceId': source.id, 'extractedText': 'unavailable',
        'warnings': list(source.warnings)}]
    with pytest.raises(AgentFailure):
        context.source_entries(workspace, 'missing-source')


def test_skills_and_their_references_are_readable_and_unknown_resources_are_refused(tmp_path):
    results = []

    async def steps(tools, _value, _cancel, _emit):
        results.append(await tools.call('read_skill', {'name': 'format-resume'}))
        results.append(await tools.call('read_skill', {'name': 'format-resume', 'resource': 'references/editorial-rules.md'}))
        results.append(await tools.call('read_skill', {'name': 'format-resume', 'resource': '../secrets'}))
        return 'Готово.'
    with assistant_app(tmp_path, steps) as (client, _app, _runtime):
        finish(client, start(client, conversation(client)))
        assert client.get(base() + '/skills').json()['items'][0]['id'] == 'import-resume'
    assert results[0]['content'].startswith('# Format the current resume')
    assert results[1]['content'].startswith('# Chat editorial rules')
    assert results[2] == {'error': {'code': 'AGENT_NOT_FOUND'}}


def test_the_export_tool_runs_the_export_task_and_links_the_file(tmp_path):
    links = []

    async def render(_request):
        return DOCX

    async def steps(tools, _value, _cancel, _emit):
        links.append(await tools.call('export_document', {'format': 'docx'}))
        links.append(await tools.call('export_document', {'format': 'foldcv'}))
        return 'Файлы готовы.'
    with assistant_app(tmp_path, steps) as (client, application, _runtime):
        exports = application.state.projects.exports
        exports._renderer = TemplateRendererIdentity(id='captured-docx', version='test', sha256='a' * 64)
        exports.render = render
        cid = conversation(client)
        _run, events = finish(client, start(client, cid))
        docx, foldcv = links
        assert client.get(docx['url']).content == DOCX
        archive = zipfile.ZipFile(BytesIO(client.get(foldcv['url']).content))
        assert 'workspace.json' in archive.namelist() and 'history.jsonl' not in archive.namelist()
        saved = application.state.projects.repository.read(PROJECT)
        assert [attempt.state for attempt in saved.project.exports] == ['completed']
        files = client.get(base() + f'/conversations/{cid}/messages').json()['files']
        assert [item['format'] for item in files] == ['docx', 'foldcv']
        assert [event['type'] for event in events].count('file.ready') == 2
        assert json.loads(client.get(base() + '/files/file_unknown').content)['error']['code'] == 'ASSISTANT_FILE_NOT_FOUND'
