"""«Скрыть» in Facts (D185): a job's card or a whole template block off the page and back.

Hide moves the exact blocks from the document into the project's hidden store (`hiddenBlocks`), with their ids; Show
puts the same blocks back. The document stays the page, so export, the page count, the original's red marks, the job
order of D182, reword and the assistant see a hidden block as absent, as a deleted one. A card or block the user
deleted on the page is in the same state; its Show builds it again from the facts (D179)."""

from ..fields import inline_groups, records_by_id, working_field
from ..models.rich_document import FactFieldSpan
from ..models.template_document import BoundLink, FieldOccurrence, TemplateSectionBlock
from ..models.template_mutations import HiddenAnchor, HiddenBlocks, HiddenGroup, HiddenTarget
from ..template_anchors import coverage_identity, coverage_target, issue_target
from ..hashing import canonical, sha256
from ..templates.captured_fields import visible_binding
from ..templates.materialize_nodes import locale_text
from .mutations import parent_items

VIEW = 'view:'
# The Facts groups whose rows a block shows; a group that shows one block carries its eye at the group's header.
ROW_KINDS = ('employment', 'education', 'language')


def _tops(document, match):
    """(parent id, sibling list, block) of each top-most block that matches, in document order."""
    found = []

    def visit(parent, items):
        for block in items:
            if match(block):
                found.append((parent, items, block))
            else:
                visit(block.id, block.children)
    for region in document.regions:
        visit(region.id, region.blocks)
    return found


def _subtree(block):
    yield block
    for child in block.children:
        yield from _subtree(child)


def _of_view(view):
    return lambda block: block.presentation is not None and block.presentation.view_key == view


def _card_of(record_id):
    return lambda block: (isinstance(block, TemplateSectionBlock) and block.props.record_id == record_id
                          and block.presentation is not None)


def _entry(project, kind, identifier):
    return next((entry for entry in project.hidden_blocks if entry.target.kind == kind and entry.target.id == identifier), None)


def _kept(project):
    """The records whose own cards a hidden block holds, by entry kind ('view' for a whole block)."""
    found = {'record': set(), 'view': set()}
    for entry in project.hidden_blocks:
        for group in entry.groups:
            for top in group.blocks:
                for block in _subtree(top):
                    if isinstance(block, TemplateSectionBlock) and block.props.record_id:
                        found[entry.target.kind].add(block.props.record_id)
    return found


def _locale(project):
    return project.template_package.definition.template.default_locale


def _heading(project, view, blocks):
    """The view's heading as the résumé writes it, else the template's title, else the view's id."""
    for block in blocks:
        if block.type == 'heading' and block.presentation is not None and block.presentation.node_index is None:
            text = ''.join(getattr(part, 'text', '') for part in block.content).strip()
            if text:
                return text
    return locale_text(view.view.title, _locale(project)) or view.id


def _types(project):
    facts = project.facts
    types = {identity.record_id: identity.semantic_type for identity in facts.builtin_identities}
    types.update({record.id: record.semantic_type for record in facts.extensions if record.active})
    return types


def _has_content(project, view, types):
    """Whether the facts hold something the view shows (a visible binding's type), so a view the page lost has
    something to bring back."""
    bound = {binding.semantic_type for binding in view.bindings if visible_binding(view, binding)}
    return any(semantic in bound for semantic in types.values())


def _identity(project, view):
    """The page header with the candidate's name has no eye (H2-d)."""
    kinds = {value.id: value.builtin_kind for value in project.template_package.definition.fact_types}
    return any(kinds.get(binding.semantic_type) == 'candidate' for binding in view.bindings)


def _view_kind(project, view):
    """The Facts group whose rows the view's items are: the builtin kind bound at its item root, else None."""
    if view.view.mode != 'items':
        return None
    from ..templates.source_spans import _bound_root
    kinds = {value.id: value.builtin_kind for value in project.template_package.definition.fact_types}
    found = {kinds.get(binding.semantic_type) for binding in view.bindings
             if _bound_root(binding.pointer, binding.semantic_type, binding.field, view.bindings) == ['*']}
    found.discard(None)
    return found.pop() if len(found) == 1 else None


