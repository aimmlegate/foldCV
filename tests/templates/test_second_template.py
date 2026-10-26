"""CT08: a second template, defined by configuration only, imports, transfers and exports (N01–N04)."""

import io
import re
import zipfile

import pytest

from packages.resume_core.models.template_document import BoundLink
from tests.templates.generic_fixtures import generic_import, export_through_service
from tests.templates.publications_fixtures import (AWARD, BLOCKS, DIVISION, TITLE, URLS, publications_package,
    publications_table, publications_workspace)
from tests.templates.test_template_view_adapters import emitted, hyperlinks, render, text, xml


def views(workspace):
    """Each view's visible texts in document order."""
    result = {}
    for block in workspace.project.document.blocks():
        if block.type != 'section':
            result.setdefault(block.presentation.view_key, []).append(text(block))
    return result


def regions(workspace):
    return {region.role: list(dict.fromkeys(block.presentation.view_key for block in region.blocks))
        for region in workspace.project.document.regions}


async def imported(tmp_path, name):
    return await generic_import(tmp_path / name, name, table=publications_table(name), package=publications_package())


def parts(content):
    archive = zipfile.ZipFile(io.BytesIO(content))
    return {name: archive.read(name).decode() for name in archive.namelist() if name.endswith('.xml')}


@pytest.mark.asyncio
async def test_a_publications_template_imports_through_configuration_only(tmp_path):
    # N01/N04: arbitrary block IDs, its own block order and a paper type the built-in facts do not declare.
    _fixture, result, workspace, _originals = await imported(tmp_path, 'F05')
    assert result.state == 'published' and {task.block_id: task.state for task in result.tasks} == dict.fromkeys(BLOCKS, 'accepted')
    assert not workspace.project.import_issues
    assert regions(workspace) == {'header': ['hdr-7'], 'sidebar': ['papers-x9'], 'main': ['work-q2']}
    shown = views(workspace)
    assert shown['papers-x9'] == ['PUBLICATIONS', TITLE, 'Systems Notes, 2024', TITLE, 'Queue Review, 2025']
    assert shown['work-q2'] == ['EXPERIENCE', 'Example Labs — engineer', '2020–2023', 'Division: ' + DIVISION, 'Awards:', AWARD]
    # Two equal titles stay two records with their own cells and links; a year shows its stated wording.
    papers = [record for record in workspace.project.facts.extensions if record.semantic_type == 'pub:paper']
    titles = [cell for record in papers for cell in record.cells if cell.field_key == 'title']
    assert len({record.id for record in papers}) == 2 and [cell.raw_input for cell in titles] == [TITLE, TITLE]
    assert len({cell.id for cell in titles}) == 2
    assert sorted(cell.raw_input for record in papers for cell in record.cells if cell.field_key == 'url') == URLS
    links = [part for block in workspace.project.document.blocks() for part in block.content if isinstance(part, BoundLink)]
    assert sorted(link.href for link in links) == URLS
    # The award is owned by the employer; the division extends it.
    employer = next(record for record in workspace.project.facts.records if record.kind == 'employment')
    kinds = {record.semantic_type: record.id for record in workspace.project.facts.extensions
        if record.semantic_type in {'pub:award', 'pub:division'}}
    assert {(relation.kind, relation.subject_id): relation.target_id for relation in workspace.project.facts.relations
        if relation.active} == {('owned_by', kinds['pub:award']): employer.id, ('extension_of', kinds['pub:division']): employer.id}


@pytest.mark.asyncio
async def test_the_export_uses_the_templates_own_columns_type_and_branding(tmp_path):
    # N04: the same build renders the independently specified geometry and type, with no bundled branding.
    _fixture, _result, workspace, originals = await imported(tmp_path, 'F05')
    content = await export_through_service(tmp_path / 'export', workspace, originals)
    xml_parts = parts(content)
    document = xml_parts['word/document.xml']
    # Sidebar 130 pt, gap 10 pt and main 420 pt in twips; body text 11 pt (22 half-points).
    assert re.findall(r'<w:gridCol w:w="(\d+)"', document) == ['2600', '200', '8400']
    assert '<w:sz w:val="22"/>' in document
    assert hyperlinks(content) == [(TITLE, (URLS[0], 'External')), (TITLE, (URLS[1], 'External'))]
    assert not any('generic' in value.lower() for value in xml_parts.values())
    assert not any('<w:drawing' in value for name, value in xml_parts.items() if name.startswith('word/header'))
    footers = [value for name, value in xml_parts.items() if re.fullmatch(r'word/footer\d+\.xml', name)]
    assert footers and all('Synthetic publications CV' in value for value in footers)


@pytest.mark.asyncio
async def test_without_publications_the_block_and_its_heading_are_omitted(tmp_path):
    # N02: no warning; the source and the other facts stay.
    _fixture, result, workspace, originals = await imported(tmp_path, 'F05-empty')
    assert {task.block_id: task.state for task in result.tasks} == {'hdr-7': 'accepted', 'papers-x9': 'empty', 'work-q2': 'accepted'}
    assert 'papers-x9' not in views(workspace) and not workspace.project.import_issues and not workspace.warnings
    assert [source.id for source in workspace.project.sources] == list(originals)
    assert any(record.kind == 'employment' for record in workspace.project.facts.records)
    assert 'PUBLICATIONS' not in emitted(xml(render(workspace, tmp_path)))


