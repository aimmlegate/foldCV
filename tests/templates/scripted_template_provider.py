"""A scripted content provider for strict template imports: no model, deterministic replies, every call counted."""

import json

from packages.resume_core.models.contracts import Source
from resume_api.providers.content import ContentResult, ContentTransportReturn, ContentFailure, ReportedUsage
from resume_api.providers.dynamic_result import DynamicResultSpec
from tests.templates.employment_fixtures import employment_proposal
from tests.templates.evidence_references import by_reference


def scripted_template_answer(value):
    """Extraction answers with the F01 employment proposal over the task's own source unit; review accepts every target."""
    if 'targets' in value:
        return by_reference({'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
            'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}, value)
    # Whole-unit evidence entries name every unit the task may cite, with their texts.
    units = {}
    for option in value['evidence']:
        span, text = option['span'], option['text']
        key = (span['unitId'], span['unitRevision'])
        if span['start'] == 0 and len(text) >= len(units.get(key, ('', 0))[0]):
            units[key] = (text, span)
    first = next(iter(units.values()))[1]
    src = Source.model_validate({'id': first['sourceId'], 'revision': first['sourceRevision'], 'originalName': 'scripted.txt',
        'mimeType': 'text/plain', 'byteSha256': '0' * 64, 'byteRef': 'sources/scripted', 'parser': 'text', 'parserVersion': '1',
        'units': [{'id': unit_id, 'revision': revision, 'order': index, 'text': text,
            'location': {'kind': 'pasted', 'index': index, 'row': None, 'column': None}, 'disposition': 'shown', 'representedFactIds': []}
            for index, ((unit_id, revision), (text, _span)) in enumerate(units.items())],
        'overlays': [], 'warnings': []})
    return by_reference(employment_proposal(src), value)


def scripted_template_result(provider, request, answer=scripted_template_answer):
    """Answer one template task as a provider would, reporting the return before the result."""
    value = request.request_value if request.request_value is not None else json.loads(request.text)
    provider.calls.append({'kind': 'template_review' if 'targets' in value else 'template_extraction'})
    raw = json.dumps({'payload': answer(value)})
    usage, witness = ReportedUsage(10, 0, 4, True), {'transport': 'scripted', 'turnId': str(len(provider.calls))}
    if request.on_return is not None:
        request.on_return(ContentTransportReturn(raw, 'completed', None, 1, usage, True, witness, request.policy.reasoning_effort))
    return ContentResult(request.result_type.decode_value(json.loads(raw)), usage, 'scripted', request.policy.model, 0, 1,
        cleanup_verified=True, dispatch_witness=witness, reasoning_effort=request.policy.reasoning_effort, raw_return=raw)


class ScriptedTemplateProvider:
    template_adapter = 'scripted'

    def __init__(self):
        self.calls = []

    def generate(self, request, _files, _cancel):
        if not isinstance(request.result_type, DynamicResultSpec):
            raise ContentFailure('UNSCRIPTED_PROVIDER_PATH')
        return scripted_template_result(self, request)
