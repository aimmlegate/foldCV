"""The résumé photo (D187): the image check, add, replace, remove, Undo and Redo through the project history, reopen,
portable transfer, DOCX with the photo, the anonymized export without it, the default place for older templates.
Every image here is drawn by the test (gradients and shapes); no photo of a person."""

import asyncio
import base64
import zipfile
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from packages.resume_core.image_check import check_image
from packages.resume_core.templates.photo import photo_growth, photo_place
from packages.resume_core.templates.store import bundled_package, shipped_templates
from tests.templates.generic_fixtures import generic_import


def drawn(size=800, kind='JPEG', exif=False, text=False, frames=1, mode='RGB'):
    image = Image.new(mode, (size if isinstance(size, int) else size[0], size if isinstance(size, int) else size[1]), (40, 90, 160))
    draw = ImageDraw.Draw(image)
    draw.ellipse([image.width // 4, image.height // 4, image.width * 3 // 4, image.height * 3 // 4], fill=(230, 180, 60))
    raw = BytesIO()
    options = {}
    if exif:
        data = Image.Exif()
        data[0x010F] = 'Synthetic Camera'
        options['exif'] = data.tobytes()
    if text:
        from PIL.PngImagePlugin import PngInfo
        info = PngInfo()
        info.add_text('Comment', 'synthetic')
        options['pnginfo'] = info
    if frames > 1:
        others = [Image.new(mode, image.size, (index * 40, 0, 0)) for index in range(1, frames)]
        image.save(raw, format='PNG', save_all=True, append_images=others)
    else:
        image.save(raw, format=kind, **options)
    return raw.getvalue()


@pytest.mark.parametrize(('data', 'kind', 'code'), [
    (lambda: drawn(800), 'photo', None), (lambda: drawn(400, 'PNG'), 'photo', None),
    (lambda: drawn(256, 'PNG', mode='RGBA'), 'icon', None),
    (lambda: b'', 'photo', 'IMAGE_INVALID'), (lambda: b'%PDF-1.7 not an image', 'photo', 'IMAGE_INVALID'),
    (lambda: drawn(800)[:200], 'photo', 'IMAGE_INVALID'), (lambda: drawn(800, exif=True), 'photo', 'IMAGE_METADATA'),
    (lambda: drawn(400, 'PNG', text=True), 'photo', 'IMAGE_METADATA'), (lambda: drawn(64, 'PNG', frames=3), 'photo', 'IMAGE_ANIMATED'),
    (lambda: drawn((800, 600)), 'photo', 'IMAGE_SIZE'), (lambda: drawn(900), 'photo', 'IMAGE_SIZE'),
    (lambda: drawn(800), 'icon', 'IMAGE_INVALID'), (lambda: drawn(128, 'PNG'), 'icon', 'IMAGE_SIZE'),
    (lambda: b'\xff\xd8\xff' + b'0' * (3 * 1024 * 1024), 'photo', 'IMAGE_TOO_LARGE')])
def test_an_added_image_is_checked_again_in_python(data, kind, code):
    if code is None:
        checked = check_image(data(), kind)
        assert checked.width == checked.height
    else:
        with pytest.raises(ValueError, match=code):
            check_image(data(), kind)


def test_every_bundled_template_has_a_photo_place_in_its_present_header():
    places = {}
    for template in shipped_templates():
        recipe = bundled_package(template).recipe
        place = photo_place(recipe)
        assert photo_growth(recipe) == 0 and place.size >= 40 and place.radius > 0
        places[template] = place.size
    assert places == {'generic-two-column': 61.33, 'generic-one-column': 42.0, 'generic-skills-table': 43.0,
                      'generic-questionnaire': 51.0, 'generic-project-cards': 58.0}


@pytest.fixture(scope='module')
def imported(tmp_path_factory):
    _fixture, _result, workspace, sources = asyncio.run(generic_import(tmp_path_factory.mktemp('photo'), 'F10'))
    return workspace, sources


def body(editor, image, identifier):
    return {'editorToken': editor.token, 'baseRevision': editor.revision, 'clientMutationId': identifier,
            'image': None if image is None else base64.b64encode(image).decode()}


def docx_parts(content):
    package = zipfile.ZipFile(BytesIO(content))
    return package, {name: package.read(name) for name in package.namelist()}


def export(client, editor, project, **extra):
    reply = client.post('/v2/projects/' + project + '/export', json={'schemaVersion': 1, 'snapshot': editor.response['snapshot'],
        'editorToken': editor.token, **extra})
    assert reply.status_code == 200, reply.text[:300]
    return reply.content


def test_a_photo_is_one_history_action_kept_on_reopen_and_transfer_and_in_the_docx(tmp_path, imported):
    from packages.resume_core.repository.archive_zip import write_zip
    from packages.resume_core.repository.template_archive import open_archive_v7
    from tests.projects.support import Editor, v2_app
    workspace, sources = imported
    first, second = drawn(800), drawn(600, 'PNG')
    with v2_app(tmp_path / 'app', [(workspace, sources)]) as (client, application):
        editor = Editor(client, workspace.project_id)
        plain = export(client, editor, workspace.project_id)
        editor = Editor(client, workspace.project_id)
        editor.adopt(editor.call('put', '/photo', body(editor, first, 'photo-add')))
        assert editor.workspace().project.photo.width == 800 and editor.history['undo']['actionId'] == 'photo-add'
        plan = editor.response['presentation']['editor']['photo']
        assert plan['size'] == 61.33 and plan['shift'] > plan['size'] and plan['url'].endswith(editor.workspace().project.photo.sha256)
        assert client.get(plan['url']).content == first
        with_photo = export(client, editor, workspace.project_id)
        editor = Editor(client, workspace.project_id)
        _package, parts = docx_parts(with_photo)
        assert any(name.startswith('word/media/') for name in parts) and b'Photo' in parts['word/header1.xml']
        assert not any(name.startswith('word/media/') for name in docx_parts(plain)[1]) or len(docx_parts(plain)[1]) < len(parts)
        # The anonymized export leaves the photo out.
        anonymous = docx_parts(export(client, editor, workspace.project_id, anonymizedName='Alex E.'))[1]
        assert b'Photo' not in anonymous['word/header1.xml']
        editor = Editor(client, workspace.project_id)
        # Replace, Undo, Redo, remove: each one step through the project history; the files stay while history needs them.
        editor.adopt(editor.call('put', '/photo', body(editor, second, 'photo-replace')))
        assert editor.workspace().project.photo.mime_type == 'image/png'
        editor.step('undo', 'undo-replace')
        assert editor.workspace().project.photo.sha256 == editor.workspace().project.photo.sha256 and editor.workspace().project.photo.width == 800
        editor.step('undo', 'undo-add')
        assert editor.workspace().project.photo is None and 'photo' not in editor.response['presentation']['editor']
        editor.step('redo', 'redo-add')
        editor.step('redo', 'redo-replace')
        assert editor.workspace().project.photo.width == 600
        application.state.projects.repository.sweep_assets(workspace.project_id)
        editor.step('undo', 'undo-replace-again')
        assert client.get(editor.response['presentation']['editor']['photo']['url']).content == first
        editor.adopt(editor.call('put', '/photo', body(editor, None, 'photo-remove')))
        assert editor.workspace().project.photo is None
        editor.step('undo', 'undo-remove')
        reopened = Editor(client, workspace.project_id)
        assert reopened.workspace().project.photo.width == 800
        archive = client.post('/v2/projects/' + workspace.project_id + '/archive', json={'editorToken': reopened.token,
            'projectRevision': reopened.revision, 'documentRevision': reopened.workspace().document_revision})
        assert archive.status_code == 200, archive.text[:300]
        transferred, _originals, _artifacts, images = open_archive_v7(archive.content, 'photo-transfer')
        assert transferred.project.photo.sha256 == reopened.workspace().project.photo.sha256
        assert images[transferred.project.photo.id] == first
        # A refused image changes nothing.
        refused = reopened.refused('put', '/photo', body(reopened, drawn(800, exif=True), 'photo-exif'), 422)
        assert refused['error']['code'] == 'IMAGE_METADATA'


def test_a_hidden_block_leaves_the_photo_as_it_is(tmp_path, imported):
    from tests.projects.support import Editor, v2_app
    from tests.templates.test_panel_creation import request
    workspace, sources = imported
    with v2_app(tmp_path / 'app', [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        editor.adopt(editor.call('put', '/photo', body(editor, drawn(800), 'photo-before-hide')))
        photo = editor.workspace().project.photo
        value = request(editor.workspace(), operation='hide', kind=None, values={'view': 'summary'}, identifier='hide-with-photo')
        editor.edit(value.model_dump(mode='json', by_alias=True))
        assert editor.workspace().project.photo == photo
        editor.step('undo', 'undo-hide-with-photo')
        assert editor.workspace().project.photo == photo


def test_a_resume_of_an_earlier_template_revision_gets_a_photo_at_the_default_place(tmp_path):
    from packages.resume_core.models.template_render import TemplateRenderPhoto, TemplateRenderRequestV1, snapshot_identity
    from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
    from packages.resume_core.responses.template_export import capture_export
    from tests.templates.generic_fixtures import two_column_1_6
    from tests.templates.test_lite_import import lite_run
    fixture, _operation = lite_run(tmp_path / 'import', 'promotions', package=two_column_1_6())
    workspace = fixture.current()
    assert workspace.project.template_package.revision == '1.6.0' and workspace.project.template_package.recipe.style.header.photo is None
    data = drawn(800)
    import hashlib
    photo = TemplateRenderPhoto(sha256=hashlib.sha256(data).hexdigest(), mimeType='image/jpeg', bytesBase64=base64.b64encode(data).decode())
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity(), photo=photo)
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=workspace.project.template_package)
    (tmp_path / 'render').mkdir()
    _package, parts = docx_parts(render_captured_docx(request, tmp_path / 'render'))
    assert b'Photo' in parts['word/header1.xml']
    # Without a photo the capture holds no photo key, so its hashes and the DOCX stay as before D187.
    _attempt, plain = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    assert 'photo' not in plain.request.model_dump(by_alias=True)


@pytest.mark.parametrize('template', list(shipped_templates()))
def test_each_bundled_template_renders_the_photo_in_its_header(tmp_path, template):
    from packages.resume_core.models.template_render import TemplateRenderPhoto, TemplateRenderRequestV1, snapshot_identity
    from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
    from packages.resume_core.responses.template_export import capture_export
    import hashlib
    _fixture, _result, workspace, _sources = asyncio.run(generic_import(tmp_path / 'import', 'F10', package=bundled_package(template)))
    data = drawn(800)
    photo = TemplateRenderPhoto(sha256=hashlib.sha256(data).hexdigest(), mimeType='image/jpeg', bytesBase64=base64.b64encode(data).decode())
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity(), photo=photo)
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=workspace.project.template_package)
    (tmp_path / 'render').mkdir()
    _package, parts = docx_parts(render_captured_docx(request, tmp_path / 'render'))
    assert b'Photo' in parts['word/header1.xml'] and any(name.startswith('word/media/') for name in parts)
