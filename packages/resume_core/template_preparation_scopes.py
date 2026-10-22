"""Prepare new shared authority while preserving all untouched display wording."""

from .models.template_document import ManualScopeSpan
from .rich_fields import inline_groups
from .rich_mutations import locate
from .template_authoring import citation_spans
from .template_preparation_cells import human_cell_steps
from .template_ranges import FlankRecorder
from .template_scope_displays import capture_source, inline_addresses, node_hash
from .template_scope_occurrences import active_scope_cells, scope_occurrences


def scope_edit_steps(workspace, operation, allocator, content, fields, scope_ranges, bound, action_id, *, replacement=None):
    from .template_preparation import _identity, _leaves, _rewrite
    selected, project = operation.range, workspace.project
    pairs = {(span.scope_id, span.occurrence_id) for span, _start, _end in scope_ranges}
    scope_ids = {key[0] for key in pairs}
    covered = sum(min(end, selected.end) - max(start, selected.start) for _span, start, end in scope_ranges)
    direct = len(pairs) == 1 and not fields and (selected.start == selected.end
        and isinstance(bound, ManualScopeSpan) or covered == selected.end - selected.start)
    active = active_scope_cells(project.facts)
    cells = {_identity(span)[0] for span in fields}
    for scope in scope_ids:
        if not active.get(scope):
            raise ValueError('shared input no longer has its captured active cells')
        cells.update(active[scope])
    citations, reference = [], None
    for span, start, end in _leaves(content):
        if not (start < selected.end and end > selected.start or start == end and selected.start <= start < selected.end
                or selected.start == selected.end and span is bound):
            continue
        reference = reference or getattr(span, 'presentation', None)
        evidence = citation_spans(project, span) if hasattr(span, 'record_id') or isinstance(span, ManualScopeSpan) else getattr(span, 'citations', [])
        for citation in evidence:
            if citation not in citations:
                citations.append(citation.model_copy(deep=True))
    for span in fields:
        for citation in citation_spans(project, span):
            if citation not in citations:
                citations.append(citation.model_copy(deep=True))
    original_groups = scope_occurrences(project.document)
    sources = [capture_source(project, *key).model_dump(by_alias=True)
        for key in original_groups if key[0] in scope_ids]
    candidate = project.model_copy(deep=True)
    found = locate(candidate.document, selected.block_id); block = found[0][found[1]]
    target = dict(inline_groups(block))[selected.cell_id or selected.field]
    if direct:
        seed = scope_ranges[0][0].model_copy(update={'citations':citations},deep=True)
        fact_steps = None
    else:
        fact_steps = human_cell_steps(workspace, sorted(cells), operation.text, action_id,
            [selected.block_id], allocator, ambiguous=True)
        scope = fact_steps[0]['scope']['id']
        root = allocator.allocate('manual-occurrence', ['replacement-scope-occurrence', scope])
        seed = ManualScopeSpan(type='manual_scope',scopeId=scope,occurrenceId=root,fragmentId=root,
            text=operation.text,styles=operation.styles,presentation=reference,citations=citations)
    flanks = FlankRecorder(allocator)
    changed, inserted = _rewrite(content, selected, operation, allocator, seed, flanks, replacement=replacement)
    target[:] = changed
    edited_pair = next(iter(pairs)) if direct else None
    if direct:
        group = scope_occurrences(candidate.document)[edited_pair]
        raw = group.text
        fact_steps = human_cell_steps(workspace, sorted(cells), raw, action_id,
            group.block_ids, allocator, ambiguous=True)
        scope = fact_steps[0]['scope']['id']
    else:
        raw = operation.text
    assignments = []
    anchor = inserted[0].fragment_id
    for address, _owner, _parts, span in inline_addresses(candidate.document):
        if not isinstance(span, ManualScopeSpan) or span.scope_id not in scope_ids:
            continue
        keep = direct and (span.scope_id, span.occurrence_id) == edited_pair and (raw != '' or span.fragment_id == anchor)
        after = {'kind':'manual_scope','scopeId':scope,'occurrenceId':span.occurrence_id,'fragmentId':span.fragment_id} if keep else {'kind':'literal'}
        assignments.append({'address':dict(zip(['blockId','cellId','field','inlineIndex'],address)),
            'beforeHash':node_hash(span),'after':after})
    steps = [{'kind':'replace_inline_range','blockId':selected.block_id,'cellId':selected.cell_id,'field':selected.field,
        'start':selected.start,'end':selected.end,'beforeRevision':selected.before_revision,
        'content':[span.model_dump(by_alias=True) for span in inserted],'flankBindings':flanks.entries},*fact_steps]
    if sources or assignments:
        steps.append({'kind':'set_manual_scope_displays','sources':sources,'assignments':assignments})
    return steps,candidate


def detach_unowned_displays(before, candidate):
    active = active_scope_cells(candidate.facts)
    orphaned = {span.scope_id for _address, _block, _content, span in inline_addresses(candidate.document)
        if isinstance(span, ManualScopeSpan) and not active.get(span.scope_id)}
    if not orphaned:
        return None
    sources = [capture_source(before, *key).model_dump(by_alias=True)
        for key in scope_occurrences(before.document) if key[0] in orphaned]
    assignments = [{'address':dict(zip(['blockId','cellId','field','inlineIndex'],address)),
        'beforeHash':node_hash(span),'after':{'kind':'literal'}}
        for address, _block, _content, span in inline_addresses(candidate.document)
        if isinstance(span, ManualScopeSpan) and span.scope_id in orphaned]
    return {'kind':'set_manual_scope_displays','sources':sources,'assignments':assignments}
