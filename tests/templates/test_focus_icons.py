"""Focus icons: the template's own names first, then the technology catalog's synonyms; pinned Devicon provenance."""

import base64
import hashlib
import json
from pathlib import Path

import pytest

from packages.resume_core.technologies import BY_ID
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.focus import icon_catalog
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.generic_fixtures import generic_package
from tests.templates.test_captured_docx import NS, parts, xml
from tests.templates.test_template_view_adapters import published, render

ROOT = Path(__file__).resolve().parents[2]
DEVICON = ROOT / 'skills/format-resume/assets/devicon'
PACK = BUNDLED_TEMPLATE.parent / 'assets/technology-icons.json'
OLD_ALIASES = {'python': 'python', 'c#': 'csharp', '.net': 'dotnet', 'docker': 'docker', 'c++': 'cplusplus'}


@pytest.mark.parametrize('name, icon', [
    ('k8s', 'kubernetes'), ('GitLab CI/CD', 'gitlab'), ('gitlab-ci', 'gitlab'), ('Python 3.12', 'python'),
    ('Microsoft SQL Server', 'mssql'), ('Postgres', 'postgresql'), ('Go', 'golang'), ('Go 1.22', 'golang'),
    ('Node.js 20', 'nodejs'), ('Spring Boot 3', 'spring'), ('Apache Kafka', 'kafka'), ('Amazon Web Services', 'aws'),
    ('Kubernetes (EKS)', 'kubernetes'), ('Docker Compose v2', 'docker'), ('  JENKINS ', 'jenkins'),
    # The template's own name wins over the catalog, which files GitHub Actions under GitHub.
    ('GitHub Actions', 'githubactions'), ('GitHub', 'github'),
    # Outside the catalog the template's names carry the spellings, versions still drop.
    ('Next.js 14', 'nextjs'), ('Tailwind CSS', 'tailwindcss'), ('Objective-C', 'objectivec'), ('R', 'r'),
    ('SQL', None), ('Yandex Cloud', None), ('Командная работа', None), ('', None)])
def test_a_focus_name_finds_its_icon_through_template_names_and_catalog_synonyms(name, icon):
    assert icon_catalog(generic_package()).find(name) == icon


def test_a_flat_catalog_of_icon_assets_still_binds_their_catalog_technology(tmp_path):
    # Packages captured before 2.5.0 name icon assets by display aliases only (c#, .net) and have no Jenkins icon.
    config = generic_package().definition.model_dump(mode='json', by_alias=True)
    config['assets'] = [asset for asset in config['assets'] if asset['id'] != 'technology-icons'] + [
        {'id': 'icon-aliases', 'path': 'assets/icon-aliases.json', 'role': 'catalog', 'mime_type': 'application/json',
            'embedding': 'not_applicable'}] + [{'id': icon, 'path': f'assets/{icon}.png', 'role': 'icon',
            'mime_type': 'image/png', 'embedding': 'not_applicable'} for icon in sorted(set(OLD_ALIASES.values()))]
    config['style']['focus']['icon_catalog'] = 'icon-aliases'
    (tmp_path / 'assets').mkdir()
    for asset in config['assets']:
        if asset['role'] == 'icon':
            (tmp_path / asset['path']).write_bytes((DEVICON / (asset['id'] + '.png')).read_bytes())
        elif asset['id'] != 'icon-aliases':
            (tmp_path / asset['path']).write_bytes((BUNDLED_TEMPLATE.parent / asset['path']).read_bytes())
    (tmp_path / 'assets/icon-aliases.json').write_text(json.dumps(OLD_ALIASES))
    package = compile_bytes(json.dumps(config).encode(), tmp_path, original_format='json')
    catalog = icon_catalog(package)
    assert [catalog.find(name) for name in ['C# 12', '.NET 8', 'Microsoft .NET', 'Python 3', 'C++', 'Jenkins', 'k8s']] == [
        'csharp', 'dotnet', 'dotnet', 'python', 'cplusplus', None, None]
    assert catalog.files['python'] == next(asset for asset in package.assets if asset.id == 'python')


def test_a_pack_icon_whose_bytes_differ_from_its_hash_is_refused():
    from packages.resume_core.templates.focus import packed_icons
    pack = json.loads(PACK.read_text())
    catalog = next(asset for asset in generic_package().assets if asset.id == 'technology-icons')
    icons = {'python': {**pack['icons']['python'], 'png': pack['icons']['docker']['png']}}
    with pytest.raises(ValueError, match='unreadable'):
        packed_icons(catalog, icons)


