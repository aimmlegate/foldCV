"""New-project persistence with captured packages; legacy wires stay unchanged."""

from __future__ import annotations

from math import isclose
from typing import Literal

import hashlib
import threading
from collections import OrderedDict

from pydantic import ConfigDict, Field, field_serializer, model_validator

from ..project_limits import ARCHIVE_BYTES, ARCHIVE_ENTRY_BYTES, ARCHIVE_EXPANDED_BYTES, PROJECT_CEILING_BYTES
from .contracts import Id, Revision, Sha256, Source, Wire, _safe_path, _unique
from .rich_document import FieldBinding, ImageBlock, NarrativeCitation, SectionBlock, SourceWitness, WorkingOwnership
from .rich_workspace import (WorkspaceV6, RichPreDraft, LocalImageAsset, ImmutableFactEvidence,
                            RichOperation, RichRenderSnapshot, RichSyncRecord)
from .template_mutations import TemplateSyncRecord
from .template_document import BoundLink, FieldOccurrence, RichDocumentV2
from .template_facts import SourceSpan, WorkingFactsV2
from .template_import import ExportAttempt, ImportIssue, ImportOperation
from .template_render import TemplateExportCapture, TemplateRenderRequestV1
from ..templates.models import StoredTemplatePackage
from ..templates.store import verify_package


class SpanCoverage(Wire):
    span: SourceSpan
    item_handle: Id | None
    block_ids: list[Id]
    disposition: Literal["accepted", "fallback", "source_only", "multiple_views"]
    reason: str | None


class ImportHistoryRef(Wire):
    """A published import's record, kept in the project's history file of this hash (D104)."""
    operation_id: Id
    sha256: Sha256


# Recently written or read history files by hash; a copy read without its records can still be archived (D104).
_HISTORY_TEXTS: 'OrderedDict[str, bytes]' = OrderedDict()
_HISTORY_LOCK = threading.Lock()
HISTORY_CACHE_BYTES = 64 * 1024 * 1024


def remember_history(digest: str, raw: bytes) -> None:
    with _HISTORY_LOCK:
        _HISTORY_TEXTS[digest] = raw
        _HISTORY_TEXTS.move_to_end(digest)
        while sum(len(value) for value in _HISTORY_TEXTS.values()) > HISTORY_CACHE_BYTES and len(_HISTORY_TEXTS) > 1:
            _HISTORY_TEXTS.popitem(last=False)


def history_text(digest: str) -> bytes | None:
    with _HISTORY_LOCK:
        return _HISTORY_TEXTS.get(digest)


def history_bytes(operation) -> bytes:
    from ..templates.compiler import canonical
    return canonical(operation)


def history_refs(operations) -> list[ImportHistoryRef]:
    return [ImportHistoryRef(operationId=operation.id, sha256=hashlib.sha256(history_bytes(operation)).hexdigest())
        for operation in operations]


def validated_with_history(workspace):
    """Validate a workspace again without losing its loaded import records, which no dump carries (D104)."""
    data = workspace.model_dump(by_alias=True)
    project = getattr(workspace, 'project', None)
    if project is not None and getattr(project, 'template_operations', None):
        data['project']['templateOperations'] = [value.model_dump(by_alias=True) for value in project.template_operations]
    return type(workspace).model_validate(data)


