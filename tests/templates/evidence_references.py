"""Test providers answer as the reference protocols ask: offered evidence and review checks are named by reference."""

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


def review_entry(entry, value, table):
    """A review answer names its check by reference; an uncaptured rule/target pair gets an invalid reference."""
    if not isinstance(entry, dict) or 'check' in entry or 'ruleId' not in entry:
        return entry
    pairs = [(target['ruleId'], target['targetId']) for target in value['targets']]
    pair = (entry['ruleId'], entry['targetId'])
    converted = {key: child for key, child in entry.items() if key not in {'ruleId', 'targetId'}}
    converted['check'] = 'C' + str(pairs.index(pair) + 1) if pair in pairs else 'C0'
    if isinstance(converted.get('evidence'), list):
        converted['evidence'] = [evidence_ref(span, table) for span in converted['evidence']]
    return converted


def by_reference(answer, value):
    """Convert a copied-span proposal or review answer for a request that offers an evidence table."""
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json', by_alias=True)
    table = value.get('evidence') if isinstance(value, dict) else None
    if table is None or not isinstance(answer, dict):
        return answer
    result = deepcopy(answer)
    if 'discoveries' in result:
        if result.get('schemaVersion') != 1:
            return answer
        result['schemaVersion'] = 2
        result.setdefault('relations', [])
        for entry in [*result.get('fields', []), *result['relations']]:
            if isinstance(entry, dict) and isinstance(entry.get('evidence'), list):
                entry['evidence'] = [evidence_ref(span, table) for span in entry['evidence']]
    elif 'targets' in value and isinstance(result.get('results'), list):
        result['results'] = [review_entry(entry, value, table) for entry in result['results']]
    return result
