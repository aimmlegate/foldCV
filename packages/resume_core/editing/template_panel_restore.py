"""«Вернуть на страницу» in Facts (F7, D179): a job, education or language card off the page, or a field line of a card
that stays, comes back where the template puts it.

A card is built again from the facts as the import builds it (the materializer), so a value edited in Facts while the
card was off the page comes back edited; the user's own text inside the card and their order of its lines do not. The
card goes after the nearest earlier card of its view that the page shows, in the order the import gives, else before
the nearest later one, else after the view's title, else where the import puts the view (with its title)."""

from ..fields import inline_groups
from ..models.rich_document import FactFieldSpan
from ..models.template_document import BoundLink, TemplateSectionBlock
from ..templates.captured_fields import ownership_parents
from ..templates.materialize import materialize
from .off_page import RESTORABLE, named_records, off_fields, off_page
from .panel_views import restore_view, view_title
from .template_panel_lines import _add_period_line, field_place, period_words, show_fields, sibling_lists

# The ids a rebuilt card brings, by the allocator prefix of each kind: the card gets new ones.
ID_KEYS = {'id': 'block', 'templateInstanceId': 'template-instance', 'occurrenceId': 'occurrence',
    'bindingRootId': 'occurrence', 'bindingId': 'fragment', 'fragmentId': 'fragment'}


def rebuilt_document(project, operations, as_of=None):
    """The document the import's template builds from the present facts and the import's records."""
    document, _coverage = materialize(project.template_package, project.facts, operations, project.sources,
        operation_id='restore', revision=1, as_of=as_of)
    return document


def _card(document, record_id):
    """(sibling list, section) of the record's own card in a document, or None."""
    for items in sibling_lists(document):
        for block in items:
            if isinstance(block, TemplateSectionBlock) and block.props.record_id == record_id and block.presentation is not None:
                return items, block
    return None


def restorable(project):
    """The off-page records of the restorable kinds: their rows offer «Вернуть на страницу»."""
    from .template_panel_hide import kept_records
    kinds = {record.id: record.kind for record in project.facts.records}
    # A record a hidden block or card holds comes back with its block's Show (D185).
    return {identifier for identifier in off_page(project) - kept_records(project) if kinds.get(identifier) in RESTORABLE}


def _owned(project, record_id):
    """The record and every record whose owner chain reaches it (its claims, technologies, project lines)."""
    parents = ownership_parents(project.facts)
    found, changed = {record_id}, True
    while changed:
        changed = False
        for child, owners in parents.items():
            if child not in found and owners & found:
                found.add(child)
                changed = True
    return found


def _names(block):
    """The records a block's own text names."""
    found = set()
    for _container, content in inline_groups(block):
        for span in content:
            if isinstance(span, FactFieldSpan):
                found.add(span.record_id)
            elif isinstance(span, BoundLink):
                found.update(value.record_id for value in (span.label_binding, span.url_binding) if value is not None)
    return found


def _without_shown(project, section, record_id):
    """The card without the lines of its facts that the page shows elsewhere, as a bullet the user moved to another
    card: a fact is not placed twice. A technology may stand in several lists, as the import puts it."""
    kinds = {record.id: getattr(record, 'kind', None) for record in project.facts.records}
    shown = named_records(project.document) & (_owned(project, record_id) - {record_id})
    shown = {identifier for identifier in shown if kinds.get(identifier) != 'technology'}

    def keep(items):
        kept = []
        for block in items:
            named = _names(block)
            if named and named <= shown:
                continue
            block.children = keep(block.children)
            kept.append(block)
        return kept
    section.children = keep(section.children)
    return section