class ProjectV6(Wire):
    schema_version: Literal[6]
    project_id: Id
    revision: Revision
    created_at: str
    sources: list[Source]
    evidence_records: list[ImmutableFactEvidence]
    facts: WorkingFactsV2
    document: RichDocumentV2
    assets: list[LocalImageAsset]
    operations: list[RichOperation]
    renders: list[RichRenderSnapshot]
    template_package: StoredTemplatePackage
    import_coverage: list[SpanCoverage]
    import_issues: list[ImportIssue]
    # The import records are 70% of a project's bytes and the editor never reads them (D104): the workspace JSON names
    # their history files, and the records themselves are loaded only by imports, publication and archives.
    import_history: list[ImportHistoryRef] = Field(default_factory=list)
    template_operations: list[ImportOperation] = Field(default_factory=list, exclude=True)
    exports: list[ExportAttempt]
    export_inputs: list[TemplateExportCapture] = Field(default_factory=list, exclude_if=lambda value: not value)

    @field_serializer('import_history', mode='wrap')
    def serialized_history(self, value, handler):
        # Loaded records name their current files; a project read without them keeps the references it was read with.
        return handler(history_refs(self.template_operations) if self.template_operations else value)

    @property
    def history_loaded(self) -> bool:
        return bool(self.template_operations) or not self.import_history

    def current_history(self) -> list[ImportHistoryRef]:
        return history_refs(self.template_operations) if self.template_operations else list(self.import_history)

    def __eq__(self, other):
        # Equal saved state: the same import records by hash, whether a copy has them loaded or not (D104).
        if not isinstance(other, ProjectV6) or not (self.template_operations or other.template_operations):
            return super().__eq__(other)
        if self.current_history() != other.current_history():
            return False
        aligned = other.model_copy(update={'import_history': self.import_history, 'template_operations': self.template_operations})
        return super().__eq__(aligned)

    @model_validator(mode="after")
    def integrity(self):
        from ..template_identity import source_slice
        from ..template_scope_occurrences import validate_scope_occurrences
        verify_package(self.template_package)
        validate_scope_occurrences(self)
        for name in ('evidence_records','assets','operations','renders','import_issues','template_operations','exports'):
            _unique([item.id for item in getattr(self,name)],'project '+name)
        _unique([ref.operation_id for ref in self.import_history], 'project import history')
        if self.template_operations and self.import_history and (
                {ref.operation_id for ref in self.import_history} != {operation.id for operation in self.template_operations}):
            raise ValueError('loaded import records differ from the import history')
        if self.template_operations:
            # Loaded records name their own files, so a loaded copy equals the one read from them.
            self.import_history = history_refs(self.template_operations)
        _unique([(source.id, source.revision) for source in self.sources], 'source revision')
        for source in self.sources:
            _unique([(unit.id, unit.revision) for unit in source.units], 'source unit revision')
        records={r.id for r in self.facts.records}|{r.id for r in self.facts.extensions if r.active}
        cells={c.id:(r.id,c.field_key) for r in self.facts.extensions for c in r.cells}
        builtins={r.id:r for r in self.facts.records}
        assets={a.id:a for a in self.assets};retained={}
        recipe=self.template_package.recipe
        from ..rich_fields import working_field,field_key
        from ..templates.compiler import canonical,sha256
        from ..templates.projection import reachable_schema,schema_at
        types={t.id:reachable_schema(t.data_schema,self.template_package.definition.content_definitions) for t in self.template_package.definition.fact_types}
        declarations = {t.id: t for t in self.template_package.definition.fact_types}
        from ..template_capture import schema_hash
        from ..templates.builtin_mapping import bind_builtin_allocation
        for identity in self.facts.builtin_identities:
            declaration = declarations.get(identity.semantic_type)
            if (declaration is None or declaration.builtin_kind is None
                    or identity.semantic_schema_hash != schema_hash(declaration, self.template_package)
                    or identity.record_id in builtins and builtins[identity.record_id].kind != declaration.builtin_kind):
                raise ValueError('incompatible durable builtin identity')
            bind_builtin_allocation(identity, declaration, lambda _prefix: None, new=False)
        record_types = {r.id: {r.semantic_type} for r in self.facts.extensions}
        builtin_types = {value.record_id: value.semantic_type for value in self.facts.builtin_identities}
        for record in self.facts.records:
            record_types[record.id] = ({builtin_types[record.id]} if record.id in builtin_types else
                {t.id for t in declarations.values() if t.builtin_kind == record.kind})
        for record in self.facts.extensions:
            schema=types.get(record.semantic_type)
            if schema is None or record.semantic_schema_hash!=sha256(canonical(schema)):
                raise ValueError('extension semantic schema identity mismatch')
            for cell in record.cells: schema_at(schema,'/'+cell.field_key.replace('.','/'))
            for key in record.retired_cell_ids: schema_at(schema, '/'+key.replace('.', '/'))
        for relation in self.facts.relations:
            if not relation.active:
                continue
            if not any(declaration.kind == relation.kind
                       and set(declaration.target_types) & record_types.get(relation.target_id, set())
                       for semantic_type in record_types.get(relation.subject_id, set())
                       for declaration in declarations[semantic_type].relations):
                raise ValueError('undeclared or incompatible effective relationship')
        def field_reference(record_id,key,cell_id):
            if record_id not in records: raise ValueError('missing bound record')
            if record_id in builtins:
                if working_field(builtins[record_id],key) is None or cell_id not in {None,field_key(record_id,key)}:
                    raise ValueError('invalid built-in field identity')
            elif cells.get(cell_id)!=(record_id,key): raise ValueError('invalid extension field identity')
        def presentation(value):
            if value is None: return
            if (value.package_hash!=self.template_package.package_hash or value.view_key not in recipe.views
                    or value.style_token not in recipe.style.text):
                raise ValueError('invalid authored presentation reference')
            if value.node_index is not None and value.node_index >= len(recipe.views[value.view_key].nodes):
                raise ValueError('authored presentation node is outside its captured view')
            if value.overrides.font is not None and value.overrides.font not in recipe.style.fonts:
                raise ValueError('invalid manual font token')
        for block in self.document.blocks():
            if block.presentation is None: raise ValueError('authored block presentation missing')
            presentation(block.presentation)
            if isinstance(block,SectionBlock) and block.props.record_id is not None and block.props.record_id not in records:
                raise ValueError('missing authored working record')
            for provenance in block.provenance:
                if isinstance(provenance, (FieldBinding, NarrativeCitation, WorkingOwnership)):
                    if provenance.record_id not in records:
                        raise ValueError('missing provenance record')
                    keys = [provenance.field_key] if isinstance(provenance, FieldBinding) else (
                        provenance.field_keys if isinstance(provenance, NarrativeCitation) else [])
                    record = builtins.get(provenance.record_id) or next(
                        r for r in self.facts.extensions if r.id == provenance.record_id)
                    if any(working_field(record, key) is None for key in keys):
                        raise ValueError('missing provenance field')
            if isinstance(block,ImageBlock):
                asset=assets.get(block.props.asset_id)
                if asset is None or not isclose(block.props.width/block.props.height,asset.width/asset.height,rel_tol=1e-6):
                    raise ValueError('invalid authored image reference/aspect')
                retained[asset.sha256]=asset.size
            groups=[block.content] if isinstance(block.content,list) else [c.content for row in block.content.rows for c in row.cells] if block.type=='table' else []
            if isinstance(block,ImageBlock): groups.append(block.props.caption)
            for content in groups:
                for span in content:
                    presentation(getattr(span,'presentation',None))
                    if isinstance(span,BoundLink):
                        for reference in (span.label_binding,span.url_binding):
                            if reference is not None: field_reference(reference.record_id,reference.field_key,reference.cell_id)
                    parts=span.content if isinstance(span,BoundLink) else [span]
                    for part in parts:
                        presentation(getattr(part,'presentation',None))
                        if isinstance(part,FieldOccurrence):
                            field_reference(part.record_id,part.field_key,part.cell_id)
        if sum(retained.values())>20*1024*1024: raise ValueError('live image retention exceeds limit')
        checked_spans=set()
        def evidence(span):
            key=(span.source_id,span.source_revision,span.unit_id,span.unit_revision,span.start,span.end,span.slice_hash)
            if key not in checked_spans: source_slice(self.sources,span);checked_spans.add(key)
        for observation in self.facts.observations:
            for span in observation.evidence: evidence(span)
        for record in self.facts.extensions:
            for cell in record.cells:
                for span in cell.evidence: evidence(span)
        for coverage in self.import_coverage: evidence(coverage.span)
        for block in self.document.blocks():
            groups = [block.content] if isinstance(block.content, list) else (
                [cell.content for row in block.content.rows for cell in row.cells] if block.type == 'table' else [])
            if isinstance(block, ImageBlock):
                groups.append(block.props.caption)
            for group in groups:
                for inline in group:
                    for part in getattr(inline, 'content', [inline]):
                        for span in getattr(part, 'citations', []):
                            evidence(span)
        source_units = {(s.id, s.revision, u.id, u.revision) for s in self.sources for u in s.units}
        def legacy_evidence(spans):
            if any((s.source_id, s.source_revision, s.unit_id, s.unit_revision) not in source_units for s in spans):
                raise ValueError('missing retained source evidence')
        for record in self.evidence_records:
            legacy_evidence(record.evidence)
        for record in self.facts.records:
            legacy_evidence(record.evidence)
            for period in getattr(record, 'periods', []):
                legacy_evidence(period.evidence)
        for block in self.document.blocks():
            for provenance in block.provenance:
                if isinstance(provenance, (SourceWitness, NarrativeCitation)):
                    legacy_evidence(provenance.evidence)
        block_ids = {block.id for block in self.document.blocks()}
        from ..template_capture import item_identities
        handles = ({r.item_handle for r in self.facts.extensions} | {value.item_handle for value in self.facts.builtin_identities}
            | {value.item_handle for operation in self.template_operations for value in item_identities(operation)})
        loaded = self.history_loaded
        for coverage in self.import_coverage:
            if not set(coverage.block_ids) <= block_ids or loaded and coverage.item_handle is not None and coverage.item_handle not in handles:
                raise ValueError('missing source coverage target')
        # Receipts live in the import records; a project read without them was checked when it was published.
        receipt_ids = [r.id for operation in self.template_operations for r in operation.receipts]
        _unique(receipt_ids, 'project review receipt')
        receipts=set(receipt_ids)
        for observation in self.facts.observations if loaded else ():
            if not set(observation.receipt_ids)<=receipts: raise ValueError('unresolved observation receipt')
        for record in self.facts.extensions if loaded else ():
            for cell in record.cells:
                if not set(cell.admission_receipt_ids)<=receipts: raise ValueError('unresolved admission receipt')
        for operation in self.template_operations:
            if operation.project_id!=self.project_id or operation.capture.package_hash!=self.template_package.package_hash:
                raise ValueError('captured operation/package mismatch')
        _unique([value.attempt_id for value in self.export_inputs], 'export input')
        exports = {value.id: value for value in self.exports}
        for captured in self.export_inputs:
            attempt = exports.get(captured.attempt_id)
            if attempt is None or (attempt.document_hash, attempt.facts_hash, attempt.presentation_hash,
                    attempt.package_hash) != (captured.request.document_hash, captured.request.facts_hash,
                    captured.request.presentation_hash, captured.request.package_hash):
                raise ValueError('export input has no matching attempt')
            TemplateRenderRequestV1.model_validate({**captured.request.model_dump(by_alias=True), 'package': self.template_package})
        return self


