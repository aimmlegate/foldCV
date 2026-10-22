"""New-version tree edits retain extension state and authored presentation."""

from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.rich_fields import occurrences
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.template_facts import human_edit
from packages.resume_core.template_inverse import inverse_template_mutation
from tests.templates.storage_fixtures import workspace
from tests.templates.test_transactions import authorization


def mutation(value, block, identifier, kind='typing'):
    return TemplateMutationV1(schemaVersion=1, projectId=value.project_id,
        clientMutationId=identifier, actionId=identifier, kind=kind,
        capture={'sessionId': 'synthetic-session', 'actionId': identifier, 'actionToken': 1, 'dependencies': []},
        steps=[{'kind': 'put_block', 'parentId': 'main', 'afterId': None,
            'beforeRevision': value.project.document.regions[2].blocks[0].revision,
            'block': block.model_dump(by_alias=True)}], history={'kind': 'edit', 'originActionId': None})


def test_v7_tree_edit_undo_redo_keeps_cells_bindings_and_presentation():
    before, _ = workspace()
    before.project.facts = human_edit(before.project.facts, 'paper-b', 'year', 'forthcoming')
    original = before.project.document.regions[2].blocks[0].model_copy(deep=True)
    changed = original.model_copy(deep=True)
    changed.content[0].text = 'Human title'
    edited, replayed = apply_rich_mutation(before, mutation(before, changed, 'edit'))
    assert not replayed and edited.schema_version == 7
    assert edited.project.facts == before.project.facts
    assert edited.project.document.regions[2].blocks[0].presentation == original.presentation
    assert occurrences(edited.project.document)[('paper-a', 'title', 'occurrence-paper-a')].text == 'Human title'
    undo = inverse_template_mutation(before, edited, origin_action_id='edit', mutation_id='undo', session_id='session', action_token=2)
    undone, _ = apply_rich_mutation(edited, undo, history_authorization=authorization(edited, undo))
    redo = inverse_template_mutation(edited, undone, origin_action_id='edit', mutation_id='redo', session_id='session', action_token=3, kind='redo')
    redone, _ = apply_rich_mutation(undone, redo, history_authorization=authorization(undone, redo))
    assert undone.project.document.regions[2].blocks[0].content == original.content
    assert redone.project.document.regions[2].blocks[0].content[0].text == 'Human title'
    assert redone.project.facts == before.project.facts
    assert redone.document_revision == 4
    repeated, replayed = apply_rich_mutation(redone, redo)
    assert replayed and repeated == redone


def test_v7_builtin_record_edit_preserves_generic_fields():
    before, _ = workspace()
    block = before.project.document.regions[2].blocks[0]
    request = mutation(before, block, 'add-candidate').model_dump(by_alias=True)
    request['steps'] = [{'kind': 'put_record', 'beforeRevision': None,
        'record': {'id': 'candidate', 'revision': 1, 'origin': 'user', 'evidence': [], 'kind': 'candidate',
            **{key: {'value': text, 'rawText': text, 'status': 'known', 'revision': 1, 'pendingRawText': None}
                for key, text in [('name', 'Alex Example'), ('title', 'Engineer'), ('location', 'Example City')]}}}]
    changed, _ = apply_rich_mutation(before, TemplateMutationV1.model_validate(request))
    assert changed.schema_version == 7
    assert changed.project.facts.extensions == before.project.facts.extensions
    assert changed.project.facts.records[0].name.value == 'Alex Example'
    assert changed.project.facts.schema_version == 2
