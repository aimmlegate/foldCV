"""D145: «Шаблоны» sets a template's own logo in its logo place and an optional footer email as its next revision."""

import base64
from io import BytesIO
import json

from PIL import Image
import pytest

from packages.resume_core.templates.store import BUNDLED_TEMPLATE, BUNDLED_TEMPLATES, TemplateStore
from resume_api.template_branding import (LOGO_BYTES, LOGO_SIDE, NO_PLACE, NOT_EMAIL, NOT_IMAGE, TOO_LARGE,
    TemplateBrandingRequest, edited_yaml)
from resume_api.template_config import TemplateConfig
from tests.templates.generic_fixtures import export_through_service, generic_import
from tests.templates.scripted_template_provider import ScriptedTemplateProvider
from tests.templates.test_captured_docx import parts
from tests.templates.test_template_import_app import app_client, upload

TWO, ONE = 'generic-two-column', 'generic-one-column'


def picture(width=3000, height=1000, kind='PNG', color=(200, 30, 30, 255)):
    out = BytesIO()
    Image.new('RGBA' if kind == 'PNG' else 'RGB', (width, height), color if kind == 'PNG' else color[:3]).save(out, kind)
    return base64.b64encode(out.getvalue()).decode()


def request(logo=None, footer='', remove=False):
    return TemplateBrandingRequest(logo=logo, removeLogo=remove, footer=footer)


def logo_of(package):
    place = package.recipe.style.header.logo
    return next((asset for asset in package.assets if place is not None and asset.id == place.asset), None)


def test_the_two_column_template_ships_an_empty_logo_place_and_no_footer(tmp_path):
    assert TemplateConfig(tmp_path).branding(TWO) == {'schemaVersion': 1, 'logoPlace': True, 'logo': None, 'footer': ''}
    # The one-column template has no logo place at all.
    assert TemplateConfig(tmp_path).branding(ONE)['logoPlace'] is False


