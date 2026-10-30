"""The employment subset renders admitted cells and exact nonoverlapping source spans."""

from types import SimpleNamespace

import pytest

from packages.resume_core.models.template_document import FieldOccurrence
from packages.resume_core.models.template_import import TaskResultRecord
from packages.resume_core.template_assembly import assemble_template
from packages.resume_core.template_identity import capture_span, source_slice
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.templates.materialize import materialize
from packages.resume_core.templates.materialize_nodes import DisplayField, render_nodes
from packages.resume_core.templates.presentation import project_presentation, snapshot_identity
from packages.resume_core.templates.span_coverage import overlaps
from tests.templates.employment_fixtures import employment_package, employment_proposal, employment_source
from tests.templates.generic_fixtures import generic_package
from tests.templates.pipeline_fixtures import source_draft
from tests.templates.test_builtin_admission import accept, proposed_from


def admitted(fixture='F01', *, unsupported=False, rewrite=True, payload_edit=None):
    package = employment_package()
    src, raw = employment_source(fixture)
    reply = employment_proposal(src, unsupported=unsupported)
    if payload_edit:
        payload_edit(reply['payload'])
    operation, facts, proposed, _package, _src = proposed_from(package, src, reply, allow_text_rewrite=rewrite)
    bad = next((value for value in operation.allocations if value.key == 'results-entry'), None)
    operation, facts = accept(operation, facts, proposed, package, src,
        [bad.cell_ids['value']] if unsupported else [])
    if unsupported:
        evidence = next(field.evidence for field in proposed.resolved_fields if field.item_handle == bad.item_handle)
        fallback(operation, evidence)
    return operation, facts, package, src, raw


def fallback(operation, spans):
    task = operation.tasks[0]
    task.state = 'source_fallback'
    operation.task_results = [TaskResultRecord(id='exact-fallback', taskId=task.id, inputHash=task.input_hash,
        value=None, sourceSpans=spans, itemHandles=task.allowed_handles, issueIds=[], disposition='source_fallback')]


def text(document):
    return '\n'.join(''.join(part.text for part in block.content) for block in document.blocks())


@pytest.mark.parametrize('fixture', ['F01', 'F02'])
def test_one_employment_materializes_stable_editable_cells_and_optional_sections(fixture):
    operation, facts, package, src, _raw = admitted(fixture)
    before = canonical(facts)
    document, coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    repeated, repeated_coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    assert canonical(document) == canonical(repeated) and coverage == repeated_coverage
    assert canonical(facts) == before
    rendered = text(document)
    assert 'Example Labs' in rendered and 'Role: backend engineer' in rendered and 'Python' in rendered
    assert rendered.count('Implemented queue processing.') == 1
    assert ('Results:' in rendered) == (fixture == 'F01')
    assert ('03.2020–11.2023' if fixture == 'F01' else '2020–2023') in rendered
    occurrences = [part for block in document.blocks() for part in block.content if isinstance(part, FieldOccurrence)]
    claimed = {value.cell_ids['value'] for value in operation.allocations if value.semantic_type == 'claim'}
    assert claimed <= {part.cell_id for part in occurrences}
    assert len({part.binding_id for part in occurrences}) == len(occurrences)
    assert all(part.presentation.node_index is not None for part in occurrences)
    assert all(value.block_ids for value in coverage if value.disposition == 'accepted')


def test_an_ongoing_period_without_a_start_shows_its_label_alone():
    package = generic_package()
    view = next(value for value in package.definition.blocks if value.id == 'projects')
    ongoing = DisplayField(('period', 'ongoing'), 'job', 'handle', SimpleNamespace(id='present', typed_value=True,
        raw_input='true', manual_scope_id=None))
    blocks, _displayed = render_nodes(package, view, 'instance', [ongoing], {}, set(),
        {'separator': ' – ', 'ongoingLabel': {'ru': 'по настоящее время'}})
    assert [[part.text for part in block['content']] for block in blocks] == [['по настоящее время']]


