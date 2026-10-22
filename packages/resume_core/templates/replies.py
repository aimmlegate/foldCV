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


def proposal_schema(content_schema):
    return _closed_schema(ProposalReply, content_schema)


def review_schema():
    return _closed_schema(ReviewReply)
