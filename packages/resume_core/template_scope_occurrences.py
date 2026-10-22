"""Address shared human text by current cell references and authored fragments."""

from dataclasses import dataclass, field

from .models.template_document import ManualScopeSpan
from .rich_fields import inline_groups


def active_scope_cells(facts):
    result = {}
    for record in facts.extensions:
        if record.active:
            for cell in record.cells:
                if cell.state == 'pending_manual' and cell.manual_scope_id is not None:
                    result.setdefault(cell.manual_scope_id, set()).add(cell.id)
    for cell, scope in facts.builtin_manual_scopes.items():
        result.setdefault(scope, set()).add(cell)
    return result


@dataclass
class ScopeOccurrence:
    scope_id: str
    occurrence_id: str
    spans: list[ManualScopeSpan] = field(default_factory=list)
    block_ids: list[str] = field(default_factory=list)

    @property
    def text(self):
        return ''.join(span.text for span in self.spans)


def scope_occurrences(document):
    result = {}
    for block in document.blocks():
        for _container, content in inline_groups(block):
            for span in content:
                if isinstance(span, ManualScopeSpan):
                    key = (span.scope_id, span.occurrence_id)
                    group = result.setdefault(key, ScopeOccurrence(*key))
                    group.spans.append(span)
                    if block.id not in group.block_ids:
                        group.block_ids.append(block.id)
    return result


def validate_scope_occurrences(project):
    scopes = {scope.id: scope for scope in project.facts.manual_scopes}
    active = active_scope_cells(project.facts)
    for group in scope_occurrences(project.document).values():
        scope = scopes.get(group.scope_id)
        if (scope is None or not active.get(group.scope_id) or group.text != scope.raw_input
                or scope.raw_input == '' and len(group.spans) != 1):
            raise ValueError('manual scope occurrence has missing authority or differs from exact raw input')


def scope_dependency(project, scope_id, occurrence_id):
    group = scope_occurrences(project.document).get((scope_id, occurrence_id))
    scope = next((value for value in project.facts.manual_scopes if value.id == scope_id), None)
    if group is None or scope is None:
        return None
    return {'scope': scope.model_dump(mode='json', by_alias=True),
        'activeCellIds': sorted(active_scope_cells(project.facts).get(scope_id, set())),
        'blockIds': group.block_ids, 'fragments': [span.model_dump(mode='json', by_alias=True) for span in group.spans]}