class RichPreDraftV2(RichPreDraft):
    facts: WorkingFactsV2
    template_package: StoredTemplatePackage | None
    template_operations: list[ImportOperation]

    @model_validator(mode='after')
    def captured_integrity(self):
        from ..template_identity import source_slice
        from ..templates.compiler import canonical, sha256
        from ..templates.projection import reachable_schema, schema_at
        _unique([(source.id, source.revision) for source in self.sources], 'pre-draft source revision')
        for source in self.sources:
            _unique([(unit.id, unit.revision) for unit in source.units], 'pre-draft source unit revision')
        if self.selected_source_id is not None and self.selected_source_id not in {source.id for source in self.sources}:
            raise ValueError('pre-draft selected source missing')
        _unique([operation.id for operation in self.template_operations], 'pre-draft operation')
        if self.template_package is None:
            if (self.template_operations or self.facts.extensions or self.facts.observations or self.facts.relations
                    or self.facts.manual_scopes or self.facts.builtin_identities or self.facts.builtin_manual_scopes):
                raise ValueError('template state requires a captured package')
            return self
        verify_package(self.template_package)
        schemas = {declaration.id: reachable_schema(declaration.data_schema, self.template_package.definition.content_definitions)
            for declaration in self.template_package.definition.fact_types}
        receipts = [receipt.id for operation in self.template_operations for receipt in operation.receipts]
        _unique(receipts, 'pre-draft review receipt')
        for record in self.facts.extensions:
            schema = schemas.get(record.semantic_type)
            if schema is None or record.semantic_schema_hash != sha256(canonical(schema)):
                raise ValueError('pre-draft semantic schema identity mismatch')
            for field in record.retired_cell_ids:
                schema_at(schema, '/' + field.replace('.', '/'))
            for cell in record.cells:
                schema_at(schema, '/' + cell.field_key.replace('.', '/'))
                if not set(cell.admission_receipt_ids) <= set(receipts):
                    raise ValueError('pre-draft admission receipt missing')
                for span in cell.evidence:
                    source_slice(self.sources, span)
        for observation in self.facts.observations:
            if not set(observation.receipt_ids) <= set(receipts):
                raise ValueError('pre-draft observation receipt missing')
            for span in observation.evidence:
                source_slice(self.sources, span)
        if any(operation.capture.package_hash != self.template_package.package_hash for operation in self.template_operations):
            raise ValueError('pre-draft operation/package mismatch')
        return self


