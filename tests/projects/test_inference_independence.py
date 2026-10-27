"""Edits and exports on the v2 routes never wait for the inference permit that a model call holds (G4)."""

import threading

from resume_api.inference_admission import INFERENCE
from tests.projects.support import Editor, v2_app
from tests.projects.test_edit_routes import typing
from tests.projects.test_export import RENDERER, render
from tests.templates.storage_fixtures import workspace as papers

PROJECT = 'template-project'


def test_an_edit_and_an_export_finish_while_the_only_inference_permit_is_held(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        exports = application.state.projects.exports
        exports._renderer, exports.render = RENDERER, render
        editor = Editor(client, PROJECT)
        with INFERENCE.hold(threading.Event()):
            assert editor.edit(typing(editor, 'Human', 'edit-1'))['revision'] == 2
            reply = client.post('/v2/projects/' + PROJECT + '/export', json={'schemaVersion': 1, 'editorToken': editor.token,
                'snapshot': editor.response['snapshot']})
            assert reply.status_code == 200, reply.text[:300]
        saved = application.state.projects.repository.read(PROJECT)
        assert [item.state for item in saved.project.exports] == ['completed']
