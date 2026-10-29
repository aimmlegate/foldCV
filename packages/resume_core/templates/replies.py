"""Closed proposal/review schemas retain raw payload assertions and typed sidecars."""

from copy import deepcopy
import json

from ..models.template_import import (OutlineReply, OutlineReviewReply, ProposalReply, ReferencedProposalReply,
    ReferencedReviewReply, ReviewReply)
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
PROPOSAL_PROTOCOL = {'version': 'template-proposal-protocol-5', 'rules': [
    'Return payload and fields; send null for discoveries, lineage and relations unless a rule below needs them. payload follows the block content schema; use null or [] for data the source does not state.',
    'Evidence is selected by reference: each evidence entry {ref, text} offers one exact source text, and a reply lists only refs. A value copied word for word from an offered text needs no fields entry: the coordinator cites the entries that contain it.',
    'Every other non-null value (reworded, inferred, classified or normalized) needs one fields entry {pointer: its concrete payload pointer, for example /0/role or /items/2, evidence: the refs of the entries that state it, item: null, fieldKey: null, effectiveCells: null}. One entry at a list pointer, for example /items, may give the evidence of every value in that list. A value read from references.cells lists their E refs in effectiveCells.',
    'The coordinator derives one new item per concrete item pointer of the declaration bindings, its add lineage and the relations the bindings configure. To update an item listed in references.items, give at least one fields entry of that item with item {kind: handle, ref: its H ref}; its other values join it. To split or merge listed items, give discoveries {key, semanticType, pointer} for the new items and lineage {kind: split or merge, parents: H refs, children: discovery keys}.',
    'Never copy an id: every selection is a key of this reply or a ref offered by this request.',
    'A request with feedback repairs this block: previousReply is the reply under repair (fields: the pointer of each value, its item H ref when it has one, and its evidence refs), and each feedback entry names a rule, its target (pointer: its place in previousReply) and the defect. Return the whole corrected reply: keep every value of previousReply that no entry names, in the same item and with its evidence, fix each named defect and add what an entry names as missing.']}

# Application-owned reply rules sent with every review; the checks and rules come from the coordinator.
# Protocol 3 (LIVE-05..07): one entry per check made a 477-check review too long to write in 90 s; a list of satisfied
# refs was cut short and a "the rest holds" flag was read as "all checks hold". A reply now lists the checks that fail,
# and a check it does not list holds. LIVE-12 listed all 349 satisfied checks of one review (73 s); the wording now says
# never to list them and that [] is a valid answer (probe P5: 1 entry, 5–12 s).
# Protocol 4 (D115): the coordinator settles the checks of a value it found word for word in its cited line and, in a
# replacement review, of a value the repair left as it was; the model sees and answers only the remaining checks.
# Protocol 5 (D117): a review of one entry of a block checks coverage of that entry's lines only.
REVIEW_PROTOCOL = {'version': 'template-review-protocol-5', 'rules': [
    'semanticContext.checks lists each target once: a field (its pointer in the proposed payload, value and evidence refs), a relation (its kind, subject and target items and evidence refs) or the extraction scope. Its checks map each check ref to the rule (rules) that check applies to that target; a target has one check per rule.',
    'A value of the proposal that has no check is settled already: the coordinator found it word for word in its cited source line, or an earlier review of this same value stands. Do not report it.',
    'Apply every rule of every target. results holds one entry {check, disposition, reason, evidence, actionable} only for a check whose rule is broken (violation) or that the evidence does not settle (uncertain). Never list a satisfied check: a check not in results is satisfied, and results is [] when every check holds.',
    'Rule kinds: evidence_identity: the cited evidence states the value; a value that a cited line lists among others is stated, and a date, number or name written in another form is the same value. A category the declaration asks to choose (an enum value such as a role family) is stated when the cited evidence fits it; the source need not use its name. semantic_support: the cited evidence supports the meaning, qualifiers and individual or team attribution of the value; a null value holds when the source does not state it. claim_ownership, attribution and task_result_separation: as their instructions say. complete_assignment: the scope coverage below.',
    'The scope target checks coverage. evidence offers the complete source text of the CV. Every source statement that belongs to the block declaration is extracted, or the source states none. Text outside the declared content is not a coverage gap, nor is a statement that fits a block in semanticContext.otherBlocks better: that block shows it. A declaration that selects or limits content (a short summary, chosen entries, a list already at its maximum item count) has a gap only when it misses a statement it requires. A gap reason names every missing statement, not examples.',
    'When semanticContext.taskInput.entry is given, the proposal extracts only the lines entry.lines names: the scope target checks coverage of those lines only; a statement on the lines of entry.others is no gap here, and a value read from those lines fails claim_ownership or evidence_identity.',
    'reason is one short sentence in Russian that names the defect or what is missing; evidence lists the refs that support the disposition, or []. actionable is true only when a corrected proposal could fix it from the offered evidence.']}


