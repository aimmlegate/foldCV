"""PUT /v1/settings/legacy-import: whether the app starts the legacy import instead of the fast one. Off unless the
user turns it on; a fast import that chose no level runs at medium where the model offers it."""

from types import SimpleNamespace

import pytest

from packages.resume_core.repository.preferences import PreferencesStore
from packages.resume_core.storage import atomic_write
from resume_api.projects.errors import ProjectFailure
from resume_api.projects.intake import TemplateIntake
from tests.settings.support import application, client_session


def test_a_preferences_file_from_before_the_setting_reads_as_off_and_the_choice_survives_a_restart(tmp_path):
    store = PreferencesStore(tmp_path / 'store')
    store.load()
    atomic_write(store.path, b'{"schemaVersion":1,"automaticAnalysis":false,"theme":"light","selectedModel":"model-a"}')
    assert store.load().legacy_import is False
    store.save_legacy_import(True)
    saved = PreferencesStore(store.root).load()
    assert (saved.legacy_import, saved.selected_model) == (True, 'model-a')
    store.save_legacy_import(False)
    assert PreferencesStore(store.root).load().legacy_import is False


@pytest.mark.asyncio
async def test_the_route_saves_the_choice_and_leaves_the_other_settings(tmp_path):
    app = application(tmp_path, template_import_call_cap=4)
    async with app.app.router.lifespan_context(app.app), client_session(app) as client:
        path = '/v1/settings/legacy-import'
        before = (await client.get('/v1/settings/preferences')).json()
        assert before['legacyImport'] is False
        saved = await client.put(path, json={'legacyImport': True})
        assert saved.status_code == 200 and saved.json() == {**before, 'legacyImport': True}
        assert (await client.put(path, json={})).status_code == 422
        assert (await client.put(path, json={'legacyImport': 'yes'})).status_code == 422
        assert (await client.get('/v1/settings/preferences')).json()['legacyImport'] is True


def test_a_fast_import_with_no_chosen_level_runs_at_medium_where_the_model_offers_it():
    def catalog(supported, default):
        def model(effort=None):
            if effort is not None and effort not in supported:
                raise ProjectFailure('IMPORT_EFFORT_UNSUPPORTED', 409)
            return SimpleNamespace(effort=effort or default)
        return SimpleNamespace(model=model)
    # One rule for every model: medium when it is offered, else the model's own default.
    assert TemplateIntake.lite_model(catalog(['low', 'medium', 'high', 'xhigh'], 'high')).effort == 'medium'
    assert TemplateIntake.lite_model(catalog(['low', 'high'], 'high')).effort == 'high'

    def denied(effort=None):
        raise ProjectFailure('MODEL_DENIED', 409)
    with pytest.raises(ProjectFailure, match='MODEL_DENIED'):
        TemplateIntake.lite_model(SimpleNamespace(model=denied))
