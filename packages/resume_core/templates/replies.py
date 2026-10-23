"""Closed proposal/review schemas retain raw payload assertions and typed sidecars."""

from copy import deepcopy

from ..models.template_import import ProposalReply, ReferencedProposalReply, ReferencedReviewReply, ReviewReply
from .projection import pointer_tokens, schema_children, validate_schema


def _closed_schema(model, payload_schema=None, choices=None):
    root = model.model_json_schema(by_alias=True)
    # Each marked selection becomes one shared enum of the request's captured choices.
    selections = set()
    def select(value):
        name = value.pop('x-reference', None)
        if name is not None:
            if choices is None or name not in choices:
                raise ValueError('reply selection has no captured choices')
            selections.add(name)
            value.clear()
            value['$ref'] = '#/$defs/' + name
        for _, child in schema_children(value):
            select(child)
    select(root)
    for name in sorted(selections):
        # An empty offer admits no value; the server-only "not" keeps the provider shape a plain string.
        root.setdefault('$defs', {})[name] = ({'type': 'string', 'enum': list(choices[name])} if choices[name]
            else {'type': 'string', 'not': {}})
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
PROPOSAL_PROTOCOL = {'version': 'template-proposal-protocol-4', 'rules': [
    'Return payload, discoveries, fields, relations and lineage. payload follows the block content schema; use null or [] for data the source does not state.',
    'Each declaration binding names a pointer (with * for array elements), a semantic_type, a field and an item_pointer. Every concrete item matched by an item_pointer is its own discovery: {key: unique string, semanticType: the binding semantic_type, pointer: the concrete JSON pointer of that item, for example /0/tasks/1}. Two array elements are two discoveries even when their text is identical. Only these items are discoveries; a relation is never a discovery.',
    'An item is selected as {kind: discovery_key, key: a discovery of this reply} or, for an item listed in references.items, as {kind: handle, ref: its H ref}.',
    'For every binding whose concrete pointer exists in the payload (a null leaf counts; a field under a null or missing parent does not), add one fields entry: {item: the item, fieldKey: the binding field, pointer: the concrete pointer, evidence: refs, effectiveCells: refs}. A selected item never has two entries for the same fieldKey.',
    'Evidence is selected by reference: each evidence entry {ref, text, span} offers one exact source text, and a reply lists only refs. Every non-null value needs the refs of the entries that state it for this item or from which it is read, including dates, booleans, numbers and classifications. A null value has evidence []. effectiveCells lists the E refs of references.cells a value is read from, otherwise [].',
    'For every binding with a relation, add one relations entry per concrete item: {relation: {kind: new, key: a new unique relation key} or, to keep a relation listed in references.relations, {kind: relation, ref: its R ref}; kind: the relation kind, subject: the binding item, target: the item at the relation subject_pointer, evidence: the refs of the item entry and of the target entry it belongs to, at least one}. One relation per subject and kind.',
    'lineage is [{kind: add, parents: [], children: every discovery key and nothing else}]; split and merge name their parents by H ref.',
    'Never copy an id: every selection is a key of this reply or a ref offered by this request.']}

# Application-owned reply rules sent with every review; the checks and rules come from the coordinator.
REVIEW_PROTOCOL = {'version': 'template-review-protocol-2', 'rules': [
    'Return one results entry for every semanticContext.checks entry, exactly once: {check: its check ref, disposition, reason, evidence, actionable}. Add no other entries.',
    'Each check applies one rule (ruleId and rules) to one target: a field (its pointer, value and evidence refs in the proposed payload), a relation (its subject and target item pointers and evidence refs) or the extraction scope. evidence offers every source text by ref.',
    'Apply the rule of the check to that target only. satisfied: the cited evidence supports the value or relation and the rule holds; a null value is satisfied when the source does not state it. violation: the rule is broken; reason names the defect. uncertain: the evidence does not settle it; reason names what is missing.',
    'The scope target checks coverage: every source statement that belongs to the block declaration is extracted, or the source states none. Text outside the declared content is not a coverage gap.',
    'reason is empty for satisfied. evidence lists the refs that support the disposition, or []. actionable is true only for a violation or uncertainty that a corrected proposal could fix from the offered evidence.']}


def check_references(review):
    """Version 2 review checks are named by their position in the captured targets: C1, C2, ..."""
    return {'C' + str(index): target for index, target in enumerate(review.targets, 1)}


def proposal_schema(content_schema, refs=None, references=None):
    """The closed reply schema; refs and references select the request's offers, None keeps the copied-id form of older requests."""
    if refs is None:
        return _closed_schema(ProposalReply, content_schema)
    return _closed_schema(ReferencedProposalReply, content_schema, {'EvidenceRef': refs,
        'ItemRef': [value.ref for value in references.items] if references else [],
        'CellRef': [value.ref for value in references.cells] if references else [],
        'RelationRef': [value.ref for value in references.relations] if references else []})


def review_schema(review=None):
    """Version 2 review inputs select captured checks and evidence by reference; version 1 keeps copied spans."""
    if review is None or review.schema_version == 1:
        return _closed_schema(ReviewReply)
    return _closed_schema(ReferencedReviewReply, choices={
        'EvidenceRef': [value.ref for value in review.evidence], 'CheckRef': list(check_references(review))})