def block_targets(project):
    """Each template block that has an eye in Facts (H2): its target id, its name, where the eye stands and whether
    the block is hidden. A block the page shows, or one hidden that has content to show; never the page header."""
    from .template_panel_focus import focus_view
    from .template_panel_records import _group_nodes, _shown
    package = project.template_package
    try:
        focus = focus_view(package)[0].id
    except ValueError:
        focus = None
    groups = set(_group_nodes(package))
    types = _types(project)
    rows = []
    for view in package.definition.blocks:
        if _identity(project, view):
            continue
        shown = [block for _parent, _items, block in _tops(project.document, _of_view(view.id))]
        entry = _entry(project, 'view', view.id)
        if shown and entry is None:
            hidden = False
        elif entry is not None:
            hidden, shown = True, [block for group in entry.groups for block in group.blocks]
        elif _shown(project, view) and _has_content(project, view, types):
            hidden = True
        else:
            continue
        place = 'focus' if view.id == focus else 'technology' if view.id in groups else 'other'
        rows.append({'id': VIEW + view.id, 'name': _heading(project, view, shown), 'place': place,
                     'kind': _view_kind(project, view), 'hidden': hidden})
    # A Facts group that shows exactly one block carries that block's eye at its header.
    for kind in ROW_KINDS:
        own = [row for row in rows if row['place'] == 'other' and row['kind'] == kind]
        if len(own) == 1:
            own[0]['place'] = 'group'
    return [{key: value for key, value in row.items() if key != 'kind' or row['place'] == 'group'} for row in rows]


def job_eyes(project, page):
    """By job, its eye (H1): 'shown' for a job with its own card on the page, 'hidden' for one off the page (hidden from
    Facts or deleted on the page), 'locked' for one whose card a hidden block holds. A job with no card of its own (a
    compact list's line) has no eye."""
    kept = _kept(project)
    cards = {block.props.record_id for _parent, _items, block in _tops(project.document,
             lambda block: isinstance(block, TemplateSectionBlock) and block.props.record_id and block.presentation is not None)}
    found = {}
    for record in project.facts.records:
        if record.kind != 'employment':
            continue
        if record.id in kept['view']:
            found[record.id] = 'locked'
        elif record.id in kept['record'] or record.id not in page:
            found[record.id] = 'hidden'
        elif record.id in cards:
            found[record.id] = 'shown'
    return found


def kept_records(project):
    """The records a hidden block or card holds: their rows offer no «Вернуть на страницу» of their own."""
    kept = _kept(project)
    return kept['view'] | kept['record']


def _groups(project, picked):
    """The picked blocks as runs of siblings, each with the earlier siblings that stay on the page."""
    ids = {block.id for _parent, _items, block in picked}
    groups, seen = [], set()
    for parent, items, block in picked:
        if block.id in seen:
            continue
        start = items.index(block)
        run = []
        for sibling in items[start:]:
            if sibling.id not in ids:
                break
            run.append(sibling.model_copy(deep=True))
            seen.add(sibling.id)
        before = [sibling.id for sibling in items[:start] if sibling.id not in ids]
        groups.append(HiddenGroup(parentId=parent, beforeIds=before[-1000:], blocks=run))
    return groups


def _anchors(project, removed):
    """The notices and coverage entries that name a block Hide takes off, with every id they name now."""
    found = []
    for issue in project.import_issues:
        if set(issue.block_ids) & removed:
            found.append(HiddenAnchor(kind='issue', key=issue.id, blockIds=list(issue.block_ids)))
    for index, value in enumerate(project.import_coverage):
        if set(value.block_ids) & removed:
            found.append(HiddenAnchor(kind='coverage', key=sha256(canonical(coverage_identity(value))), index=index,
                                      blockIds=list(value.block_ids)))
    return found


def _target(project, command):
    """('record', job id) or ('view', view id) of a hide or show command; refused for anything without an eye."""
    view = command.values.get('view')
    if command.record_id is not None and view is None:
        record = next((value for value in project.facts.records if value.id == command.record_id), None)
        if record is None or record.kind != 'employment':
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        return 'record', record.id
    if command.record_id is None and view is not None:
        if not any(row['id'] == VIEW + view for row in block_targets(project)):
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        return 'view', view
    raise ValueError('PANEL_ACTION_UNSUPPORTED')


def hide(project, command, allocator):
    """(candidate, steps) taking a job's card or a whole block off the page into the hidden store. The tree steps and
    the anchor steps follow from the candidate, as for a delete on the page."""
    from .off_page import named_records
    kind, identifier = _target(project, command)
    if kind == 'record':
        if job_eyes(project, named_records(project.document)).get(identifier) != 'shown':
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        picked = _tops(project.document, _card_of(identifier))
    else:
        if _entry(project, 'view', identifier) is not None:
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        picked = _tops(project.document, _of_view(identifier))
    if not picked:
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    removed = {block.id for _parent, _items, top in picked for block in _subtree(top)}
    entry = HiddenBlocks(id=allocator.allocate('hidden', ['panel-hidden', kind, identifier]), revision=1,
        target=HiddenTarget(kind=kind, id=identifier), groups=_groups(project, picked), anchors=_anchors(project, removed))
    candidate = project.model_copy(deep=True)
    tops = {block.id for _parent, _items, block in picked}
    for _parent, items, _block in _tops(candidate.document, lambda block: block.id in tops):
        items[:] = [block for block in items if block.id not in tops]
    return candidate, [{'kind': 'put_hidden_blocks', 'beforeRevision': None, 'entry': entry.model_dump(mode='json', by_alias=True)}]


