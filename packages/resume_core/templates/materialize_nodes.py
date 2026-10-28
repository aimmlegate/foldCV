"""Turn configured nodes into editable rich fields with durable presentation refs."""

from dataclasses import dataclass

from ..models.template_facts import ExtensionCell
from ..models.template_document import BoundLink, FieldOccurrence, FieldRef, ManualScopeSpan, PresentedText
from .models import AuthoredPresentation
from .projection import pointer_tokens
from .compiler import canonical, sha256


OVERRIDES = {'font': None, 'size': None, 'color': None, 'alignment': None, 'bold': None, 'italic': None}


def stable_id(*parts):
    return 'template-' + sha256(canonical(list(parts)))


@dataclass(frozen=True)
class DisplayField:
    relative: tuple[str, ...]
    record_id: str
    item_handle: str
    cell: ExtensionCell


def reference(package, view, token, instance, handle=None, node_index=None):
    return AuthoredPresentation(packageHash=package.package_hash, viewKey=view, styleToken=token,
        templateInstanceId=instance, itemHandle=handle, overrides=OVERRIDES, nodeIndex=node_index)


def literal(text, presentation):
    return PresentedText(type='text', text=text, styles={}, presentation=presentation)


def locale_text(values, locale):
    return values.get(locale, '')


def fallback_style(declaration):
    if declaration.view.fallback_style is not None:
        return declaration.view.fallback_style
    if declaration.view.nodes:
        return declaration.view.nodes[0].style
    raise ValueError('materialized fallback has no configured text style')


def field_span(field, ref, instance, position, scopes, shown_scopes):
    cell = field.cell
    if cell.manual_scope_id is not None:
        if cell.manual_scope_id in shown_scopes:
            return None
        shown_scopes.add(cell.manual_scope_id)
        scope = scopes[cell.manual_scope_id]
        root = stable_id(instance, 'manual-scope-occurrence', ref.node_index, scope.id)
        return ManualScopeSpan(type='manual_scope', scopeId=scope.id, occurrenceId=root,
            fragmentId=stable_id(root, 'fragment'), text=scope.raw_input, styles={}, presentation=ref,
            citations=cell.evidence)
    if not cell.raw_input:
        return None
    root = stable_id(instance, 'occurrence', ref.node_index, position, cell.id)
    return FieldOccurrence(type='fact_field', bindingId=stable_id(root, 'fragment'), bindingRootId=root,
        recordId=field.record_id, fieldKey=cell.field_key, cellId=cell.id, occurrenceId=root,
        complete=True, presentation=ref, text=cell.raw_input, styles={}, syncedFactRevision=cell.revision)


def bound_ref(field, occurrence):
    return FieldRef(recordId=field.record_id, fieldKey=field.cell.field_key, cellId=field.cell.id, occurrenceId=occurrence)


def link_part(ref, instance, label, url, scopes, shown_scopes):
    """The label links to the exact URL; a URL-only record shows its URL, and a label without a URL stays a plain field."""
    if any(field.cell.manual_scope_id is not None for field in [*label, *url]):
        raise ValueError('a bound link cannot show a manual edit scope')
    shown = (label or url)[0]
    part = field_span(shown, ref.model_copy(update={'item_handle': shown.item_handle}, deep=True), instance, 0, scopes, shown_scopes)
    if not url:
        return part
    target = url[0]
    root = stable_id(instance, 'occurrence', ref.node_index, 'url', target.cell.id) if label else part.occurrence_id
    return BoundLink(type='bound_link', href=target.cell.raw_input, content=[part],
        labelBinding=bound_ref(shown, part.occurrence_id) if label else None, urlBinding=bound_ref(target, root),
        presentation=ref.model_copy(update={'item_handle': target.item_handle}, deep=True))


def render_plain_fields(package, declaration, instance, fields, scopes, shown_scopes):
    blocks, displayed = [], {}
    if not fields:
        return blocks, displayed
    token = fallback_style(declaration)
    for field in fields:
        ref = reference(package, declaration.id, token, instance, field.item_handle)
        part = field_span(field, ref, instance, field.cell.id, scopes, shown_scopes)
        if part is None:
            continue
        identifier = stable_id(instance, 'unassigned', field.cell.id)
        blocks.append({'type': 'paragraph', 'id': identifier, 'revision': 1, 'props': {}, 'content': [part],
            'children': [], 'provenance': [], 'presentation': ref})
        displayed[field.cell.id] = [identifier]
    return blocks, displayed