def test_unbound_period_raw_never_becomes_current_document_text():
    operation, facts, package, src, _raw = admitted(payload_edit=lambda payload: payload[0]['period'].update(raw='Invented 1900–2100'))
    document, _coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    assert 'Invented' not in text(document) and '03.2020–11.2023' in text(document)


def test_rejected_metric_falls_back_once_without_duplicating_accepted_task_or_promoting_it():
    operation, facts, package, src, _raw = admitted(unsupported=True)
    document, coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    rendered = text(document)
    assert '80%' not in rendered
    assert rendered.count('Our team reduced median latency from 800 ms to 500 ms.') == 1
    assert rendered.count('Implemented queue processing.') == 1
    assert 'Example Labs' in rendered
    raw = [value for value in coverage if value.disposition == 'fallback']
    accepted = [value for value in coverage if value.disposition in {'accepted', 'multiple_views'}]
    assert len(raw) == 1 and not any(overlaps(left.span, right.span) for left in raw for right in accepted)
    assert all('80%' not in str(record.value.value) for record in facts.records if record.kind == 'claim')


def test_shared_unit_fallback_replaces_overlapping_rewrites_with_one_source_copy_and_retains_facts():
    operation, facts, package, src, _raw = admitted()
    before = canonical(facts)
    fallback(operation, [capture_span(src, src.units[0])])
    document, coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    # The block keeps its own title (S8, LIVE-09) and adds no diagnostic heading (5.3).
    assert [block.type for block in document.blocks()] == ['heading', 'paragraph']
    assert document.blocks()[0].content[0].text == 'PROJECTS'
    # The paragraph shows the unit without its closing line break; only that whitespace stays source-only.
    shown = document.blocks()[1].content[0]
    assert shown.text == src.units[0].text.rstrip('\n') and source_slice([src], shown.citations[0]) == shown.text
    assert all(not source_slice([src], value.span).strip() for value in coverage if value.disposition == 'source_only')
    assert not any(value.disposition in {'accepted', 'multiple_views'} for value in coverage)
    assert canonical(facts) == before


def test_fallback_places_disconnected_evidence_added_by_suppression_once_without_losing_facts():
    package = employment_package()
    src, _raw = employment_source()
    reply = employment_proposal(src, unsupported=True)
    task_field = next(field for field in reply['fields'] if field['item']['key'] == 'tasks-entry')
    result_field = next(field for field in reply['fields'] if field['item']['key'] == 'results-entry')
    task_field['evidence'] = [*result_field['evidence'], *task_field['evidence']]
    operation, facts, proposal, _package, _src = proposed_from(package, src, reply)
    rejected = next(value for value in operation.allocations if value.key == 'results-entry')
    operation, facts = accept(operation, facts, proposal, package, src, [rejected.cell_ids['value']])
    fallback(operation, [type(proposal.resolved_fields[0].evidence[0]).model_validate(value)
        for value in result_field['evidence']])
    before = canonical(facts)
    document, coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    rendered = text(document)
    assert rendered.count('Implemented queue processing.') == 1
    assert rendered.count('Our team reduced median latency from 800 ms to 500 ms.') == 1
    assert '80%' not in rendered and 'Tasks:' not in rendered and 'Results:' not in rendered
    assert 'Example Labs' in rendered and canonical(facts) == before
    spans = [value for value in coverage if value.disposition == 'fallback']
    assert len(spans) == 2 and len({value.block_ids[0] for value in spans}) == 2
    blocks = {block.id: block for block in document.blocks()}
    assert all(blocks[value.block_ids[0]].presentation.style_token == 'body' for value in spans)
    assert all(blocks[value.block_ids[0]].content[0].citations == [value.span] for value in spans)