def test_every_pack_name_names_a_packed_icon_with_pinned_devicon_provenance():
    package = generic_package()
    pack = json.loads(PACK.read_text())
    files = icon_catalog(package).files
    assert set(pack['names'].values()) == set(pack['icons']) == set(files)
    assert all(pack['names'][icon] == icon for icon in pack['icons'])
    # Every icon is a catalog technology but those the catalog has no entry for; their names live in the pack.
    outside = set(files) - set(BY_ID)
    assert 'r' in outside and 'githubactions' in outside and {'kubernetes', 'jenkins', 'gitlab'} <= set(files) - outside
    # sources.json keeps the eleven icons the frozen foldcv-reference manifest pins; later ones are in pinned-sources.json.
    frozen = json.loads((DEVICON / 'sources.json').read_text())
    pinned = json.loads((DEVICON / 'pinned-sources.json').read_text())
    assert not frozen.keys() & pinned.keys() and frozen.keys() | pinned.keys() == set(files)
    license_asset = next(asset for asset in package.assets if asset.id == 'devicon-license')
    assert base64.b64decode(license_asset.bytes_base64) == (DEVICON / 'LICENSE').read_bytes()
    for icon, asset in files.items():
        source, png = {**frozen, **pinned}[icon], base64.b64decode(asset.bytes_base64)
        assert hashlib.sha256((DEVICON / (icon + '.svg')).read_bytes()).hexdigest() == source['sha256'], icon
        assert (DEVICON / (icon + '.png')).read_bytes() == png, icon
        assert pack['icons'][icon]['source'] == source['url'] and pack['icons'][icon]['svgSha256'] == source['sha256']
        if icon in pinned:
            assert source['revision'] == pack['provenance']['commit'] and source['revision'] in source['url']
            assert source['license'] == 'MIT' and source['pngSha256'] == asset.sha256


def renamed(workspace, names):
    """The published Focus rows with each technology cell and its shown text changed by hand to the given names."""
    from packages.resume_core.models.template_document import FieldOccurrence
    from packages.resume_core.models.template_workspace import WorkspaceV7
    value = workspace.model_copy(deep=True)
    cells = {cell.id: cell for record in value.project.facts.extensions for cell in record.cells}
    rows = [block for block in value.project.document.blocks() if block.type == 'paragraph'
        and block.presentation.view_key == 'focus' and block.presentation.style_token == 'emphasis']
    for block, name in zip(rows, names, strict=True):
        for part in block.content:
            if isinstance(part, FieldOccurrence):
                cell = cells[part.cell_id]
                cell.raw_input = cell.typed_value = part.text = name
                cell.origin, cell.user_corrected = 'human', True
    return WorkspaceV7.model_validate(value.model_dump(by_alias=True))


@pytest.mark.asyncio
async def test_focus_rows_show_synonym_icons_in_the_plan_and_embed_the_same_bytes_in_docx(tmp_path):
    from packages.resume_core.templates.models import asset_text
    from packages.resume_core.templates.presentation_plan import editor_plan
    _fixture, workspace, _originals = await published(tmp_path)
    workspace = renamed(workspace, ['k8s', 'GitLab CI/CD', 'UnknownTool'])
    plan = editor_plan(workspace.project)
    assert [entry['focus']['icon'] for entry in plan['blocks'].values() if 'focus' in entry] == ['kubernetes', 'gitlab', None]
    files = icon_catalog(workspace.project.template_package).files
    assert plan['icons'] == ['gitlab', 'kubernetes']
    assert plan['iconFiles'] == {icon: files[icon].sha256 for icon in plan['icons']}
    # The asset route serves a packed icon by its hash once a plan names it.
    assert asset_text(files['kubernetes'].sha256) == files['kubernetes'].bytes_base64
    content = render(workspace, tmp_path)
    tree = xml(content)
    blips = tree.xpath('//w:body//a:blip/@r:embed', namespaces={**NS, 'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'})
    rels = {child.get('Id'): child.get('Target') for child in xml(content, 'word/_rels/document.xml.rels')}
    embedded = [parts(content)['word/' + rels[identifier]] for identifier in blips]
    assert embedded == [base64.b64decode(files[icon].bytes_base64) for icon in ['kubernetes', 'gitlab']]
