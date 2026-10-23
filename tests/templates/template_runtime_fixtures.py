"""Synthetic transport and assembly exercise the coordinator without render claims."""

import json
from itertools import count

from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.template_identity import capture_span, source_slice
from packages.resume_core.template_import import CleanupProof, digest
from tests.templates.test_template_publication import TemplatePublicationFixture
from tests.templates.pipeline_fixtures import NOW, owner, setup_operation, source_draft
from tests.templates.storage_fixtures import presentation, workspace
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.evidence_references import by_reference
from resume_api.importer.template_pipeline import TemplatePipeline
from resume_api.providers.content import ContentFailure, ContentResult, ContentTransportReturn, ReportedUsage


class ControlledTransport:
    def __init__(self, fixture, scripted=None):
        self.fixture, self.scripted = fixture, scripted
        self.calls, self.serial = [], count(1)
        self.fail_at, self.cleanup_unknown = None, False

    def reserve_owner(self, _operation, _task, _policy):
        return owner(next(self.serial))

    def generate(self, request, cancel):
        value = json.loads(request.text)
        self.calls.append(value)
        if self.fail_at == 'dispatch':
            raise SystemExit('controlled process loss after durable dispatch')
        if self.scripted:
            answer = self.scripted(request, value)
        elif 'targets' in value:
            answer = {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
                'disposition': 'satisfied', 'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}
        else:
            answer = raw_proposal(self.fixture.source)
        raw = answer if isinstance(answer, str) else json.dumps({'payload': by_reference(answer, value)})
        usage = ReportedUsage(10, 0, 4, True)
        request.on_return(ContentTransportReturn(raw, 'completed', None, 1, usage,
            not self.cleanup_unknown, {'transport': 'controlled', 'turnId': str(len(self.calls))}, 'medium'))
        if self.fail_at == 'return':
            raise SystemExit('controlled process loss after durable return')
        try:
            decoded = request.result_type.decode_value(json.loads(raw))
        except ValueError:
            raise ContentFailure('INVALID_RESULT', logical_attempts=1, usage=usage,
                cleanup_verified=not self.cleanup_unknown, dispatch_witness={'transport': 'controlled'}, raw_return=raw) from None
        return ContentResult(decoded, usage, 'controlled', request.policy.model, 0, 1,
            cleanup_verified=not self.cleanup_unknown, dispatch_witness={'transport': 'controlled'},
            reasoning_effort='medium', raw_return=raw)

    def prove_return(self, attempt, frame):
        if not frame.cleanup_verified:
            return None
        return CleanupProof(attempt.id, digest(attempt.owner), digest({'owner': attempt.owner,
            'witness': frame.dispatch_witness}), 'controlled-owned-terminal',
            bool(frame.dispatch_witness and frame.dispatch_witness.get('neverDispatched') is True))

    def reconcile(self, attempt):
        return None


class RuntimeFixture(TemplatePublicationFixture):
    def __init__(self, root, *, scripted=None, cap=8, fallback=True, captured=None, src=None, original_bytes=None):
        super().__init__(root, create=False)
        operation, self.command, self.package, self.source, self.facts = setup_operation(cap=cap, fallback=fallback,
            captured=captured, src=src)
        self.now = NOW
        if src is None:
            from tests.templates.storage_fixtures import source
            original_bytes = source()[1]
        assert original_bytes is not None
        self.originals = {(self.project, self.source.id): original_bytes}
        self.before = source_draft(operation, self.facts, captured=self.package, src=self.source)
        self.before.pre_draft.template_operations = []
        self.canonical.save(self.before, self.originals, {})
        self.jobs.open(self.project)
        self.transport = ControlledTransport(self, scripted)
        self.admissions = 0
        self.pipeline = self.fresh_pipeline()

    def fresh_pipeline(self, publisher=None):
        def authority(operation, current):
            if not self.external_authority or (current.project or current.pre_draft).template_package.package_hash != operation.capture.package_hash:
                from packages.resume_core.template_import import TemplateImportFailure
                raise TemplateImportFailure('IMPORT_CAPTURE_STALE')
        def derive(_operation, _task, _data):
            raise AssertionError('this fixture has no deterministic operations')
        return TemplatePipeline(publisher or self.publisher, self.transport, originals=self.originals, authority=authority,
            assemble=self.assemble, derive=derive, wall=lambda: self.now)

    async def admitted(self):
        self.admissions += 1

    def assemble(self, before, operation):
        full = workspace()[0].model_dump(by_alias=True)
        full.update(before.model_dump(by_alias=True, exclude={'project', 'pre_draft'}))
        full['preDraft'] = None
        full['project'].update({'projectId': before.project_id, 'revision': before.project_revision,
            'sources': [self.source.model_dump(by_alias=True)], 'facts': before.pre_draft.facts.model_dump(by_alias=True),
            'templatePackage': self.package.model_dump(by_alias=True),
            'templateOperations': [operation.model_dump(by_alias=True)],
            'importIssues': [issue.model_dump(by_alias=True) for issue in operation.issues]})
        blocks, coverage = [], []
        fallback_spans = [span for result in operation.task_results if result.disposition == 'source_fallback'
            for span in result.source_spans]
        def overlaps(left, right):
            return left.source_id == right.source_id and left.unit_id == right.unit_id and left.start < right.end and right.start < left.end
        scopes = {scope.id: scope for scope in before.pre_draft.facts.manual_scopes}
        shown_scopes = set()
        for record in before.pre_draft.facts.extensions:
            if not record.active:
                continue
            for cell in record.cells:
                if any(overlaps(span, fallback) for span in cell.evidence for fallback in fallback_spans):
                    continue
                if cell.manual_scope_id in shown_scopes:
                    continue
                text = cell.raw_input
                if cell.manual_scope_id is not None:
                    text = scopes[cell.manual_scope_id].raw_input
                    shown_scopes.add(cell.manual_scope_id)
                blocks.append({'id': 'accepted-' + cell.id, 'revision': 1, 'type': 'paragraph', 'props': {},
                    'content': [{'type': 'text', 'text': text, 'styles': {}}],
                    'children': [], 'provenance': [], 'presentation': presentation(self.package)})
                coverage.extend({'span': span.model_dump(by_alias=True), 'itemHandle': record.item_handle,
                    'blockIds': ['accepted-' + cell.id], 'disposition': 'multiple_views', 'reason': 'controlled field views'}
                    for span in cell.evidence)
        shown = set()
        for result in operation.task_results:
            if result.disposition != 'source_fallback':
                continue
            for index, span in enumerate(result.source_spans):
                if digest(span) in shown:
                    continue
                shown.add(digest(span))
                block_id = 'fallback-' + result.id + '-' + str(index)
                blocks.append({'id': block_id, 'revision': 1, 'type': 'paragraph', 'props': {},
                    'content': [{'type': 'text', 'text': source_slice([self.source], span), 'styles': {},
                        'citations': [span.model_dump(by_alias=True)]}],
                    'children': [], 'provenance': [], 'presentation': presentation(self.package)})
                coverage.append({'span': span.model_dump(by_alias=True), 'itemHandle': None, 'blockIds': [block_id],
                    'disposition': 'fallback', 'reason': 'controlled-source-fallback'})
        for region in full['project']['document']['regions']:
            region['blocks'] = blocks if region['role'] == 'main' else []
        full['project']['importCoverage'] = coverage
        return WorkspaceV7.model_validate(full)

    def text(self):
        return '\n'.join(part.text for block in self.current().project.document.blocks() for part in block.content)
