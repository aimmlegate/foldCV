"""The anonymized export (D186): the short name, contacts left out by pattern, the blocks of the candidate's own links
left out whole, and nothing of the project changed. Synthetic data only (the F10 fixture with invented contacts)."""

import asyncio
import zipfile
from io import BytesIO

import pytest

from packages.resume_core.editing.anonymize import _contacts, anonymized, contact_only, default_name, preview, short_name
from packages.resume_core.hashing import canonical
from packages.resume_core.models.template_document import PresentedText, TemplateParagraphBlock
from packages.resume_core.models.template_workspace import AnonymizedName
from tests.templates.generic_fixtures import generic_import

CONTACT_LINE = 'Тел.: +7 (900) 123-45-67 · alex@example.com'
SENTENCE = 'Пишите на alex@example.com или в Telegram @alexqueue, отвечу быстро.'
PROFILE = 'Профиль: github.com/alexqueue'
PRODUCT = 'Продукт: https://queue.example.com, Kafka 4.0, 2019–2021, @Override в коде.'


@pytest.mark.parametrize(('full', 'short'), [
    ('Иван Петров', 'Иван П.'), ('Петров Иван Сергеевич', 'Иван П.'), ('Иван Сергеевич Петров', 'Иван П.'),
    ('Петрова Анна Ильинична', 'Анна П.'), ('Анна-Мария Петрова-Водкина', 'Анна-Мария П.'), ('Ivan Petrov', 'Ivan P.'),
    ('Petrov Ivan Sergeevich', 'Ivan P.'), ('Ivan Sergeevich Petrov', 'Ivan P.'), ('Мадонна', 'Мадонна'), ('', ''),
    ('  ', ''), ('Jean Paul Marie Dupont', 'Jean D.'), ('anna smith', 'anna S.')])
def test_the_short_name_is_the_first_name_and_the_family_initial(full, short):
    assert short_name(full) == short


@pytest.mark.parametrize(('text', 'kinds'), [
    ('alex@example.com', ['почта']), ('+7 (900) 123-45-67', ['телефон']), ('8 900 123 45 67', ['телефон']),
    ('+1 415 555 0100', ['телефон']), ('https://t.me/alexqueue', ['ссылка на профиль']),
    ('linkedin.com/in/alex', ['ссылка на профиль']), ('Telegram: @alexqueue', ['мессенджер']),
    ('https://alex.github.io', ['ссылка на профиль']),
    # Near misses that stay: a version, a year range, a date, a product link, an «@» in code text, a long number in text.
    ('Kafka 4.0.1', []), ('2019–2021', []), ('2019-2021 1.2.3.4', []), ('01.02.2023', []),
    ('https://queue.example.com', []), ('@Override public void run()', []), ('v10.2.3.4567', []),
    ('ИНН проекта 2019 2021', [])])
def test_contacts_are_found_by_pattern_and_near_misses_stay(text, kinds):
    assert [kind for _start, _end, kind in _contacts(text)] == kinds


@pytest.mark.parametrize(('text', 'only'), [(CONTACT_LINE, True), ('E-mail: alex@example.com', True), (PROFILE, True),
    ('Telegram: @alexqueue; Skype: @alexq', True), (SENTENCE, False), (PRODUCT, False), ('Москва', False)])
def test_a_line_of_contact_data_only_is_told_apart_from_a_sentence(text, only):
    assert contact_only(text) is only


@pytest.fixture(scope='module')
def imported(tmp_path_factory):
    _fixture, _result, workspace, sources = asyncio.run(generic_import(tmp_path_factory.mktemp('anonymized'), 'F10'))
    return workspace, sources


def line(identifier, text, ref):
    return TemplateParagraphBlock(type='paragraph', id=identifier, revision=1, props={}, children=[], provenance=[],
        presentation=ref, content=[PresentedText(type='text', text=text, styles={}, presentation=ref)])


def with_contacts(workspace, contacts_block=False):
    """F10 with a contacts line, a sentence with contacts and a profile line in «О себе», a product link in the job; with
    `contacts_block` the location block holds only contact lines, as a custom template's contacts block would."""
    value = workspace.model_copy(deep=True)
    sections = {block.presentation.view_key: block for block in value.project.document.blocks()
                if block.type == 'section' and block.presentation is not None and block.presentation.view_key}
    summary = sections['summary']
    ref = summary.children[0].presentation
    summary.children += [line('contact-line', CONTACT_LINE, ref), line('contact-sentence', SENTENCE, ref),
                         line('profile-line', PROFILE, ref)]
    job = sections['projects']
    job.children.append(line('product-line', PRODUCT, job.children[-1].presentation))
    if contacts_block:
        location = sections['location']
        gone = {block.id for child in location.children for block in [child, *child.children]}
        location.children = [line('telegram-line', 'Telegram: @alexqueue', location.children[0].presentation),
                             line('mail-line', 'alex@example.com', location.children[0].presentation)]
        for item in [*value.project.import_coverage, *value.project.import_issues]:
            item.block_ids = [identifier for identifier in item.block_ids if identifier not in gone]
    return type(value).model_validate(value.model_dump(by_alias=True))


def text_of(document):
    return ' '.join(getattr(span, 'text', '') or ''.join(getattr(child, 'text', '') for child in getattr(span, 'content', []))
                    for block in document.blocks() for span in (block.content if isinstance(block.content, list) else []))