def render_nodes(package, declaration, instance, fields, scopes, shown_scopes, period_format=None, durations=None):
    blocks, displayed = [], {}
    locale = package.definition.template.default_locale
    def scalar(path):
        matches = [field for field in fields if field.relative == tuple(pointer_tokens(path))]
        if len(matches) > 1:
            raise ValueError('one view field selects multiple current cells')
        return matches
    def collection(node):
        base = tuple(pointer_tokens(node.field))
        tail = tuple(pointer_tokens(node.item_field)) if node.item_field is not None else ()
        return sorted([field for field in fields if len(field.relative) == len(base) + 1 + len(tail)
            and field.relative[:len(base)] == base and field.relative[len(base)].isdecimal()
            and field.relative[len(base) + 1:] == tail], key=lambda field: (int(field.relative[len(base)]), field.cell.id))
    def block(content, ref, selected=(), *, kind='paragraph', suffix=''):
        if not content:
            return
        identifier = stable_id(instance, ref.node_index, suffix, [field.cell.id for field in selected])
        blocks.append({'type': kind, 'id': identifier, 'revision': 1, 'props': {}, 'content': content,
            'children': [], 'provenance': [], 'presentation': ref})
        for field in selected:
            displayed.setdefault(field.cell.id, []).append(identifier)
    def shown(path):
        return [field for field in scalar(path) if field.cell.raw_input or field.cell.manual_scope_id is not None]
    def parts(selected, base):
        result = []
        for position, field in enumerate(selected):
            part = field_span(field, base.model_copy(update={'item_handle': field.item_handle}, deep=True),
                instance, position, scopes, shown_scopes)
            if part is not None:
                result.append((field, part))
        return result
    for index, node in enumerate(declaration.view.nodes):
        ref = reference(package, declaration.id, node.style, instance, node_index=index)
        label, prefix = locale_text(node.label, locale), locale_text(node.prefix, locale)
        def lead():
            return [literal(prefix, ref)] if prefix else []
        if node.type == 'link':
            name, url = shown(node.name_field), shown(node.url_field)
            if name or url:
                if label:
                    block([literal(label, ref)], ref, suffix='label')
                block([*lead(), link_part(ref, instance, name, url, scopes, shown_scopes)], ref, [*name, *url])
            continue
        if node.type == 'focus_entry':
            # The stated experience is its own line in the detail style; without one, the time the technology's jobs
            # span is shown as plain text (D104).
            detail = reference(package, declaration.id, node.detail_style or node.style, instance, node_index=index)
            name, experience = parts(scalar(node.name_field), ref), parts(scalar(node.experience_field), detail)
            if name or experience:
                if label:
                    block([literal(label, ref)], ref, suffix='label')
                if name:
                    block([*lead(), *(part for _field, part in name)], ref, [field for field, _part in name])
                computed = (durations or {}).get(name[0][0].record_id) if name and not experience else None
                if computed:
                    block([literal(computed, detail)], detail, suffix='detail')
                block([part for _field, part in experience], detail, [field for field, _part in experience], suffix='detail')
            continue
        if node.type == 'text':
            selected = scalar(node.field)
        elif node.type == 'join_fields':
            selected = [field for path in node.fields for field in scalar(path)]
        elif node.type in {'join_items', 'tags', 'bullets'}:
            selected = collection(node)
        elif node.type == 'period':
            start, end, ongoing = [scalar(node.field + '/' + name) for name in ['start', 'end', 'ongoing']]
            current = bool(ongoing) and ongoing[0].cell.typed_value is True
            # A declared period format shows its localized ongoing label instead of the boolean cell.
            selected = [*start, *(([] if period_format else ongoing) if current else end)]
        else:
            raise ValueError('template materializer primitive is not implemented: ' + node.type)
        visible = parts(selected, ref)
        if not visible:
            continue
        if label:
            block([literal(label, ref)], ref, suffix='label')
        if node.type == 'bullets':
            for field, part in visible:
                block(lead() + [part], ref, [field], kind='bullet_list', suffix=field.cell.id)
            continue
        # Tags without a declared separator keep the comma every package before 2.5.0 materialized.
        separator = ((period_format['separator'] if period_format else '–') if node.type == 'period'
            else node.separator if node.type in {'join_fields', 'join_items'} else (node.separator or ', ') if node.type == 'tags'
            else '')
        content = lead()
        for position, (_field, part) in enumerate(visible):
            if position:
                content.append(literal(separator, ref))
            content.append(part)
        if node.type == 'period' and period_format and current:
            content += [literal(separator, ref), literal(locale_text(period_format['ongoingLabel'], locale), ref)]
        block(content, ref, [field for field, _part in visible])
    return blocks, displayed