class WorkspaceV7(WorkspaceV6):
    schema_version: Literal[7]
    project: ProjectV6 | None
    pre_draft: RichPreDraftV2 | None
    sync_records: list[TemplateSyncRecord | RichSyncRecord]

    @model_validator(mode='after')
    def operation_owner(self):
        owner = self.project or self.pre_draft
        if any(operation.project_id != self.project_id for operation in owner.template_operations):
            raise ValueError('workspace template operation belongs to another project')
        from ..template_identity import source_slice
        for operation in owner.template_operations:
            for result in operation.task_results:
                for span in result.source_spans:
                    source_slice(owner.sources, span)
        return self


class TemplateArchiveEntry(Wire):
    path: str
    role: Literal['workspace','source_original','render','user_image','template_package','template_asset','template_history']
    sha256: Sha256
    size: int = Field(ge=0,le=PROJECT_CEILING_BYTES)

    @model_validator(mode="after")
    def path_role(self):
        if not _safe_path(self.path): raise ValueError('unsafe archive path')
        # Only the project file grows with the project size setting.
        if self.role!='workspace' and self.size>ARCHIVE_ENTRY_BYTES: raise ValueError('archive entry exceeds 32 MiB')
        required={'workspace':'workspace.json','template_package':'template/package.json'}
        if self.role in required and self.path!=required[self.role]: raise ValueError('invalid archive role path')
        prefix={'source_original':'sources/','render':'renders/','user_image':'images/','template_asset':'template/assets/',
            'template_history':'template/history/'}
        if self.role in prefix and not self.path.startswith(prefix[self.role]): raise ValueError('invalid archive role path')
        return self


class ArchiveManifestV7(Wire):
    # The client reads the ZIP ceiling from the generated schema instead of restating it.
    model_config = ConfigDict(json_schema_extra={'x-maxArchiveBytes': ARCHIVE_BYTES})
    schema_version: Literal[7]
    app_version: str
    project_id: Id
    entries: list[TemplateArchiveEntry] = Field(min_length=1,max_length=47)

    @model_validator(mode="after")
    def payload(self):
        _unique([entry.path.casefold() for entry in self.entries],'archive path')
        if sum(entry.role=='workspace' for entry in self.entries)!=1: raise ValueError('one workspace required')
        if sum(entry.role=='template_package' for entry in self.entries)>1: raise ValueError('one captured package allowed')
        if sum(entry.role=='render' for entry in self.entries)>1: raise ValueError('one optional render allowed')
        if sum(entry.size for entry in self.entries)>ARCHIVE_EXPANDED_BYTES: raise ValueError('expanded archive exceeds limit')
        return self
