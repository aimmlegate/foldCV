"""Test providers answer as the reference protocols ask: offered evidence, items, cells, relations and checks by reference."""

from copy import deepcopy


def _unit(span):
    return span['sourceId'], span['sourceRevision'], span['unitId'], span['unitRevision']


def evidence_ref(span, table):
    if isinstance(span, str):
        return span
    holders = [option for option in table if _unit(option['span']) == _unit(span)
        and option['span']['start'] <= span['start'] and span['end'] <= option['span']['end']]
    if not holders:
        # An unoffered span stays copied, so the reply remains invalid as the test intends.
        return span
    return min(holders, key=lambda option: option['span']['end'] - option['span']['start'])['ref']


def model_pairs(value):
    """The rule/target pairs the model is asked about: the captured targets without the settled checks (D115)."""
    settled = {(check['ruleId'], check['targetId']) for check in value.get('settled') or []}
    return [(target['ruleId'], target['targetId']) for target in value['targets']
        if (target['ruleId'], target['targetId']) not in settled]


def model_targets(value):
    """The captured targets the model is asked about, as the request dicts them."""
    pairs = set(model_pairs(value))
    return [target for target in value['targets'] if (target['ruleId'], target['targetId']) in pairs]


def review_entry(entry, value, table):
    """A review answer names its check by reference; an uncaptured rule/target pair gets an invalid reference and a
    settled one, which the model is not asked about, is left out."""
    if not isinstance(entry, dict) or 'check' in entry or 'ruleId' not in entry:
        return entry
    pairs = model_pairs(value)
    pair = (entry['ruleId'], entry['targetId'])
    if pair not in pairs and any((target['ruleId'], target['targetId']) == pair for target in value['targets']):
        return None
    converted = {key: child for key, child in entry.items() if key not in {'ruleId', 'targetId'}}
    converted['check'] = 'C' + str(pairs.index(pair) + 1) if pair in pairs else 'C0'
    if isinstance(converted.get('evidence'), list):
        converted['evidence'] = [evidence_ref(span, table) for span in converted['evidence']]
    return converted


def proposal_entries(result, value, table):
    """Copied ids become the request's H/E/R references; an id the request did not offer stays copied."""
    references = value.get('references') or {'items': [], 'cells': [], 'relations': []}
    items = {entry['itemHandle']: entry['ref'] for entry in references['items']}
    cells = {entry['cellId']: entry['ref'] for entry in references['cells']}
    relations = {entry['relationId']: entry['ref'] for entry in references['relations']}
    def item(selector):
        if isinstance(selector, dict) and selector.get('kind') == 'handle' and 'itemHandle' in selector:
            return {'kind': 'handle', 'ref': items.get(selector['itemHandle'], selector['itemHandle'])}
        return selector
    def spans(entry):
        if isinstance(entry.get('evidence'), list):
            entry['evidence'] = [evidence_ref(span, table) for span in entry['evidence']]
    for field in result.get('fields', []):
        if isinstance(field, dict):
            field['item'] = item(field.get('item'))
            spans(field)
            if 'effectiveCellIds' in field:
                field['effectiveCells'] = [cells.get(cell, cell) for cell in field.pop('effectiveCellIds')]
    for relation in result['relations']:
        if isinstance(relation, dict):
            selector = relation.get('relation') or {}
            if selector.get('kind') == 'discovery_key':
                relation['relation'] = {'kind': 'new', 'key': selector['key']}
            elif selector.get('kind') == 'relation_id':
                relation['relation'] = {'kind': 'relation', 'ref': relations.get(selector['relationId'], selector['relationId'])}
            relation['subject'], relation['target'] = item(relation.get('subject')), item(relation.get('target'))
            spans(relation)
    for lineage in result.get('lineage', []):
        if isinstance(lineage, dict):
            lineage['parents'] = [items.get(parent, parent) for parent in lineage.get('parents', [])]


def by_reference(answer, value):
    """Convert a copied-id proposal or review answer for a request that offers reference tables."""
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json', by_alias=True)
    table = value.get('evidence') if isinstance(value, dict) else None
    if table is None or not isinstance(answer, dict):
        return answer
    result = deepcopy(answer)
    if 'discoveries' in result:
        if result.get('schemaVersion') != 1:
            return answer
        result['schemaVersion'] = 3
        result.setdefault('relations', [])
        proposal_entries(result, value, table)
    elif 'targets' in value and isinstance(result.get('results'), list):
        result['results'] = [converted for converted in (review_entry(entry, value, table) for entry in result['results'])
            if converted is not None]
        if review_protocol(value) in {'template-review-protocol-3', 'template-review-protocol-4', 'template-review-protocol-5'}:
            # Protocol 3 lists only failing checks, or ones with a reason or evidence; an unlisted check holds. Only a
            # clean answer is shortened: an extra, repeated or conflicting entry stays for the test to refuse.
            answered = [entry.get('check') for entry in result['results'] if isinstance(entry, dict)]
            refs = {'C' + str(index) for index in range(1, len(model_pairs(value)) + 1)}
            if len(answered) == len(set(answered)) == len(result['results']) and set(answered) <= refs:
                result['results'] = [entry for entry in result['results'] if not (entry.get('disposition') == 'satisfied'
                    and not entry.get('reason') and not entry.get('evidence') and not entry.get('actionable'))]
    return result


def review_protocol(value):
    return ((value.get('semanticContext') or {}).get('replyProtocol') or {}).get('version')


def expanded_checks(value):
    """One entry per check, in check order, from review checks grouped by target (older inputs hold one per check)."""
    entries = {}
    for group in (value.get('semanticContext') or {}).get('checks', []):
        if 'check' in group:
            entries[group['check']] = group
            continue
        kind = 'field' if 'pointer' in group else 'relation' if 'relation' in group else 'scope'
        for ref, rule in group['checks'].items():
            entries[ref] = {**{key: part for key, part in group.items() if key != 'checks'}, 'check': ref, 'ruleId': rule,
                'kind': kind, **({'block': group['scope']} if kind == 'scope' else {})}
    return [entries[ref] for ref in sorted(entries, key=lambda ref: int(ref[1:]))]
