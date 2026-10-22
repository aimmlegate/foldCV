"""Explicit retained-flank identities make compact range application repeatable."""

from .models.rich_document import Hyperlink
from .models.template_document import BoundLink
from .models.template_mutations import SetManualScopeDisplays, TemplateReplaceInlineRange
from .template_preparation_ids import existing_ids


def descriptor(source, start, end, role):
    identifier = source.binding_id if source.kind == 'field' else source.fragment_id
    return source.kind, identifier, start, end, role


class CutFactory:
    def __init__(self, owner, role):
        self.owner, self.role = owner, role

    def allocate(self, prefix, slot):
        if prefix not in {'binding', 'manual-fragment'} or slot[0] != 'fragment':
            raise ValueError('unsupported compact flank source')
        return self.owner.allocate(('field' if prefix == 'binding' else 'manual_scope', slot[1], slot[2], slot[3], self.role))


class FlankRecorder:
    def __init__(self, allocator):
        self.allocator, self.values = allocator, {}

    def factory(self, role):
        return CutFactory(self, role)

    def allocate(self, key):
        if key in self.values:
            raise ValueError('duplicate retained flank descriptor')
        self.values[key] = self.allocator.allocate('fragment', ['range-flank', *key])
        return self.values[key]

    @property
    def entries(self):
        return [{'source': {'kind': kind, 'bindingId' if kind == 'field' else 'fragmentId': identifier}, 'sourceStart': start, 'sourceEnd': end,
            'role': role, 'fragmentId': value} for (kind, identifier, start, end, role), value in sorted(self.values.items())]


def validate_flank_ids(workspace, request):
    supplied = [entry.fragment_id for step in request.steps if isinstance(step, TemplateReplaceInlineRange)
        and step.flank_bindings is not None for entry in step.flank_bindings]
    if not supplied:
        return
    ordinary = []
    for step in request.steps:
        value = step.model_dump(mode='json', by_alias=True, exclude={'flank_bindings'})
        if isinstance(step, SetManualScopeDisplays):
            for assignment in value['assignments']:
                # A post-tree metadata reference does not allocate the cut fragment again.
                assignment['after'].pop('fragmentId', None)
        ordinary.append(value)
    if len(set(supplied)) != len(supplied) or set(supplied) & (existing_ids(workspace) | existing_ids(ordinary)):
        raise ValueError('compact flank IDs collide with another retained or supplied identity')


class FlankResolver:
    def __init__(self, entries):
        self.values, self.used = {}, set()
        for entry in entries:
            key = descriptor(entry.source, entry.source_start, entry.source_end, entry.role)
            if key in self.values:
                raise ValueError('duplicate supplied flank descriptor')
            self.values[key] = entry.fragment_id

    def allocate(self, key):
        if key not in self.values or key in self.used:
            raise ValueError('missing or repeated compact flank descriptor')
        self.used.add(key)
        return self.values[key]

    def factory(self, role):
        return CutFactory(self, role)

    def finish(self):
        if self.used != self.values.keys():
            raise ValueError('surplus compact flank descriptor')


def splice_inline(content, start, end, inserted, resolver):
    from .rich_mutations import cut_inline, inline_text, utf16_slice
    text = ''.join(inline_text(span) for span in content)
    utf16_slice(text, start, end)
    cursor = 0
    for index, span in enumerate(content):
        length = len(inline_text(span).encode('utf-16-le')) // 2
        if (isinstance(span, (Hyperlink, BoundLink)) and cursor <= start <= end <= cursor + length
                and len(inserted) == 1 and type(inserted[0]) is type(span)
                and inserted[0].model_dump(exclude={'content'}) == span.model_dump(exclude={'content'})):
            result = [part.model_copy(deep=True) for part in content]
            result[index].content = splice_inline(span.content, start - cursor, end - cursor, inserted[0].content, resolver)
            return result
        cursor += length
    return (cut_inline(content, 0, start, id_factory=resolver.factory('prefix'))
        + [part.model_copy(deep=True) for part in inserted]
        + cut_inline(content, end, len(text.encode('utf-16-le')) // 2,
            id_factory=resolver.factory('suffix'), empty_end=True))