def test_the_editor_plan_and_recipe_carry_the_templates_columns_and_type():
    # N04: the mounted editor reads the same geometry and type the DOCX uses.
    from packages.resume_core.templates.presentation import project_presentation
    workspace, _originals = publications_workspace('F05')
    presentation = project_presentation(workspace)
    assert [(region['id'], region['x'], region['width']) for region in presentation['recipe']['layout']['regions']] == [
        ('header', 20.0, 556.0), ('sidebar', 20.0, 130.0), ('main', 160.0, 420.0)]
    styles = presentation['editor']['styles']
    assert (styles['body']['size'], styles['body']['faces']['regular']) == (11.0, 'Sans-Regular')
    assert presentation['editor']['fonts'] == ['Sans-Bold', 'Sans-Regular'] and presentation['recipe']['style']['header']['logo'] is None


def test_a_transfer_keeps_the_template_its_equal_titles_and_its_owners():
    # N04: copy the project out and back in; package, document and facts survive unchanged.
    from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
    workspace, originals = publications_workspace('F11')
    copied, *_ = open_rich_archive(export_rich_archive(workspace, originals, {}, {}), 'publications-transfer')
    assert copied.project.template_package.package_hash == workspace.project.template_package.package_hash
    assert copied.project.document == workspace.project.document and copied.project.facts == workspace.project.facts


def renamed(workspace, identifier):
    """The same workspace under another project id, so two projects share one service."""
    import json
    from packages.resume_core.models.template_workspace import WorkspaceV7
    data = workspace.model_dump(mode='json', by_alias=True)
    if workspace.project is not None and workspace.project.template_operations:
        # The JSON names import records by history file (D104); a renamed copy carries them along.
        data['project']['templateOperations'] = [value.model_dump(mode='json', by_alias=True)
            for value in workspace.project.template_operations]
    return WorkspaceV7.model_validate_json(json.dumps(data).replace('"' + workspace.project_id + '"', '"' + identifier + '"'))


@pytest.mark.asyncio
async def test_a_mounted_project_keeps_its_template_while_another_template_is_active(tmp_path):
    # N03: activating the second template changes only new projects; interleaved exports keep each project's own.
    from types import SimpleNamespace
    import httpx
    from packages.resume_core.template_export import snapshot_identity
    from packages.resume_core.templates.presentation import project_presentation
    from packages.resume_core.templates.store import TemplateStore
    from resume_api.jobs.service import JobService
    from tests.templates.generic_fixtures import direct_generic, generic_package
    from tests.templates.test_template_api import application, isolated_service
    first, first_originals = direct_generic('F01', ['identity', 'projects'])
    second, second_originals = publications_workspace('F05')
    second = renamed(second, 'publications-project')
    service, first_id = isolated_service(tmp_path, first, first_originals)
    service.workspaces[second.project_id] = second.model_copy(deep=True)
    service.originals.update({(second.project_id, key): value for key, value in second_originals.items()})
    assert service.persist(second.project_id) == 'durable'
    store = TemplateStore(service.storage.root)
    store.activate(generic_package())
    mounted = project_presentation(service.storage.read_committed(first_id)[0])
    store.activate(publications_package())
    assert store.active().package_hash == publications_package().package_hash
    jobs = JobService(service, None, lambda: SimpleNamespace(ready=False), enabled=False, template_cleanup_verified=lambda: True)
    await jobs.start()
    exported = []
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(service)), base_url='http://foldcv.test') as client:
            for identifier in [first_id, second.project_id, first_id]:
                before = service.storage.read_committed(identifier)[0]
                response = await client.post('/v1/rich/projects/' + identifier + '/export',
                    json={'schemaVersion': 1, 'snapshot': snapshot_identity(before).model_dump(mode='json', by_alias=True)})
                assert response.status_code == 200, response.text
                attempt = service.storage.read_committed(identifier)[0].project.exports[-1]
                exported.append((attempt.package_hash, parts(response.content)['word/footer1.xml']))
    finally:
        await service.shutdown()
        await jobs.shutdown()
    hashes = [value for value, _footer in exported]
    assert hashes == [first.project.template_package.package_hash, second.project.template_package.package_hash,
        first.project.template_package.package_hash]
    assert 'mail@example.com' in exported[0][1] and 'Synthetic publications CV' in exported[1][1] and exported[2][1] == exported[0][1]
    # The mounted project's presentation is still its own; a new project captures the active second template.
    assert project_presentation(service.storage.read_committed(first_id)[0])['recipe'] == mounted['recipe']
    new = service.allocate_template('Новое резюме', store.active())
    assert service.read(new).pre_draft.template_package.package_hash == publications_package().package_hash


def test_a_date_or_period_shows_its_stated_wording_and_other_objects_their_json():
    # A template-only type showed {"raw": ...} JSON for its year; built-in records already showed the wording.
    from packages.resume_core.template_wording import display_text
    assert display_text('As stated') == 'As stated'
    assert display_text({'raw': '2024', 'year': 2024, 'month': None}) == '2024'
    assert display_text({'raw': '2020–2023', 'start': None, 'end': None, 'ongoing': False}) == '2020–2023'
    assert display_text({'raw': '  ', 'year': 2024}) == '{"raw":"  ","year":2024}'
    assert display_text({'name': 'Queue'}) == '{"name":"Queue"}' and display_text(['a']) == '["a"]'