def test_the_copy_leaves_out_contacts_and_link_blocks_and_keeps_everything_else(imported):
    workspace = with_contacts(imported[0])
    raw = canonical(workspace)
    document, notices = anonymized(workspace.project, 'Alex E.')
    assert canonical(workspace) == raw
    text, ids = text_of(document), {block.id for block in document.blocks()}
    assert 'Alex E.' in text and 'Alex Example' not in text
    # A4-c: the contacts line and the profile line go whole; A4-d: the sentence keeps its words, not its contacts.
    assert 'contact-line' not in ids and 'profile-line' not in ids
    sentence = next(block for block in document.blocks() if block.id == 'contact-sentence').content[0].text
    assert 'alex@example.com' not in sentence and '@alexqueue' not in sentence and 'отвечу быстро' in sentence
    assert {notice['kind'] for notice in notices} >= {'contact', 'family'}
    # A4-e, A4-f: a product link, a version, a year range and code text stay; so do the location, employers and dates.
    assert PRODUCT in text and 'Example City' in text and 'Example Labs' in text and '03.2020' in text
    # A4-b: «Open source» goes whole, heading included.
    assert not any(block.presentation is not None and block.presentation.view_key == 'opensource' for block in document.blocks())
    assert 'OPEN SOURCE' not in text and 'Queue Tools' not in text


def test_a_custom_contacts_block_goes_whole_with_its_heading(imported):
    workspace = with_contacts(imported[0], contacts_block=True)
    document, _notices = anonymized(workspace.project, 'Alex E.')
    assert not any(block.presentation is not None and block.presentation.view_key == 'location' for block in document.blocks())
    assert 'ЛОКАЦИЯ' not in text_of(document)


def test_an_empty_name_leaves_the_name_line_out(imported):
    workspace = imported[0]
    document, _notices = anonymized(workspace.project, '')
    assert 'Alex' not in text_of(document) and 'Backend engineer' in text_of(document)


def test_the_dialog_takes_the_remembered_name_until_the_full_name_changes(imported):
    workspace = imported[0].model_copy(deep=True)
    assert default_name(workspace.project) == 'Alex E.'
    workspace.project.anonymized_name = AnonymizedName(name='A. E.', fullName='Alex Example')
    assert default_name(workspace.project) == 'A. E.'
    workspace.project.anonymized_name = AnonymizedName(name='A. E.', fullName='Someone Else')
    assert default_name(workspace.project) == 'Alex E.'
    shown = preview(workspace.project, 'Al E.')
    assert shown['name'] == 'Al E.' and shown['proposal'] == 'Alex E.' and shown['leftOut'].startswith('Скрываем:')
    assert any(text == 'Al E.' for text in shown['texts'].values())


def test_a_hidden_block_stays_hidden_and_the_store_is_not_read_or_changed(imported):
    from tests.templates.test_panel_hide import hide
    workspace = with_contacts(imported[0])
    hidden = hide(workspace, 'summary', view='summary').preview.workspace
    store = canonical([entry.model_dump(mode='json', by_alias=True) for entry in hidden.project.hidden_blocks])
    document, _notices = anonymized(hidden.project, 'Alex E.')
    assert 'reliable queue systems' not in text_of(document) and canonical([entry.model_dump(mode='json', by_alias=True) for entry in hidden.project.hidden_blocks]) == store


def test_the_routes_export_an_anonymized_docx_remember_the_name_and_change_nothing_else(tmp_path, imported):
    from packages.resume_core.repository.archive_zip import write_zip
    from packages.resume_core.repository.template_archive import archive_payload_v7, open_archive_v7
    from tests.projects.support import Editor, v2_app
    workspace, sources = imported
    workspace = with_contacts(workspace)
    with v2_app(tmp_path / 'app', [(workspace, sources)]) as (client, application):
        editor = Editor(client, workspace.project_id)
        before = editor.workspace()
        shown = editor.call('post', '/anonymized', {})
        assert shown['name'] == 'Alex E.' and shown['notices'] and 'contact-line' in shown['removed']
        snapshot = editor.response['snapshot']
        reply = client.post('/v2/projects/' + workspace.project_id + '/export', json={'schemaVersion': 1, 'snapshot': snapshot,
            'editorToken': editor.token, 'anonymizedName': 'Alex E.'})
        assert reply.status_code == 200, reply.text[:300]
        package = zipfile.ZipFile(BytesIO(reply.content))
        body = package.read('word/document.xml').decode() + ''.join(
            package.read(name).decode() for name in package.namelist() if name.startswith('word/header') or name.startswith('word/footer'))
        core = package.read('docProps/core.xml').decode()
        for secret in ('Alex Example', 'alex@example.com', '123-45-67', '@alexqueue', 'github.com/alexqueue', 'Queue Tools'):
            assert secret not in body and secret not in core, secret
        assert 'Alex E.' in body and 'Example Labs' in body
        current = application.state.projects.repository.read(workspace.project_id)
        assert current.project.document == before.project.document and current.project.facts == before.project.facts
        assert current.project.anonymized_name == AnonymizedName(name='Alex E.', fullName='Alex Example')
        assert current.project.exports == before.project.exports
        # The PDF path remembers its name by its own route; the history has no action of it.
        editor.call('post', '/anonymized/name', {'editorToken': editor.token, 'name': 'A. E.'})
        reopened = Editor(client, workspace.project_id)
        assert reopened.workspace().project.anonymized_name.name == 'A. E.'
        assert reopened.history.get('undo') is None or reopened.history['undo']['actionId'] != 'anonymized'
        transferred, _retained, _, _ = open_archive_v7(write_zip(archive_payload_v7(reopened.workspace(), sources, {})), 'anon-transfer')
        assert transferred.project.anonymized_name.name == 'A. E.'
