"""Synthetic transport and assembly exercise the import coordinator on a project repository, without render claims."""

import asyncio
import hashlib
import json
from itertools import count

from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.project_repository import ProjectRepository, decode_project
from packages.resume_core.template_identity import source_slice
from packages.resume_core.template_import import CleanupProof, TemplateImportFailure, digest
from tests.templates.pipeline_fixtures import NOW, owner, setup_operation, source_draft
from tests.templates.storage_fixtures import presentation, workspace
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.evidence_references import by_reference
from resume_api.importer.template_pipeline import TemplatePipeline
from resume_api.importer.template_sidecar import OperationSidecar
from resume_api.projects.fold import register_import_fold
from resume_api.providers.content import ContentFailure, ContentResult, ContentTransportReturn, ReportedUsage


class ControlledTransport:
    def __init__(self, fixture, scripted=None):
        self.fixture, self.scripted = fixture, scripted
        self.calls, self.prompts, self.serial = [], [], count(1)
        self.fail_at, self.cleanup_unknown = None, False

    def reserve_owner(self, _operation, _task, _policy):
        return owner(next(self.serial))

    def generate(self, request, cancel):
        # The prompt omits span records; scripted answers build spans from the captured request.
        value = request.request_value if request.request_value is not None else json.loads(request.text)
        self.calls.append(value)
        self.prompts.append(request.text)
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


class RuntimeFixture:
    """One pre-draft in a repository under `root`; `pipeline` imports it through the controlled transport."""

    project = 'pipeline-project'

    def __init__(self, root, *, scripted=None, cap=8, fallback=True, captured=None, src=None, original_bytes=None, concurrency=1):
        self.root, self.now, self.external_authority = root, NOW, True
        operation, self.command, self.package, self.source, self.facts = setup_operation(cap=cap, fallback=fallback,
            captured=captured, src=src, concurrency=concurrency)
        if src is None:
            from tests.templates.storage_fixtures import source
            original_bytes = source()[1]
        assert original_bytes is not None
        self.originals = {self.source.id: original_bytes}
        self.before = source_draft(operation, self.facts, captured=self.package, src=self.source)
        self.before.pre_draft.template_operations = []
        self.repository = self.open_repository()
        self.repository.create(self.before, blobs=[('sources', self.source.id, original_bytes,
            hashlib.sha256(original_bytes).hexdigest())])
        self.transport = ControlledTransport(self, scripted)
        self.admissions = 0
        self.pipeline = self.fresh_pipeline()

    def open_repository(self):
        repository = ProjectRepository(self.root / 'store', clock=lambda: self.now)
        repository.start()
        register_import_fold(repository)
        return repository

    def restart(self):
        """A new process on the same store: sessions closed, a new repository and pipeline."""
        for identifier in list(self.repository.sessions):
            self.repository.close(identifier)
        self.repository = self.open_repository()
        self.pipeline = self.fresh_pipeline()
        return self.pipeline

    @property
    def directory(self):
        return self.repository.open(self.project).directory

    @property
    def sidecar(self):
        return OperationSidecar(self.directory)

    def current(self):
        # The durable state: the saved project with the running import's sidecar steps (S7e).
        return self.pipeline.read(self.project)

    def saved(self):
        """The committed project file alone, without the sidecar."""
        directory = self.directory
        return decode_project(directory, (directory / 'workspace.json').read_bytes(), history=True)

    def authority(self, operation, current):
        if not self.external_authority or (current.project or current.pre_draft).template_package.package_hash != operation.capture.package_hash:
            raise TemplateImportFailure('IMPORT_CAPTURE_STALE')

    def derive(self, _operation, _task, _data):
        raise AssertionError('this fixture has no deterministic operations')

    def fresh_pipeline(self):
        return TemplatePipeline(self.transport, repository=self.repository, authority=self.authority,
            assemble=self.assemble, derive=self.derive, wall=lambda: self.now)

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


class EmploymentFixture(RuntimeFixture):
    def assemble(self, before, operation):
        from packages.resume_core.template_assembly import assemble_template
        return assemble_template(before, operation)


def scripted_employment(src, *, unsupported=False):
    from tests.templates.employment_fixtures import employment_proposal
    bad_cells = set()
    def script(_request, value):
        if 'targets' in value:
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
                'disposition': 'violation' if target['targetId'] in bad_cells else 'satisfied',
                'reason': 'Individual 80% is unsupported by the source' if target['targetId'] in bad_cells else '',
                'actionable': False, 'evidence': []} for target in value['targets']]}
        reply = employment_proposal(src, unsupported=unsupported)
        captured = {item['key']: item for item in value.get('capturedHandles', []) if 'key' in item}
        if captured:
            if unsupported:
                bad_cells.add(captured['results-entry']['cellIds']['value'])
            for field in reply['fields']:
                field['item'] = {'kind': 'handle', 'itemHandle': captured[field['item']['key']]['itemHandle']}
            known = {(relation['kind'], relation['subjectId'], relation['targetId']): relation['id']
                for relation in value['capturedRelations']}
            for relation in reply['relations']:
                subject, target = captured[relation['subject']['key']], captured[relation['target']['key']]
                relation['subject'] = {'kind': 'handle', 'itemHandle': subject['itemHandle']}
                relation['target'] = {'kind': 'handle', 'itemHandle': target['itemHandle']}
                relation['relation'] = {'kind': 'relation_id', 'relationId': known[(relation['kind'], subject['recordId'], target['recordId'])]}
            reply['discoveries'], reply['lineage'] = [], []
        return reply
    def observe(_request, value):
        if 'targets' in value and unsupported:
            bad_cells.update(item['cellIds']['value'] for item in value['handleMap']
                if item.get('key') == 'results-entry')
        return script(_request, value)
    return observe


async def import_task(fixture, command=None, *, kind='start', operation_id=None):
    """Run one import as the v2 import task over the fixture's repository and pipeline; returns the finished status."""
    from resume_api.projects.imports import ImportCommand, ImportService
    from resume_api.projects.service import ProjectService
    projects = ProjectService(fixture.repository)
    service = ImportService(projects, fixture.pipeline, commands=lambda *_args: command or fixture.command)
    request = ImportCommand(kind=kind, clientRequestId=(command or fixture.command).client_request_id
        if kind == 'start' else 'resume-request', operationId=operation_id)
    identifier = await service.start(fixture.project, request, asyncio.Event())
    runner = service.runners.get(identifier)
    if runner is not None:
        await runner
    return next(value for value in projects.tasks.list(fixture.project) if value['id'] == identifier)