# D117: a block declared per_entry is outlined first, then each entry is extracted by its own request.
OUTLINE_PROTOCOL = {'version': 'template-outline-protocol-1', 'rules': [
    'This request outlines the block before its entries are extracted one by one. payload.entries lists every entry the block declaration extracts from the evidence, in the order the declaration asks for, each as {title, first, last}: title names the entry as the source does (the employer, the project, the school), first and last are the refs of its first and its last source line; the lines between belong to it.',
    'An entry is one item of the block content; keep the boundaries the source states, as the declaration says. The lines of one entry are contiguous, a line belongs to at most one entry, and a line that states no entry of this block is in none. Return [] when the source states no entry of this block.']}

OUTLINE_REVIEW_PROTOCOL = {'version': 'template-outline-review-protocol-1', 'rules': [
    'outline.entries lists the entries of the block as the coordinator extracts them, each with its title and the refs of its first and last source line. Check the outline against the whole evidence: payload.missing lists every entry of the block the outline leaves out, each as {title, first, last} like an outline entry; payload.remarks lists an outline entry that joins two entries of the source or splits one, as {entries: [their indices], reason}.',
    'Text outside the declared content is no entry, nor is a statement that fits a block in otherBlocks better. reason is one short sentence in Russian. Return empty lists when the outline is complete.']}

# The rule an entry request adds to its proposal protocol.
ENTRY_RULE = ('entry names the part of the source this reply extracts: entry.lines, refs of this request, and the entries '
    'the outline found in them (entry.parts, each by title and its first and last line). payload holds the items of the '
    'block that these lines state, usually one per part, read from those lines only, or [] when they state none; the '
    'lines of entry.others are extracted by their own requests, so never take their values or claims here.')


# The same protocol for a request that offers no captured items or relations: nothing can be updated, split or merged,
# so the reply needs no lineage or relations and the coordinator derives them (LIVE-12: a first projects reply was
# refused for relations that named a handle nobody offered). The schema keeps the keys so a model that still sends them
# decodes; selections of unoffered handles are dropped before completion, relations by discovery key stay.
CONTENT_ONLY_RULES = [
    'Return payload and fields; discoveries may be null. payload follows the block content schema; use null or [] for data the source does not state.',
    PROPOSAL_PROTOCOL['rules'][1],
    PROPOSAL_PROTOCOL['rules'][2],
    'The coordinator derives the items, their add lineage and the relations the bindings configure from the payload; the reply has no lineage or relations. discoveries {key, semanticType, pointer} may name new items or be null.',
    PROPOSAL_PROTOCOL['rules'][4],
    PROPOSAL_PROTOCOL['rules'][5]]
BOOKKEEPING_KEYS = ()


def offers_nothing(references):
    return references is not None and not references.items and not references.relations


def proposal_protocol(references, *, entry=False):
    """The reply rules for a request: the full protocol with offers, the content-only wording without them; an entry
    request (D117) adds the rule that binds the reply to its entry."""
    rules = list(CONTENT_ONLY_RULES) if offers_nothing(references) else PROPOSAL_PROTOCOL['rules']
    if not entry:
        return PROPOSAL_PROTOCOL if rules is PROPOSAL_PROTOCOL['rules'] else {'version': PROPOSAL_PROTOCOL['version'], 'rules': rules}
    return {'version': PROPOSAL_PROTOCOL['version'], 'rules': [*rules, ENTRY_RULE]}


