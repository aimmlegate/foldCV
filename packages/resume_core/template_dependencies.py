"""Resolve template-only state through explicit shared dependency selectors."""

import json

from .templates.compiler import canonical


def selector(kind, identifier):
    return canonical(['template', kind, identifier]).decode()


def target(workspace, kind, identifier):
    if workspace.schema_version != 7 or workspace.project is None:
        return None
    project = workspace.project
    collections = {'relation': project.facts.relations, 'issue': project.import_issues,
        'manual_scope': project.facts.manual_scopes, 'sync': workspace.sync_records}
    if kind in collections:
        return next((value for value in collections[kind] if value.id == identifier), None)
    if kind == 'sync_placement':
        previous = None
        for row in workspace.sync_records:
            if row.id == identifier:
                return {'afterSyncId': previous}
            previous = row.id
        return None
    if kind == 'builtin_scope':
        return {'cellId': identifier, 'scopeId': project.facts.builtin_manual_scopes.get(identifier)}
    if kind == 'coverage_anchor':
        from .template_anchors import coverage_at
        return coverage_at(project, identifier)
    if kind == 'scope_occurrence':
        from .template_scope_occurrences import scope_dependency
        try:
            pair = json.loads(identifier)
        except ValueError:
            return None
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(value, str) for value in pair):
            return None
        return scope_dependency(project, *pair)
    return None


def step_targets(workspace, step):
    if step.kind in {'put_template_sync', 'remove_template_sync'}:
        identifier = step.record.id if step.kind == 'put_template_sync' else step.sync_id
        result = {('field', selector('sync', identifier))}
        if step.kind == 'put_template_sync' and step.before_hash is not None and step.history_placement is None:
            return result
        result.add(('field', selector('sync_placement', identifier)))
        rows = workspace.sync_records
        if step.kind == 'remove_template_sync' or step.history_placement is not None:
            index = next((index + 1 for index, value in enumerate(rows) if value.id == identifier), None)
            if index is not None and index < len(rows):
                result.add(('field', selector('sync_placement', rows[index].id)))
        if step.kind == 'put_template_sync':
            previous = (step.history_placement.after_sync_id if step.history_placement is not None
                else step.placement.after_sync_id)
            index = 0 if previous is None else next((index + 1 for index, value in enumerate(rows) if value.id == previous), None)
        if index is not None and index < len(rows):
            result.add(('field', selector('sync_placement', rows[index].id)))
        return result
    if step.kind in {'put_extension', 'remove_extension'}:
        return {('record', step.record.id if step.kind == 'put_extension' else step.record_id)}
    if step.kind in {'put_relation', 'remove_relation'}:
        relation = step.relation if step.kind == 'put_relation' else next(
            (value for value in workspace.project.facts.relations if value.id == step.relation_id), None)
        identifier = step.relation.id if step.kind == 'put_relation' else step.relation_id
        return {('field', selector('relation', identifier)), *([('record', relation.subject_id)] if relation else [])}
    if step.kind == 'put_manual_scope':
        return {('field', selector('manual_scope', step.scope.id))}
    if step.kind == 'set_builtin_manual_scope':
        return {('field', selector('builtin_scope', step.cell_id)), ('field', step.cell_id)}
    if step.kind == 'set_issue_state':
        return {('field', selector('issue', step.issue_id))}
    if step.kind == 'set_authored_anchors':
        target = step.target
        if target.kind == 'issue':
            return {('field', selector('issue', target.issue_id))}
        address = canonical([target.coverage_index, target.coverage_identity_hash, target.coverage_sequence_hash]).decode()
        return {('field', selector('coverage_anchor', address))}
    if step.kind == 'set_manual_scope_displays':
        result = {('block', value.address.block_id) for value in step.assignments}
        for source in step.sources:
            result.add(('field', selector('manual_scope', source.scope_id)))
            result.add(('field', selector('scope_occurrence', canonical([source.scope_id, source.occurrence_id]).decode())))
            result.update(('field', cell) for cell in source.active_cell_ids)
            result.update(('block', fragment.block_id) for fragment in source.fragments)
        for value in step.assignments:
            if value.after.kind == 'manual_scope':
                result.add(('field', selector('manual_scope', value.after.scope_id)))
        return result
    return None
