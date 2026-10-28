"""Bundled templates: the Generic package keeps its exact hash in the shared folder; the generic one-column template
imports, edits and exports in one column with plain headings and job technology chips, without Generic branding, Focus
or a logo."""

import asyncio
from functools import cache
import io
import re
import zipfile

import pytest

from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.compiler import compile_template
from packages.resume_core.templates.presentation import project_presentation
from packages.resume_core.templates.store import BUNDLED_TEMPLATE, BUNDLED_TEMPLATES
from tests.templates.generic_fixtures import generic_import, f10
from tests.templates.test_captured_docx import NS, emitted, xml
from tests.templates.test_panel_preparation import move
from tests.templates.test_template_preparation import response
from tests.templates.test_template_view_adapters import render

GENERIC_HASH = '29cc211fa5f0f6663844286c5af99310317def70cdc6fce322000151aadd8e4e'
GENERIC = BUNDLED_TEMPLATES['generic-one-column']


@cache
def generic():
    return compile_template(GENERIC)


def test_the_generic_package_keeps_its_exact_hash_in_the_shared_folder():
    # Captured projects and the template store name this hash; moving the files must not change a byte of it.
    assert next(iter(BUNDLED_TEMPLATES)) == 'generic-two-column' and BUNDLED_TEMPLATE == BUNDLED_TEMPLATES['generic-two-column']
    assert compile_template(BUNDLED_TEMPLATE).package_hash == GENERIC_HASH


def test_the_generic_template_has_one_column_and_no_generic_branding_focus_logo_or_icons():
    assert b'generic' not in GENERIC.read_bytes().lower()
    package = generic()
    assert [region.id for region in package.recipe.layout.regions] == ['header', 'main']
    style = package.recipe.style
    assert style.header.logo is None and style.footer.text == '' and style.focus.icon_catalog is None
    assert not any(node.type == 'focus_entry' for view in package.recipe.views.values() for node in view.nodes)
    assert {view.heading for view in package.recipe.views.values()} == {'none', 'plain'}
    # The fonts are the same bytes as the Generic package's; its logo, icon pack and Devicon license are left out.
    generic = {asset.path: asset.sha256 for asset in compile_template(BUNDLED_TEMPLATE).assets}
    assert all(generic[asset.path] == asset.sha256 for asset in package.assets)
    assert not {asset.id for asset in package.assets} & {'generic', 'technology-icons', 'devicon-license'}


@pytest.fixture(scope='module')
def imported(tmp_path_factory):
    # F10 without its Focus reply: the generic template asks for none.
    table = {key: value for key, value in f10(True).items() if key != 'focus'}
    _fixture, result, workspace, _originals = asyncio.run(generic_import(tmp_path_factory.mktemp('generic'), 'F10',
        table=table, package=generic()))
    return result, workspace


def chip_line(workspace):
    plan = project_presentation(workspace)['editor']
    block = next(block for block in workspace.project.document.blocks() if plan['blocks'][block.id].get('chips'))
    return [span.text for span in block.content], set(plan['blocks'][block.id]['chips'].values())


@pytest.mark.slow
def test_an_import_fills_one_column_in_the_requested_order_and_keeps_job_technology_chips(imported):
    result, workspace = imported
    assert result.state == 'published' and 'focus' not in {task.block_id for task in result.tasks}
    regions = {region.role: list(dict.fromkeys(block.presentation.view_key for block in region.blocks))
        for region in workspace.project.document.regions}
    assert regions == {'header': ['identity'], 'sidebar': [], 'main': ['summary', 'projects', 'other_projects',
        'career_highlights', 'programming', 'data_and_tools', 'infrastructure', 'education', 'courses', 'languages',
        'location', 'opensource']}
    plan = project_presentation(workspace)['editor']
    assert not any('band' in entry or 'focus' in entry for entry in plan['blocks'].values()) and plan['icons'] == []
    assert chip_line(workspace) == (['Python', ' ', 'PostgreSQL', ' ', 'Docker'], {'#EFEFEF'})
    # The Facts panel lists the job's technologies; its reorder moves the chips.
    job = next(record for record in workspace.project.facts.records
        if record.kind == 'employment' and record.employer.raw_text == 'Example Labs')
    technologies = {record.display.raw_text: record.id for record in workspace.project.facts.records
        if record.kind == 'technology' and record.job_id == job.id}
    prepared = prepare_edit(response(workspace), move(workspace, technologies['Docker'], technologies['Python']))
    assert chip_line(apply_rich_mutation(workspace, prepared.mutation)[0])[0] == ['Docker', ' ', 'Python', ' ', 'PostgreSQL']


@pytest.mark.slow
def test_the_docx_is_one_column_at_full_width_without_bands_logo_or_footer_text(imported, tmp_path):
    _result, workspace = imported
    content = render(workspace, tmp_path)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        parts = {name: archive.read(name) for name in names if name.endswith('.xml')}
    body = xml(content)
    # A4 is 11920 twips: 800 left, the 10320 main column, 800 right. The body is the column, with no layout table.
    assert [body.xpath('string(//w:pgMar/@w:' + side + ')', namespaces=NS) for side in ('left', 'right')] == ['800', '800']
    assert not body.xpath('//w:tbl', namespaces=NS)
    # Headings have no band; only the three job technology chips are shaded.
    assert not body.xpath('//w:pPr/w:shd', namespaces=NS)
    assert body.xpath('//w:rPr/w:shd/@w:fill', namespaces=NS) == ['EFEFEF'] * 3
    assert not [name for name in names if name.startswith('word/media/')]
    assert not any(b'<w:t' in value for name, value in parts.items() if re.fullmatch(r'word/footer\d*\.xml', name))
    assert not any(b'generic' in value.lower() for value in parts.values())
    text = emitted(body)
    assert 'ФОКУС' not in text and text.index('О СЕБЕ') < text.index('ПРОЕКТЫ') < text.index('ОБРАЗОВАНИЕ') < text.index('OPEN SOURCE')
    # A block moved into the sidebar of a one-column resume still exports, before the main column.
    document = workspace.project.document.model_copy(deep=True)
    sidebar, main = document.regions[1:]
    moved = {block.id for block in main.blocks if block.presentation.view_key == 'education'}
    sidebar.blocks = [block for block in main.blocks if block.id in moved]
    main.blocks = [block for block in main.blocks if block.id not in moved]
    moved_body = xml(render(workspace, tmp_path, document=document))
    assert not moved_body.xpath('//w:tbl', namespaces=NS)
    assert emitted(moved_body).index('ОБРАЗОВАНИЕ') < emitted(moved_body).index('О СЕБЕ')