@pytest.mark.parametrize('owner', ['original', 'moved', 'missing'])
def test_captured_nested_human_claim_without_sidecar_stays_with_current_owner_as_plain_text(owner):
    from packages.resume_core.template_capture import prepare_builtin_identities
    from packages.resume_core.template_facts import move_owned
    from packages.resume_core.template_import import start_operation
    from tests.templates.pipeline_fixtures import NOW, setup_operation
    from tests.templates.test_existing_capture import serial
    from tests.templates.test_relations import facts as related_facts
    facts = related_facts()
    facts.extensions, facts.relations, facts.observations = [], [], []
    if owner == 'moved':
        facts = move_owned(facts, 'claim', 'employer-b', supported_owner_ids=['employer-a', 'employer-b'])
    elif owner == 'missing':
        next(record for record in facts.records if record.id == 'claim').job_id = None
    package = employment_package()
    facts = prepare_builtin_identities(facts, package, [], id_factory=serial())
    src, _raw = employment_source()
    _empty, command, _package, _source, _facts = setup_operation(captured=package, src=src)
    command.capture.fact_revisions = {record.id: record.revision for record in facts.records}
    operation, _created = start_operation('human-project', command, package, [src], facts, [], NOW)
    operation.tasks[0].allowed_handles = [identity.item_handle for identity in operation.captured_items]
    before = canonical(facts)
    if owner == 'missing':
        with pytest.raises(ValueError, match='reachable configured owner'):
            materialize(package, facts, [operation], [src], operation_id=operation.id)
        assert canonical(facts) == before
        return
    document, _coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    rendered = text(document)
    assert rendered.count('Maintained a queue') == 1 and canonical(facts) == before
    assert 'Tasks:' not in rendered and 'Results:' not in rendered
    section = next(block for block in document.blocks() if block.type == 'section' and
        any('Maintained a queue' in ''.join(part.text for part in child.content) for child in block.children))
    assert section.props.record_id == ('employer-b' if owner == 'moved' else 'employer-a')
    part = next(part for child in section.children for part in child.content
        if isinstance(part, FieldOccurrence) and part.record_id == 'claim')
    identity = next(value for value in operation.captured_items if value.record_id == 'claim')
    assert part.cell_id == identity.cell_ids['value'] and part.presentation.item_handle == identity.item_handle
    assert part.presentation.node_index is None and part.presentation.style_token == 'body'
    assert not operation.attempts and not operation.receipts


@pytest.mark.parametrize('explicit_style', [False, True])
def test_source_fallback_with_no_nodes_needs_an_explicit_captured_style(explicit_style, monkeypatch):
    import json
    from packages.resume_core.templates import compiler
    from packages.resume_core.templates.compiler import compile_bytes
    from packages.resume_core.templates.store import BUNDLED_TEMPLATE
    from tests.templates.pipeline_fixtures import setup_operation
    config = employment_package().definition.model_dump(mode='json', by_alias=True)
    config['blocks'][0]['view']['nodes'] = []
    if not explicit_style:
        config['blocks'][0]['view'].pop('fallback_style')
        # New packages refuse this view; one already stored still reaches the materializer.
        monkeypatch.setattr(compiler, 'check_runs', lambda _definition: None)
    package = compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')
    src, _raw = employment_source()
    operation, _command, _package, _source, facts = setup_operation(captured=package, src=src)
    fallback(operation, [capture_span(src, src.units[0])])
    if not explicit_style:
        with pytest.raises(ValueError, match='no configured text style'):
            materialize(package, facts, [operation], [src], operation_id=operation.id)
        return
    document, _coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    assert text(document) == 'PROJECTS\n' + src.units[0].text.rstrip('\n')
    assert document.blocks()[-1].presentation.style_token == 'body'


def test_captured_human_classification_is_retained_in_facts_without_becoming_cv_text():
    from packages.resume_core.template_capture import schema_hash
    from packages.resume_core.template_import import start_operation
    from tests.templates.pipeline_fixtures import NOW, setup_operation
    operation, facts, package, src, _raw = admitted()
    for record in facts.extensions:
        for cell in record.cells:
            cell.origin, cell.user_corrected, cell.state = 'human', True, 'human_raw'
            cell.raw_input, cell.typed_value = 'PRIVATE CLASSIFICATION', None
        declaration = next(value for value in package.definition.fact_types if value.id == record.semantic_type)
        assert record.semantic_schema_hash == schema_hash(declaration, package)
    _empty, command, _package, _source, _facts = setup_operation(captured=package, src=src)
    command.capture.fact_revisions = {record.id: record.revision for record in [*facts.records, *facts.extensions]}
    captured, _created = start_operation('human-project', command, package, [src], facts, [], NOW)
    captured.tasks[0].allowed_handles = [identity.item_handle for identity in captured.captured_items]
    before = canonical(facts)
    document, _coverage = materialize(package, facts, [operation, captured], [src], operation_id=captured.id)
    assert 'PRIVATE CLASSIFICATION' not in text(document) and canonical(facts) == before


