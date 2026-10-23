"""Closed proposal/review schemas retain raw payload assertions and typed sidecars."""

from copy import deepcopy

from ..models.template_import import ProposalReply, ReviewReply
from .projection import pointer_tokens, schema_children, validate_schema


def _closed_schema(model, payload_schema=None):
    root = model.model_json_schema(by_alias=True)
    if payload_schema is not None:
        content = deepcopy(payload_schema)
        definitions = content.pop('$defs', {})
        def rename(value):
            if '$ref' in value:
                value['$ref'] = '#/$defs/content_' + value['$ref'].removeprefix('#/$defs/')
            for _, child in schema_children(value):
                rename(child)
        rename(content)
        for value in definitions.values():
            rename(value)
        root['properties']['payload'] = content
        root.setdefault('$defs', {}).update({'content_' + key: value for key, value in definitions.items()})
    definitions = root.pop('$defs', {})
    used = set()
    def collect(value):
        if '$ref' in value:
            tokens = pointer_tokens(value['$ref'].removeprefix('#'))
            if len(tokens) != 2 or tokens[0] != '$defs' or tokens[1] not in definitions:
                raise ValueError('reply schema needs a local definition reference')
            if tokens[1] not in used:
                used.add(tokens[1])
                collect(definitions[tokens[1]])
        for _, child in schema_children(value):
            collect(child)
    collect(root)
    if used:
        root['$defs'] = {key: definitions[key] for key in sorted(used)}
    def close(value):
        if 'oneOf' in value and 'discriminator' in value:
            tag = value['discriminator']['propertyName']
            choices = []
            for branch in value['oneOf']:
                target = definitions[pointer_tokens(branch['$ref'].removeprefix('#'))[1]] if '$ref' in branch else branch
                choice = target.get('properties', {}).get(tag, {}).get('const')
                if choice is None or choice in choices or target.get('additionalProperties') is not False:
                    raise ValueError('reply union must have disjoint closed tags')
                choices.append(choice)
            value['anyOf'] = value.pop('oneOf')
            value.pop('discriminator')
        if value.get('type') == 'object' and 'properties' in value:
            value['required'] = list(value['properties'])
        value.pop('default', None)
        for path, child in schema_children(value):
            if payload_schema is not None and value is root and (path == 'properties/payload' or path.startswith('$defs/content_')):
                continue
            close(child)
    close(root)
    validate_schema(root)
    return root


# Application-owned reply rules sent with every extraction task; generic for any template declaration.
PROPOSAL_PROTOCOL = {'version': 'template-proposal-protocol-1', 'rules': [
    'Return payload, discoveries, fields, relations and lineage. payload follows the block content schema; use null or [] for data the source does not state.',
    'Each declaration binding names a pointer (with * for array elements), a semantic_type, a field and an item_pointer. Every concrete item matched by an item_pointer is its own discovery: {key: unique string, semanticType: the binding semantic_type, pointer: the concrete JSON pointer of that item, for example /0/tasks/1}. Two array elements are two discoveries even when their text is identical.',
    'For every binding whose concrete pointer exists in the payload (a null leaf counts; a field under a null or missing parent does not), add one fields entry: {item: {kind: discovery_key, key: the discovery of that item}, fieldKey: the binding field, pointer: the concrete pointer, evidence: spans, effectiveCellIds: []}. A discovery never has two entries for the same fieldKey.',
    'Evidence spans are copied exactly, with all their properties, from sourceSpans; choose the spans whose text contains the value. A null value has evidence []. Never invent or edit a span.',
    'For every binding with a relation, add one relations entry per concrete item: {relation: {kind: discovery_key, key: unique string}, kind: the relation kind, subject: {kind: discovery_key, key: the discovery of the binding item}, target: {kind: discovery_key, key: the discovery at the relation subject_pointer}, evidence: the spans of the bound value}. One relation per subject and kind.',
    'lineage is [{kind: add, parents: [], children: all discovery keys}].']}


def proposal_schema(content_schema):
    return _closed_schema(ProposalReply, content_schema)


def review_schema():
    return _closed_schema(ReviewReply)