def test_an_own_logo_and_email_are_the_next_revision_and_the_text_keeps_its_comments(tmp_path):
    config = TemplateConfig(tmp_path)
    before = TemplateStore(tmp_path).current(TWO)
    saved, refused = config.save_branding(TWO, request(picture(), ' hr@example.com '))
    assert refused is None
    package = TemplateStore(tmp_path).current(TWO)
    assert package.revision == '1.4.1' != before.revision and saved['package']['revision'] == '1.4.1'
    asset = logo_of(package)
    assert (asset.id, asset.path, asset.mime_type) == ('logo', 'assets/logo.png', 'image/png')
    with Image.open(BytesIO(base64.b64decode(asset.bytes_base64))) as image:
        assert image.format == 'PNG' and image.size == (LOGO_SIDE, LOGO_SIDE // 3)
    assert package.recipe.style.footer.text == 'hr@example.com'
    assert package.recipe.style.header.logo.model_dump(exclude={'asset'}) == before.recipe.style.header.logo.model_dump(exclude={'asset'})
    text = saved['text']
    assert "# The logo's place." in text and 'asset: logo' in text and 'text: "hr@example.com"' in text
    assert saved['branding'] == {'logoPlace': True, 'logo': 'data:image/png;base64,' + asset.bytes_base64, 'footer': 'hr@example.com'}
    assert (saved['bundled'], saved['edited']) == (True, True)
    # The YAML editor shows the same version, and saving it again changes nothing.
    assert config.read(TWO)['text'] == text and config.check(TWO, text)['valid'] is True


def test_a_jpeg_becomes_a_png_and_removing_it_keeps_the_place_and_the_email(tmp_path):
    config = TemplateConfig(tmp_path)
    assert config.save_branding(TWO, request(picture(400, 200, 'JPEG'), 'hr@example.com'))[1] is None
    assert logo_of(TemplateStore(tmp_path).current(TWO)).mime_type == 'image/png'
    saved, refused = config.save_branding(TWO, request(None, 'hr@example.com', remove=True))
    assert refused is None
    package = TemplateStore(tmp_path).current(TWO)
    assert package.revision == '1.4.2' and logo_of(package) is None and package.recipe.style.header.logo is not None
    assert not any(asset.role == 'logo' for asset in package.assets) and package.recipe.style.footer.text == 'hr@example.com'
    assert 'asset: logo' not in saved['text'] and 'assets/logo.png' not in saved['text']
    # Without a new logo and without removal the logo stays and only the email changes.
    config.save_branding(TWO, request(picture(), 'hr@example.com'))
    kept = config.save_branding(TWO, request(None, ''))[0]
    assert kept['branding']['logo'] is not None and kept['branding']['footer'] == ''


@pytest.mark.parametrize('logo, footer, template, path, message', [
    (None, 'not an email', TWO, '/footer', NOT_EMAIL),
    (base64.b64encode(b'not a picture').decode(), '', TWO, '/logo', NOT_IMAGE),
    ('%%%', '', TWO, '/logo', NOT_IMAGE),
    (base64.b64encode(b'GIF89a' + bytes(64)).decode(), '', TWO, '/logo', NOT_IMAGE),
    (base64.b64encode(bytes(LOGO_BYTES + 1)).decode(), '', TWO, '/logo', TOO_LARGE),
    (picture(10, 10), '', ONE, '/logo', NO_PLACE),
])
def test_a_refused_branding_saves_nothing(tmp_path, logo, footer, template, path, message):
    config = TemplateConfig(tmp_path)
    saved, refused = config.save_branding(template, request(logo, footer))
    assert saved is None and refused['error'] == {'path': path, 'message': message}
    assert not (tmp_path / 'identities.json').exists()


def test_a_template_without_a_logo_place_takes_a_footer_email(tmp_path):
    saved, refused = TemplateConfig(tmp_path).save_branding(ONE, request(None, 'jobs@example.org'))
    assert refused is None and saved['branding'] == {'logoPlace': False, 'logo': None, 'footer': 'jobs@example.org'}


def test_yaml_edits_keep_the_text_around_them():
    text = 'a:\n  # note\n  b: 1\n  c:\n  d:\n    e: 2\n    f: 3\n  g: x\nh: {i: 1}\n'
    assert edited_yaml(text, [(('a', 'b'), '5')]) == text.replace('  b: 1', '  b: 5')
    assert edited_yaml(text, [(('a', 'c'), 'y')]) == text.replace('  c:\n', '  c: y\n')
    assert edited_yaml(text, [(('a', 'd'), None)]) == 'a:\n  # note\n  b: 1\n  c:\n  g: x\nh: {i: 1}\n'
    assert edited_yaml(text, [(('a', 'k'), 'z')]) == 'a:\n  # note\n  k: z\n  b: 1\n  c:\n  d:\n    e: 2\n    f: 3\n  g: x\nh: {i: 1}\n'
    assert edited_yaml(text, [(('a', 'd'), '{e: 4}')]).startswith('a:\n  # note\n  d: {e: 4}\n  b: 1\n  c:\n  g: x\n')
    # Removing a key the text lacks changes nothing.
    assert edited_yaml(text, [(('a', 'missing'), None)]) == text
    # A flow mapping or a missing parent is not edited here.
    assert edited_yaml(text, [(('h', 'i'), '2')]) is None and edited_yaml(text, [(('x', 'y'), '1')]) is None


def test_removing_a_logo_the_template_lacks_only_sets_the_email(tmp_path):
    saved, refused = TemplateConfig(tmp_path).save_branding(TWO, request(None, 'hr@example.com', remove=True))
    assert refused is None and saved['branding'] == {'logoPlace': True, 'logo': None, 'footer': 'hr@example.com'}
    assert 'asset:' not in saved['text'].split("# The logo's place.", 1)[1].split('divider:', 1)[0]


def test_a_json_template_is_written_again_with_its_logo_and_email(tmp_path):
    # The import fixtures keep their template as JSON; it has no comments, so it is written again.
    from tests.templates.employment_fixtures import employment_package
    package = employment_package()
    TemplateStore(tmp_path).activate(package)
    config = TemplateConfig(tmp_path)
    assert config.read(package.id)['format'] == 'json'
    saved, refused = config.save_branding(package.id, request(picture(300, 100), 'jobs@example.org'))
    # Its text stays JSON (which YAML reads too, so the compiler records it as YAML, as a Settings save of JSON does).
    assert refused is None and json.loads(saved['text'])['style']['footer']['text'] == 'jobs@example.org'
    current = TemplateStore(tmp_path).current(package.id)
    assert logo_of(current).path == 'assets/logo.png' and current.recipe.style.footer.text == 'jobs@example.org'
    # The earlier logo's declaration went with it.
    assert [asset.id for asset in current.assets if asset.role == 'logo'] == ['logo']
    # A second save reads the saved JSON text again.
    assert config.save_branding(package.id, request(None, 'hr@example.org'))[1] is None
    assert TemplateStore(tmp_path).current(package.id).recipe.style.footer.text == 'hr@example.org'


@pytest.mark.asyncio
async def test_routes_read_and_save_branding_for_imports_made_after_it(tmp_path):
    async with app_client(tmp_path, call_cap=4, provider=ScriptedTemplateProvider()) as (client, _app):
        path = '/v1/rich/template-config/' + TWO + '/branding'
        assert (await client.get(path)).json() == {'schemaVersion': 1, 'logoPlace': True, 'logo': None, 'footer': ''}
        refused = await client.put(path, json={'footer': 'nobody'})
        assert refused.status_code == 422 and refused.json()['error']['message'] == NOT_EMAIL
        saved = await client.put(path, json={'logo': picture(600, 200), 'footer': 'hr@example.com'})
        assert saved.status_code == 200, saved.text
        assert saved.json()['branding']['footer'] == 'hr@example.com' and saved.json()['package']['revision'] == '1.4.1'
        workspace = (await upload(client, template_id=TWO)).json()['workspace']
        captured = workspace['preDraft']['templatePackage']
        assert captured['packageHash'] == saved.json()['package']['packageHash']
        assert (await client.get('/v1/rich/template-config/missing/branding')).status_code == 404


def test_the_bundled_files_still_name_every_shipped_template():
    assert BUNDLED_TEMPLATES[TWO] == BUNDLED_TEMPLATE


@pytest.mark.slow
@pytest.mark.asyncio
async def test_an_export_with_an_own_logo_and_email_carries_both(tmp_path):
    from lxml import etree
    from packages.resume_core.templates.compiler import sha256
    store_root = tmp_path / 'store'
    TemplateConfig(store_root).save_branding(TWO, request(picture(900, 300), 'hr@example.com'))
    branded = TemplateStore(store_root).current(TWO)
    _fixture, result, workspace, originals = await generic_import(tmp_path / 'import', 'F10', package=branded)
    assert result.state == 'published'
    archive = parts(await export_through_service(tmp_path / 'export', workspace, originals))
    logo = logo_of(branded)
    headers = [name for name in archive if name.startswith('word/header') and name.endswith('.xml')]
    pictures = {sha256(archive['word/' + relation.get('Target')]) for name in headers
        for relation in etree.fromstring(archive['word/_rels/' + name.removeprefix('word/') + '.rels'])
        if relation.get('Type').endswith('/image')}
    assert pictures == {logo.sha256}
    footers = [name for name in archive if name.startswith('word/footer') and name.endswith('.xml')]
    assert footers and all('hr@example.com' in ''.join(etree.fromstring(archive[name]).itertext()) for name in footers)