def _refreshed(project, block):
    """A kept block as Show puts it back: each fact field takes its fact's present value; a card or field of a record
    that is gone is left out. Typed text, literals and formatting stay as they were."""
    records = records_by_id(project.facts)

    def keep(value):
        if isinstance(value, TemplateSectionBlock) and value.props.record_id and value.props.record_id not in records:
            return None
        for _container, content in inline_groups(value):
            spans = []
            for span in content:
                if isinstance(span, FactFieldSpan) and span.record_id not in records:
                    continue
                if isinstance(span, BoundLink) and any(item is not None and item.record_id not in records
                                                       for item in (span.label_binding, span.url_binding)):
                    continue
                if isinstance(span, FieldOccurrence) and not hasattr(records[span.record_id], 'cells'):
                    field = working_field(records[span.record_id], span.field_key)
                    if field is None:
                        continue
                    if span.text != field.raw_text:
                        span = span.model_copy(update={'text': field.raw_text, 'synced_fact_revision': field.revision})
                spans.append(span)
            content[:] = spans
        value.children = [child for child in (keep(item) for item in value.children) if child is not None]
        return value
    return keep(block.model_copy(deep=True))


def _anchor_steps(project, entry, restored):
    """Steps that give the kept anchors back their block ids, in their old order."""
    steps = []
    issues = {issue.id: issue for issue in project.import_issues}
    for anchor in entry.anchors:
        if anchor.kind == 'issue':
            current = issues.get(anchor.key)
            if current is None:
                continue
            target = issue_target(current).model_dump(mode='json', by_alias=True)
        else:
            if anchor.index is None or anchor.index >= len(project.import_coverage):
                continue
            current = project.import_coverage[anchor.index]
            if sha256(canonical(coverage_identity(current))) != anchor.key:
                continue
            target = coverage_target(project, anchor.index).model_dump(mode='json', by_alias=True)
        present = set(current.block_ids)
        after = [identifier for identifier in anchor.block_ids if identifier in present or identifier in restored]
        after += [identifier for identifier in current.block_ids if identifier not in after]
        if after != current.block_ids:
            steps.append({'kind': 'set_authored_anchors', 'target': target, 'beforeBlockIds': list(current.block_ids),
                          'afterBlockIds': after})
    return steps


def show(workspace, command, allocator, operations=None):
    """(candidate, steps) putting a hidden card or block back: the kept blocks with their ids where they stood, else (a
    card or block deleted on the page) built again from the facts."""
    from .off_page import named_records
    project = workspace.project
    kind, identifier = _target(project, command)
    page = named_records(project.document)
    if kind == 'record' and job_eyes(project, page).get(identifier) != 'hidden':
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    if kind == 'view' and not next(row for row in block_targets(project) if row['id'] == VIEW + identifier)['hidden']:
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    entry = _entry(project, kind, identifier)
    if entry is None:
        return _rebuild(workspace, kind, identifier, allocator, operations)
    candidate = project.model_copy(deep=True)
    restored = set()
    for group in entry.groups:
        blocks = [block for block in (_refreshed(project, value) for value in group.blocks) if block is not None]
        if not blocks:
            continue
        try:
            items, _parent = parent_items(candidate.document, group.parent_id)
        except Exception:
            raise ValueError('PANEL_ACTION_UNSUPPORTED') from None
        positions = {block.id: index for index, block in enumerate(items)}
        at = next((positions[before] + 1 for before in reversed(group.before_ids) if before in positions), 0)
        items[at:at] = blocks
        restored.update(block.id for top in blocks for block in _subtree(top))
    steps = [{'kind': 'remove_hidden_blocks', 'entryId': entry.id, 'beforeRevision': entry.revision},
             *_anchor_steps(project, entry, restored)]
    return candidate, steps


def _rebuild(workspace, kind, identifier, allocator, operations):
    """A card or block the user deleted on the page, built again from the facts where the import puts it (D179)."""
    from types import SimpleNamespace
    from .panel_views import restore_view, view_title
    from .template_panel_restore import _new_ids, rebuilt_document, restore
    project = workspace.project
    if kind == 'record':
        return restore(workspace, SimpleNamespace(record_id=identifier, job_id=None, period_id=None, values={}), allocator,
                       operations)
    view = next(value for value in project.template_package.definition.blocks if value.id == identifier)
    document = rebuilt_document(project, operations if operations is not None else project.template_operations,
                                workspace.formatting_as_of)
    blocks = [_new_ids(block.model_copy(deep=True), allocator) for _parent, _items, block in _tops(document, _of_view(view.id))
              if not view_title(block, view.id)]
    if not blocks:
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    candidate = project.model_copy(deep=True)
    if not restore_view(candidate.document, project.template_package, view, blocks, allocator, 'view'):
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    return candidate, []
