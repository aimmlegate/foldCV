"""Template store: bundled templates by id, the version saved last for each id, and the default for new imports."""

import shutil

import pytest

from packages.resume_core.storage import atomic_write
from packages.resume_core.templates import store as module
from packages.resume_core.templates.compiler import canonical, compile_bytes, compile_template
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import BUNDLED_TEMPLATE, TemplateStore, UnknownTemplate
from tests.templates.employment_fixtures import employment_package

GENERIC, SECOND = 'generic-two-column', 'second-one-column'


def second_bundled(tmp_path, monkeypatch):
    """A synthetic second bundled template: the two-column files under another id and name."""
    folder = tmp_path / 'bundled-second'
    shutil.copytree(BUNDLED_TEMPLATE.parent, folder)
    text = BUNDLED_TEMPLATE.read_text(encoding='utf-8')
    text = text.replace(f'  id: {GENERIC}\n', f'  id: {SECOND}\n', 1).replace('  name: Две колонки\n', '  name: Second CV\n', 1)
    (folder / 'template.yaml').write_text(text, encoding='utf-8')
    monkeypatch.setattr(module, 'BUNDLED_TEMPLATES', {GENERIC: BUNDLED_TEMPLATE, SECOND: folder / 'template.yaml'})
    return folder / 'template.yaml'


def revised(path, revision, name):
    """A compiled edit of a bundled file: another revision and name, same id."""
    text = path.read_text(encoding='utf-8')
    bundled = compile_template(path)
    text = text.replace(f'  revision: {bundled.revision}\n', f'  revision: {revision}\n', 1)
    text = text.replace(f'  name: {bundled.definition.template.name}\n', f'  name: {name}\n', 1)
    return compile_bytes(text.encode('utf-8'), path.parent)


def listed(store):
    default_id, templates = store.templates()
    return default_id, [(package.id, package.revision, bundled is not None) for package, bundled in templates]


def test_an_empty_store_offers_every_bundled_template_and_the_first_is_the_default(tmp_path, monkeypatch):
    second = second_bundled(tmp_path, monkeypatch)
    store = TemplateStore(tmp_path / 'data')
    revision = compile_template(BUNDLED_TEMPLATE).revision
    assert listed(store) == (GENERIC, [(GENERIC, revision, True), (SECOND, revision, True)])
    assert store.active().id == GENERIC and store.current(SECOND).package_hash == compile_template(second).package_hash
    assert not (tmp_path / 'data').exists()


def test_saving_one_template_keeps_the_other_and_the_default(tmp_path, monkeypatch):
    second = second_bundled(tmp_path, monkeypatch)
    store = TemplateStore(tmp_path / 'data')
    edited = revised(second, '9.0.0', 'Second edited')
    store.save(edited)
    assert store.current(SECOND).package_hash == edited.package_hash
    assert store.current(GENERIC).package_hash == compile_template(BUNDLED_TEMPLATE).package_hash
    assert store.active().id == GENERIC
    store.set_default(SECOND)
    assert store.active().package_hash == edited.package_hash
    generic = revised(BUNDLED_TEMPLATE, '9.0.0', 'Generic edited')
    store.save(generic)
    assert store.default_id() == SECOND and store.current(GENERIC).package_hash == generic.package_hash
    # The ID+revision rule holds per id: the same revision with other bytes is refused and changes nothing.
    other = revised(second, '9.0.0', 'Second other')
    with pytest.raises(SchemaFailure, match='already identifies'):
        store.save(other)
    assert store.current(SECOND).package_hash == edited.package_hash
    store.reset(SECOND)
    assert store.current(SECOND).package_hash == compile_template(second).package_hash
    assert store.default_id() == SECOND and store.current(GENERIC).package_hash == generic.package_hash


def test_a_schema_1_pointer_is_the_current_version_of_its_id_and_the_default(tmp_path, monkeypatch):
    second_bundled(tmp_path, monkeypatch)
    store = TemplateStore(tmp_path / 'data')
    legacy = revised(BUNDLED_TEMPLATE, '8.0.0', 'Saved before')
    # The layout an earlier version wrote: one package and one pointer to it.
    atomic_write(store.root / legacy.package_hash / 'package.json', canonical(legacy))
    atomic_write(store.root / 'identities.json', canonical({canonical([legacy.id, legacy.revision]).decode(): legacy.package_hash}))
    atomic_write(store.root / 'active.json', canonical({'schemaVersion': 1, 'packageHash': legacy.package_hash}))
    store.set_default(GENERIC)
    assert store.active().package_hash == legacy.package_hash
    store.set_default(SECOND)
    assert store.active().id == SECOND and store.current(GENERIC).package_hash == legacy.package_hash
    store.reset(GENERIC)
    assert store.current(GENERIC).package_hash == compile_template(BUNDLED_TEMPLATE).package_hash


def test_a_schema_1_pointer_to_an_id_the_app_does_not_ship_stays_listed_and_default(tmp_path, monkeypatch):
    second_bundled(tmp_path, monkeypatch)
    store = TemplateStore(tmp_path / 'data')
    custom = employment_package()
    atomic_write(store.root / custom.package_hash / 'package.json', canonical(custom))
    atomic_write(store.root / 'active.json', canonical({'schemaVersion': 1, 'packageHash': custom.package_hash}))
    before = (store.root / 'active.json').read_bytes()
    default_id, templates = listed(store)
    assert default_id == custom.id and [value[0] for value in templates] == [GENERIC, SECOND, custom.id]
    assert templates[2][2] is False and (store.root / 'active.json').read_bytes() == before
    with pytest.raises(UnknownTemplate):
        store.reset(custom.id)


def test_unknown_ids_are_refused_and_change_nothing(tmp_path, monkeypatch):
    second_bundled(tmp_path, monkeypatch)
    store = TemplateStore(tmp_path / 'data')
    store.set_default(SECOND)
    before = (store.root / 'active.json').read_bytes()
    for call in (store.current, store.set_default, store.reset):
        with pytest.raises(UnknownTemplate):
            call('missing')
    assert (store.root / 'active.json').read_bytes() == before


def test_a_default_that_an_update_no_longer_ships_falls_back_to_the_first_bundled(tmp_path, monkeypatch):
    second_bundled(tmp_path, monkeypatch)
    store = TemplateStore(tmp_path / 'data')
    store.set_default(SECOND)
    monkeypatch.setattr(module, 'BUNDLED_TEMPLATES', {GENERIC: BUNDLED_TEMPLATE})
    assert listed(store)[0] == GENERIC and store.active().id == GENERIC


@pytest.mark.parametrize('pointer', [
    {'schemaVersion': 2, 'defaultId': GENERIC},
    {'schemaVersion': 2, 'defaultId': 7, 'current': {}},
    {'schemaVersion': 2, 'defaultId': None, 'current': {GENERIC: 'not-a-hash'}},
    {'schemaVersion': 3, 'defaultId': None, 'current': {}},
])
def test_a_damaged_pointer_fails_explicitly(tmp_path, pointer):
    store = TemplateStore(tmp_path)
    atomic_write(store.root / 'active.json', canonical(pointer))
    with pytest.raises(SchemaFailure):
        store.active()
