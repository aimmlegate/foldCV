"""Explicit synthetic runtime policy; no production model or call-cap default."""

from itertools import count

from packages.resume_core.models.template_facts import WorkingFactsV2
from packages.resume_core.models.template_import import (CleanupOutcome, ImportCapture, LaunchOwner, ModelCapture,
    ObservedUsage, ResumeTemplateImportV1, RuntimePolicy, StartTemplateImportV1)
from packages.resume_core.template_import import admit_operation, capture_task_input, digest, start_operation
from tests.templates.storage_fixtures import package, source


NOW = '2026-10-21T00:00:00+00:00'


def model(name='synthetic-primary'):
    return ModelCapture(adapter='controlled', model=name, effort='medium', capabilityProfile='closed-json-v1',
        capabilityVersion='1', configurationHash=digest({'model': name, 'test': True}))


def owner(index):
    return LaunchOwner(reservationId='reservation-' + str(index), incarnationId='controlled-incarnation', generation=1,
        leaseId='lease-' + str(index), processStartWitness='synthetic-owner', transportSessionId=None,
        transportTurnId=None, pid=None)


def setup_operation(*, cap=8, fallback=True, captured=None, src=None, allow_text_rewrite=True, concurrency=1):
    captured, src = captured or package(), src or source()[0]
    facts = WorkingFactsV2(schemaVersion=2, revision=1, records=[], tombstones=[],
        extensions=[], observations=[], relations=[], manualScopes=[])
    capture = ImportCapture(packageHash=captured.package_hash, sourceHashes={src.id: src.byte_sha256}, factRevisions={},
        authorityHash=digest('synthetic-account-and-permissions'), dependencyHash=digest('synthetic-dependencies'),
        allowTextRewrite=allow_text_rewrite, primary=model(), fallback=model('synthetic-fallback') if fallback else None,
        formattingAsOf={'precision': 'day', 'year': 2026, 'month': 10, 'day': 21},
        policy=RuntimePolicy(callCap=cap, concurrency=concurrency, processingSeconds=300, cleanupSeconds=5,
            finalizationSeconds=30, primaryRepairs=1, fallbackRepairs=1))
    command = StartTemplateImportV1(kind='start_new_import', protocol='template_import_v1', clientRequestId='request', capture=capture)
    serial = count()
    operation, created = start_operation('pipeline-project', command, captured, [src], facts, [], NOW,
        id_factory=lambda prefix: prefix + '-' + str(next(serial)))
    assert created
    return operation, command, captured, src, facts


def blocks_package(count):
    """The synthetic package with its one block repeated: independent blocks for parallel runs (CT10)."""
    import json
    from packages.resume_core.templates.compiler import compile_bytes
    from packages.resume_core.templates.store import BUNDLED_TEMPLATE
    config = package().definition.model_dump(mode='json', by_alias=True)
    first = config['blocks'][0]
    config['blocks'] += [{**first, 'id': 'view-' + str(index), 'placement': {**first['placement'], 'order': first['placement']['order'] + index}}
        for index in range(1, count)]
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def ready_operation(**options):
    operation, command, captured, src, facts = setup_operation(**options)
    operation = admit_operation(operation, NOW)
    operation = capture_task_input(operation, operation.tasks[0].id,
        {'protocol': 'template_import_v1', 'sources': [src.model_dump(mode='json', by_alias=True)],
            'effectiveCells': [], 'tools': []}, [], NOW)
    return operation


def resume_command(operation, identifier='resume-authority'):
    return ResumeTemplateImportV1(kind='resume_import', protocol='template_import_v1', operationId=operation.id,
        authorizationId=identifier, authorityHash=operation.capture.authority_hash)


def usage():
    return ObservedUsage(inputTokens=10, cachedInputTokens=0, outputTokens=4, complete=True)


def cleaned():
    return CleanupOutcome(state='verified', evidenceHash=digest('controlled-terminal-proof'), witness='controlled-terminal')


def source_draft(operation, facts, *, captured=None, src=None):
    from packages.resume_core.models.template_workspace import WorkspaceV7
    from tests.templates.storage_fixtures import workspace
    value = workspace()[0].model_dump(by_alias=True)
    if captured is not None:
        value['project']['templatePackage'] = captured.model_dump(by_alias=True)
    if src is not None:
        value['project']['sources'] = [src.model_dump(by_alias=True)]
    value['projectId'] = operation.project_id
    value['preDraft'] = {'selectedInput': 'text', 'selectedSourceId': value['project']['sources'][0]['id'],
        'sources': value['project']['sources'], 'facts': facts.model_dump(by_alias=True), 'operations': [], 'warnings': [],
        'templatePackage': value['project']['templatePackage'], 'templateOperations': [operation.model_dump(by_alias=True)]}
    value['project'] = None
    return WorkspaceV7.model_validate(value)