def strip_unoffered_bookkeeping(payload, references):
    """A reply to a request without offers keeps only the bookkeeping it can mean: lineage adds, relations and items named
    by discovery keys. A handle, cell or relation ref nobody offered (LIVE-12: target {kind: handle, ref: item-/0}) is
    dropped and the coordinator derives the fact instead of refusing the whole reply."""
    if not offers_nothing(references) or not isinstance(payload, dict):
        return payload
    def by_key(selection):
        return isinstance(selection, dict) and selection.get('kind') in {'discovery_key', 'new'}
    cleaned = dict(payload)
    if isinstance(payload.get('fields'), list):
        cleaned['fields'] = [{**entry, 'item': entry.get('item') if by_key(entry.get('item')) else None, 'effectiveCells': None}
            if isinstance(entry, dict) else entry for entry in payload['fields']]
    if isinstance(payload.get('lineage'), list):
        cleaned['lineage'] = [entry for entry in payload['lineage'] if isinstance(entry, dict) and not entry.get('parents')] or None
    if isinstance(payload.get('relations'), list):
        cleaned['relations'] = [entry for entry in payload['relations'] if isinstance(entry, dict) and by_key(entry.get('subject'))
            and by_key(entry.get('target')) and (entry.get('relation') is None or by_key(entry.get('relation')))] or None
    return cleaned


def review_protocol(review):
    """The reply protocol a review input was sent with; it selects the reply shape its return is decoded by."""
    return ((review.semantic_context or {}).get('replyProtocol') or {}).get('version')


# Protocols whose reply lists failing checks only; an unlisted check holds.
FAILING_ONLY_PROTOCOLS = frozenset({'template-review-protocol-3', 'template-review-protocol-4', REVIEW_PROTOCOL['version']})


def model_targets(review):
    """The captured targets the model is asked about: every target without a settled check (D115)."""
    settled = {(value.rule_id, value.target_id) for value in review.settled}
    return [target for target in review.targets if (target.rule_id, target.target_id) not in settled]


def check_references(review):
    """Version 2 review checks are named by their position in the model's targets: C1, C2, ..."""
    return {'C' + str(index): target for index, target in enumerate(model_targets(review), 1)}


def proposal_schema(content_schema, refs=None, references=None):
    """The closed reply schema; refs and references select the request's offers, None keeps the copied-id form of older requests."""
    if refs is None:
        return _closed_schema(ProposalReply, content_schema)
    root = _closed_schema(ReferencedProposalReply, content_schema, {'EvidenceRef': refs,
        'ItemRef': [value.ref for value in references.items] if references else [],
        'CellRef': [value.ref for value in references.cells] if references else [],
        'RelationRef': [value.ref for value in references.relations] if references else []})
    if offers_nothing(references):
        # No item, cell or relation can be selected, so a stray selection is a plain string the coordinator drops
        # (strip_unoffered_bookkeeping) instead of a schema refusal of the whole reply.
        for name in ('ItemRef', 'CellRef', 'RelationRef'):
            if name in root.get('$defs', {}):
                root['$defs'][name] = {'type': 'string'}
        validate_schema(root)
    return root


def outline_schema(refs):
    """The closed reply of an outline request: entries bounded by the request's evidence refs (D117)."""
    return _closed_schema(OutlineReply, choices={'EvidenceRef': list(refs)})


def outline_review_schema(refs):
    return _closed_schema(OutlineReviewReply, choices={'EvidenceRef': list(refs)})


def review_schema(review=None):
    """Version 2 review inputs select captured checks and evidence by reference; version 1 keeps copied spans."""
    if review is None or review.schema_version == 1:
        return _closed_schema(ReviewReply)
    return _closed_schema(ReferencedReviewReply, choices={
        'EvidenceRef': [value.ref for value in review.evidence], 'CheckRef': list(check_references(review))})