def _new_ids(section, allocator):
    """The card with new ids: the rebuilt card has the ids of the import's card, which history may still hold."""
    mapping = {}

    def visit(value, key=None):
        if isinstance(value, dict):
            return {name: visit(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [visit(item) for item in value]
        if key in ID_KEYS and isinstance(value, str) and value.startswith('template-'):
            if value not in mapping:
                mapping[value] = allocator.allocate(ID_KEYS[key], ['panel-restore', value])
            return mapping[value]
        return value
    return type(section).model_validate(visit(section.model_dump(mode='json', by_alias=True)))


def _place(candidate, package, rebuilt, items, section, allocator, kind):
    """Insert the card in the candidate's document by the order rule above."""
    view = section.presentation.view_key
    peers = [block for block in items if isinstance(block, TemplateSectionBlock) and block.props.record_id is not None
        and block.presentation is not None and block.presentation.view_key == view]
    at = [block.id for block in peers].index(rebuilt.id)
    shown = {}
    for page_items in sibling_lists(candidate.document):
        for block in page_items:
            if isinstance(block, TemplateSectionBlock) and block.props.record_id is not None and block.presentation is not None \
                    and block.presentation.view_key == view:
                shown.setdefault(block.props.record_id, (page_items, block))
    for earlier in reversed(peers[:at]):
        if earlier.props.record_id in shown:
            page_items, block = shown[earlier.props.record_id]
            page_items.insert(page_items.index(block) + 1, section)
            return
    for later in peers[at + 1:]:
        if later.props.record_id in shown:
            page_items, block = shown[later.props.record_id]
            page_items.insert(page_items.index(block), section)
            return
    for page_items in sibling_lists(candidate.document):
        title = next((block for block in page_items if view_title(block, view)), None)
        if title is not None:
            page_items.insert(page_items.index(title) + 1, section)
            return
    declaration = next(value for value in package.definition.blocks if value.id == view)
    if not restore_view(candidate.document, package, declaration, [section], allocator, kind):
        raise ValueError('PANEL_ACTION_UNSUPPORTED')


def restore(workspace, command, allocator, operations=None):
    """(candidate project, steps) of «Вернуть на страницу»; the steps are the document's only. `operations`: the import
    records, when the workspace does not hold them."""
    project = workspace.project
    record = next((value for value in project.facts.records if value.id == command.record_id), None)
    if record is None or record.kind not in RESTORABLE or command.job_id is not None or command.period_id is not None:
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    field = command.values.get('field')
    candidate = project.model_copy(deep=True)
    if field is None:
        if record.id not in off_page(project):
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        document = rebuilt_document(project, operations if operations is not None else project.template_operations,
            workspace.formatting_as_of)
        found = _card(document, record.id)
        if found is None:
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        items, rebuilt = found
        section = _new_ids(_without_shown(project, rebuilt.model_copy(deep=True), record.id), allocator)
        _place(candidate, project.template_package, rebuilt, items, section, allocator, record.kind)
        return candidate, []
    if field not in off_fields(project).get(record.id, []):
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    updated = next(value for value in candidate.facts.records if value.id == record.id)
    if field.startswith('period:'):
        identifier = field.removeprefix('period:').rpartition(':')[0]
        period = next(value for value in updated.periods if value.id == identifier)
        _add_period_line(candidate, updated, period, period_words(project.template_package), allocator)
    elif not _whole_line(candidate, project, updated, field, operations, workspace.formatting_as_of, allocator):
        show_fields(candidate, updated, {field}, allocator)
    return candidate, []


def _whole_line(candidate, project, record, field, operations, as_of, allocator):
    """A node's line that left the card whole comes back whole from the rebuilt card, with the other values it shows (a
    role with its scope) and its label; False when the card still has a line of the node, which the field joins."""
    found = field_place(candidate, record, field)
    if found is None:
        return False
    section, _view, index, _node, _parts = found
    if any(child.presentation is not None and child.presentation.node_index == index for child in section.children):
        return False
    rebuilt = _card(rebuilt_document(project, operations if operations is not None else project.template_operations, as_of),
        record.id)
    if rebuilt is None or section.presentation is None:
        return False
    lines = [child for child in rebuilt[1].children if child.presentation is not None and child.presentation.node_index == index]
    if not lines:
        return False
    instance, handle = section.presentation.template_instance_id, section.presentation.item_handle
    shown = named_records(candidate.document)
    lines = [line for line in lines if not (_names(line) - {record.id}) & shown]
    if not lines:
        return False
    # The allocator names each old id's slot, so ids two lines share stay shared.
    lines = [_new_ids(line, allocator) for line in lines]
    # The card keeps its instance: the line's presentation names it, as an import line of this card does.
    for line in lines:
        if line.presentation is not None:
            line.presentation = line.presentation.model_copy(update={'template_instance_id': instance, 'item_handle': handle})
    at = next((len(section.children) - position for position, child in enumerate(reversed(section.children))
        if child.presentation is not None and child.presentation.node_index is not None
        and child.presentation.node_index <= index), 0)
    section.children[at:at] = lines
    return True
