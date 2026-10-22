"""Changed captures cannot promote or publish an in-flight model return."""

import hashlib
from dataclasses import replace

import pytest

from packages.resume_core.models.contracts import Source
from packages.resume_core.models.template_facts import ExtensionCell, ExtensionRecord
from packages.resume_core.template_import import TemplateImportFailure, digest
from packages.resume_core.templates.projection import reachable_schema
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.test_template_finalization_flow import queued
from tests.templates.test_template_job_routing import service_for


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
@pytest.mark.parametrize('change', ['source', 'account', 'facts'])
async def test_changed_authority_preserves_current_data_and_denies_publication(tmp_path, entry, change):
    fixture = RuntimeFixture(tmp_path)
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.pipeline
    def script(_request, _value):
        if change == 'account':
            pipeline.publisher.jobs.replace_account(2)
        else:
            def edit(workspace):
                data = workspace.pre_draft
                if change == 'source':
                    raw = b'Later source text'
                    source = Source.model_validate({**fixture.source.model_dump(by_alias=True), 'id': 'later-source',
                        'originalName': 'later.txt', 'byteSha256': hashlib.sha256(raw).hexdigest(), 'byteRef': 'sources/later.txt',
                        'units': []})
                    pipeline.originals[(fixture.project, source.id)] = raw
                    data.sources.append(source)
                else:
                    declaration = next(value for value in fixture.package.definition.fact_types if value.id == 'papers')
                    schema = reachable_schema(declaration.data_schema, fixture.package.definition.content_definitions)
                    data.facts.extensions.append(ExtensionRecord(schemaVersion=1, id='manual-record', itemHandle='manual-item',
                        revision=1, semanticType='papers', semanticSchemaHash=digest(schema), active=True,
                        copyOfRecordId=None, relations=[], observationIds=[], cells=[ExtensionCell(id='manual-year', fieldKey='year',
                            revision=1, rawInput='forthcoming', typedValue=None, state='human_raw', origin='human',
                            userCorrected=True, evidence=[], observationIds=[], admissionReceiptIds=[], manualScopeId=None)]))
                return workspace
            pipeline.checkpoint(fixture.project, edit)
        return raw_proposal(fixture.source)
    fixture.transport.scripted = script
    try:
        if service:
            result = await queued(service, fixture, fixture.command)
            assert result.template_outcome.state == 'failed_before_replacement'
        else:
            with pytest.raises(TemplateImportFailure, match='IMPORT_AUTHORITY_REVOKED|IMPORT_CAPTURE_STALE'):
                await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
        current = fixture.current()
        assert current.project is None and len(fixture.transport.calls) == 1
        assert not current.pre_draft.template_operations[0].receipts
        if change == 'source':
            assert current.pre_draft.sources[-1].id == 'later-source'
        elif change == 'facts':
            cell = current.pre_draft.facts.extensions[0].cells[0]
            assert cell.raw_input == 'forthcoming' and cell.typed_value is None and cell.origin == 'human'
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
async def test_duplicate_and_out_of_order_returns_cannot_rewrite_published_state(tmp_path, entry):
    fixture = RuntimeFixture(tmp_path)
    returned = []
    original = fixture.transport.generate
    def generate(request, cancel):
        def retain(frame):
            returned.append((request.on_return, frame))
            request.on_return(frame)
        return original(replace(request, on_return=retain), cancel)
    fixture.transport.generate = generate
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.pipeline
    try:
        if service:
            await queued(service, fixture, fixture.command)
        else:
            await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
        before = fixture.current()
        callback, frame = returned[0]
        callback(frame)
        assert fixture.current() == before
        with pytest.raises(TemplateImportFailure, match='IMPORT_RETURN_CONFLICT'):
            callback(replace(frame, raw_return='{changed delayed return'))
        fixture.now = '2026-10-21T00:00:01+00:00'
        with pytest.raises(TemplateImportFailure, match='IMPORT_RETURN_CONFLICT'):
            callback(frame)
        assert fixture.current() == before and len(fixture.transport.calls) == 2
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()