def test_hidden_human_classification_does_not_prevent_visible_claim_source_fallback():
    from packages.resume_core.template_facts import human_edit
    operation, facts, package, src, _raw = admitted(payload_edit=lambda value:
        value[0]['results'][0].update(value='Rewritten team result'))
    result = next(value for value in operation.allocations if value.key == 'results-entry')
    classification = next(value for value in operation.allocations if value.key == 'results-entry-classification')
    facts = human_edit(facts, classification.record_id, 'category', 'private category')
    evidence = next(field.evidence for proposal in operation.proposals for field in proposal.resolved_fields
        if field.item_handle == result.item_handle)
    fallback(operation, evidence)
    before = canonical(facts)
    document, coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    rendered = text(document)
    assert 'Rewritten team result' not in rendered and 'private category' not in rendered
    assert rendered.count('Our team reduced median latency from 800 ms to 500 ms.') == 1
    assert rendered.count('Implemented queue processing.') == 1
    assert canonical(facts) == before
    assert len([span for span in coverage if span.disposition == 'fallback']) == 1


def test_disabled_rewriting_materializes_exact_source_raw_text_with_same_cell_identity():
    edit = lambda payload: payload[0]['tasks'][0].update(value='Built asynchronous queue processing.')
    operation, facts, package, src, _raw = admitted(rewrite=False, payload_edit=edit)
    document, _coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    assert 'Built asynchronous' not in text(document)
    assert text(document).count('Implemented queue processing.') == 1
    cell = next(value.cell_ids['value'] for value in operation.allocations if value.key == 'tasks-entry')
    assert any(isinstance(part, FieldOccurrence) and part.cell_id == cell for block in document.blocks() for part in block.content)


def test_actual_project_assembly_retains_captured_assets_facts_and_exact_presentation_snapshot():
    operation, facts, package, src, _raw = admitted()
    before = source_draft(operation, facts, captured=package, src=src)
    assembled = assemble_template(before, operation)
    assert assembled.pre_draft is None and before.project is None
    assert assembled.project.template_package == package and assembled.project.facts == facts
    assert assembled.project.sources == [src]
    snapshot = snapshot_identity(assembled)
    presented = project_presentation(assembled)
    assert presented['snapshot'] == snapshot.model_dump(by_alias=True)
    assert presented['recipe'] == package.recipe.model_dump(by_alias=True)
    assert set(presented['blocks']) == {block.id for block in assembled.project.document.blocks()}
    broken = assembled.model_dump(by_alias=True)
    block = next(block for block in broken['project']['document']['regions'][2]['blocks'] if block['type'] == 'section')['children'][0]
    block['presentation']['nodeIndex'] = 999
    with pytest.raises(ValueError, match='node is outside'):
        type(assembled).model_validate(broken)


def issue_workspace():
    from tests.templates.test_transactions import issue
    operation, facts, package, src, raw = admitted(unsupported=True)
    bad = next(value for value in operation.allocations if value.key == 'results-entry')
    job = next(value for value in operation.allocations if value.key == 'job')
    operation.issues = [issue('metric-warning', bad.cell_ids['value']), issue('role-warning', job.cell_ids['role'])]
    for finding in operation.issues:
        finding.task_id = operation.tasks[0].id
    assembled = assemble_template(source_draft(operation, facts, captured=package, src=src), operation)
    return assembled, {src.id: raw}


