"""Facts the template shows and the page does not (F78-R, D179): a record no block names that the import's template has a
shown view for. A fact the template never shows (a role family that only picks a branch, a job of the compact list's
technology, a line kept as «other») is not off the page. Nothing here writes the project."""

from ..models.rich_document import FactFieldSpan
from ..models.template_document import BoundLink
from ..fields import inline_groups
from ..template_capture import item_identities
from ..templates.captured_fields import ownership_parents, visible_binding
from ..templates.operations import operation_value


def named_records(document):
    """The records any block of the document names: by its section, a field, a bound link or its provenance."""
    found = set()

    def spans(content):
        for span in content:
            if isinstance(span, FactFieldSpan):
                found.add(span.record_id)
            elif isinstance(span, BoundLink):
                found.update(value.record_id for value in (span.label_binding, span.url_binding) if value is not None)
                spans(span.content)
    for block in document.blocks():
        record = getattr(block.props, 'record_id', None)
        if record:
            found.add(record)
        for _container, content in inline_groups(block):
            spans(content)
        found.update(value.record_id for value in block.provenance if getattr(value, 'record_id', None))
    return found


def _hidden(project):
    """View id to the records its stored operation results keep out of it (a compact job, a skill moved elsewhere)."""
    hidden = {}
    for value in project.template_package.definition.operations:
        stored = operation_value(project.template_operations, value.id)
        if stored is None:
            continue
        if value.kind == 'partition_employment':
            hidden.setdefault(stored['detailedBlock'], set()).update(stored['compact'])
        elif value.kind == 'assign_skills':
            for group, records in stored['hidden'].items():
                hidden.setdefault(group, set()).update(records)
    return hidden


def off_page(project):
    """The ids of the active records the import's template shows and no block of the page names."""
    if project is None or project.template_package is None:
        return set()
    from .template_panel_records import _shown
    facts = project.facts
    types = {}
    for operation in project.template_operations:
        for identity in item_identities(operation):
            types.setdefault(identity.record_id, identity.semantic_type)
    views = {}
    for view in project.template_package.definition.blocks:
        if _shown(project, view):
            for binding in view.bindings:
                if visible_binding(view, binding):
                    views.setdefault(binding.semantic_type, set()).add(view.id)
    hidden, parents, page = _hidden(project), ownership_parents(facts), named_records(project.document)

    def owners(identifier):
        chain, seen = {identifier}, set()
        while chain - seen:
            current = (chain - seen).pop()
            seen.add(current)
            chain |= parents.get(current, set())
        return chain
    return {record.id for record in [*facts.records, *facts.extensions] if getattr(record, 'active', True)
        and record.id not in page and record.id in types
        and any(not owners(record.id) & hidden.get(view, set()) for view in views.get(types[record.id], ()))}


# The kinds whose cards and field lines Facts can put back (stop 3 of the 2026-11-23 feedback).
RESTORABLE = ('employment', 'education', 'language')


def _period_place(project, record):
    from .template_panel_lines import _sections
    views = {value.id: value for value in project.template_package.definition.blocks}
    for section in _sections(project, record.id):
        view = views.get(section.presentation.view_key)
        if view is not None and sum(1 for node in view.view.nodes if node.type == 'period') == 1:
            return True
    return False


def off_fields(project, records=None):
    """{record id: the panel's field keys} of the cards on the page that have a node for a field with a value and do not
    show it: a field line the user removed. A period counts by its start and end."""
    from ..fields import occurrences, working_field
    from .template_panel_lines import field_place, period_fields, period_words
    from .template_panel_records import DOCUMENT_FIELDS
    if project is None or project.template_package is None:
        return {}
    page = named_records(project.document) if records is None else records
    shown = {(group.record_id, group.key) for group in occurrences(project.document).values()}
    label = period_words(project.template_package)[1]
    found = {}
    for record in project.facts.records:
        if record.kind not in RESTORABLE or record.id not in page:
            continue
        keys = [key for key in sorted(DOCUMENT_FIELDS.get(record.kind, ())) if (record.id, key) not in shown
            and (value := working_field(record, key)) is not None and value.raw_text
            and field_place(project, record, key) is not None]
        for period in getattr(record, 'periods', []):
            parts, _ongoing = period_fields(period, label)
            base = 'period:' + period.id + ':'
            if parts and not any((record.id, base + part) in shown for part in ('start', 'end', 'present')) \
                    and _period_place(project, record):
                keys.extend(key for key in (base + 'start', base + 'end') if working_field(record, key).raw_text)
        if keys:
            found[record.id] = keys
    return found