def fallback_edit(before):
    from tests.templates.test_transactions import request
    finding = before.project.import_issues[0]
    block = next(block for block in before.project.document.blocks() if block.id in finding.block_ids)
    return request(before, [
        {'kind': 'replace_inline_range', 'blockId': block.id, 'beforeRevision': block.revision,
            'cellId': None, 'field': 'content', 'start': 0, 'end': len(block.content[0].text.encode('utf-16-le')) // 2,
            'content': [{'type': 'text', 'text': 'Exact human correction', 'styles': {}}]},
        {'kind': 'set_issue_state', 'issueId': finding.id, 'beforeLifecycleId': finding.lifecycle_id,
            'beforeState': 'active', 'afterLifecycleId': 'human-retired', 'afterState': 'retired',
            'actionId': 'human-edit', 'importedFingerprint': finding.imported_fingerprint}])


def test_materialized_fallback_issue_edit_undo_redo_is_scoped_without_new_checks(monkeypatch):
    from packages.resume_core.rich_mutations import apply_rich_mutation
    from packages.resume_core.template_inverse import inverse_template_mutation
    from tests.templates.test_transactions import authorization
    before, _sources = issue_workspace()
    assert all(finding.block_ids for finding in before.project.import_issues)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('manual fallback editing must not evaluate template assertions')
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload', forbidden)
    changed, _ = apply_rich_mutation(before, fallback_edit(before))
    assert [finding.state for finding in changed.project.import_issues] == ['retired', 'active']
    assert changed.project.facts == before.project.facts
    inverse = inverse_template_mutation(before, changed, origin_action_id='human-edit',
        mutation_id='undo', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(changed, inverse, history_authorization=authorization(changed, inverse))
    assert [finding.state for finding in restored.project.import_issues] == ['active', 'active']
    assert 'Exact human correction' not in text(restored.project.document)
    redo = inverse_template_mutation(changed, restored, origin_action_id='human-edit',
        mutation_id='redo', session_id='session', action_token=3, kind='redo')
    replayed, _ = apply_rich_mutation(restored, redo, history_authorization=authorization(restored, redo))
    assert [finding.state for finding in replayed.project.import_issues] == ['retired', 'active']
    assert 'Exact human correction' in text(replayed.project.document)


def test_failed_save_of_materialized_issue_edit_keeps_coherent_disk_and_retry_transfer(tmp_path, monkeypatch):
    from packages.resume_core import project_repository as module
    from packages.resume_core.archive_zip import write_zip
    from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
    from tests.templates.editor_fixtures import TemplateEditor
    before, sources = issue_workspace()
    editor = TemplateEditor(tmp_path, before, sources)
    path = editor.session().directory / 'workspace.json'
    previous = path.read_bytes()
    command = fallback_edit(before)
    write = module.atomic_write
    def fail(target, data, **kwargs):
        if target.name == 'workspace.json':
            raise OSError('synthetic disk failure')
        return write(target, data, **kwargs)
    monkeypatch.setattr(module, 'atomic_write', fail)
    with pytest.raises(module.RepositoryFailure, match='PROJECT_SAVE_FAILED'):
        editor.commit(command)
    assert path.read_bytes() == previous
    prior = module.decode_project(path.parent, previous)
    assert prior.project.document == before.project.document and prior.project.facts == before.project.facts
    assert prior.project.import_issues[0].state == 'active'
    monkeypatch.setattr(module, 'atomic_write', write)
    assert not editor.commit(command).replayed
    candidate = editor.current()
    assert [finding.state for finding in candidate.project.import_issues] == ['retired', 'active']
    reopened = editor.reopen()
    assert reopened == candidate
    transferred, _originals, _, _ = open_archive_v7(write_zip(archive_payload_v7(reopened, sources, {})), 'employment-copy')
    assert transferred.project.document == reopened.project.document
    assert transferred.project.facts == reopened.project.facts
    assert [finding.state for finding in transferred.project.import_issues] == ['retired', 'active']


@pytest.mark.parametrize('state', ['human_raw', 'pending_manual'])
def test_captured_human_fields_survive_source_fallback_without_resurrecting_old_wording(state):
    from packages.resume_core.template_import import start_operation
    from tests.templates.pipeline_fixtures import NOW, setup_operation
    from tests.templates.human_authority_fixtures import HUMAN_TEXT, human_papers
    _empty, command, package, src, _facts = setup_operation()
    facts = human_papers(state)
    command.capture.fact_revisions = {record.id: record.revision for record in facts.extensions}
    operation, _created = start_operation('human-project', command, package, [src], facts, [], NOW)
    operation.tasks[0].allowed_handles = [record.item_handle for record in facts.extensions]
    fallback(operation, [capture_span(src, src.units[0])])
    document, coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    assert text(document).count(HUMAN_TEXT) == 1
    assert src.units[0].text not in text(document)
    assert not any(value.disposition == 'fallback' for value in coverage)


def test_a_fallback_suppresses_a_shared_cell_only_in_its_own_view():
    # K02: a cell two views show is replaced by one view's source copy there and stays in the other view.
    from types import SimpleNamespace
    from packages.resume_core.templates.span_coverage import fallback_plan
    src, _raw = employment_source()
    unit = src.units[0]
    def phrase(value):
        start = unit.text.index(value)
        return capture_span(src, unit, start, start + len(value))
    shared = SimpleNamespace(id='cell-shared', origin='model', evidence=[phrase('Python')])
    other = SimpleNamespace(id='cell-other', origin='model', evidence=[phrase('Example Labs')])
    _spans, suppressed, placements = fallback_plan([src], {'tasks': [phrase('Python')]},
        {'tasks': [shared], 'skills': [shared, other]})
    assert suppressed == {('tasks', 'cell-shared')} and set(placements) == {'tasks'}
    assert [source_slice([src], span) for span in placements['tasks']] == ['Python']


def test_lines_a_review_names_as_missing_show_only_where_no_view_shows_them():
    # LIVE-09: a coverage gap repeated lines another block already showed; such lines now place only once, nowhere
    # twice, while the accepted values stay.
    from packages.resume_core.template_identity import line_spans
    from packages.resume_core.template_import import digest
    from packages.resume_core.templates.span_coverage import overlaps
    operation, facts, package, src, _raw = admitted()
    _document, before = materialize(package, facts, [operation], [src], operation_id=operation.id)
    lines = [line for line in line_spans(src, src.units[0]) if source_slice([src], line).strip()]
    # A line counts as shown when an accepted value cites it, whatever wording the view gives it.
    unshown = [line for line in lines if not any(value.disposition in {'accepted', 'multiple_views'}
        and overlaps(value.span, line) for value in before)]
    assert unshown and len(unshown) < len(lines)
    fallback(operation, lines)
    operation.task_results[0].value = {'scope': 'cited', 'leftoverOnly': [digest(line) for line in lines]}
    document, coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    placed = [block for block in document.blocks() if block.type == 'paragraph' and block.content[0].citations]
    # Adjacent missing lines stay one paragraph.
    assert '\n'.join(source_slice([src], block.content[0].citations[0]).strip() for block in placed) == '\n'.join(
        source_slice([src], line).strip() for line in unshown)
    # Nothing is lost: every line is shown by an accepted value or placed once.
    assert all(any(value.disposition in {'accepted', 'multiple_views', 'fallback'} and overlaps(value.span, line)
        for value in coverage) for line in lines)


def test_a_source_fallback_of_an_operation_task_places_no_text():
    # finish_fallbacks gives every unfinished task a fallback, operations included; only blocks have views.
    from tests.templates.generic_fixtures import generic_package
    from tests.templates.pipeline_fixtures import setup_operation
    package = generic_package()
    src, _raw = employment_source()
    operation, _command, _package, _source, facts = setup_operation(captured=package, src=src)
    task = next(value for value in operation.tasks if value.block_id == 'project-window')
    operation.task_results = [TaskResultRecord(id='operation-fallback', taskId=task.id, inputHash=task.input_hash,
        value=None, sourceSpans=[capture_span(src, src.units[0])], itemHandles=[], issueIds=[], disposition='source_fallback')]
    document, _coverage = materialize(package, facts, [operation], [src], operation_id=operation.id)
    assert src.units[0].text.strip() not in text(document)
    task.block_id = 'nowhere'
    with pytest.raises(ValueError, match='no configured block view'):
        materialize(package, facts, [operation], [src], operation_id=operation.id)
