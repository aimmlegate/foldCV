"""Generic semantic cells retain observations separately from working authority."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from .contracts import Id, Revision, Sha256, Wire, _unique
from .rich_facts import WorkingFacts


class SourceSpan(Wire):
    source_id: Id
    source_revision: Revision
    unit_id: Id
    unit_revision: Revision
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    slice_hash: Sha256

    @model_validator(mode="after")
    def half_open(self):
        if self.end < self.start: raise ValueError("source span ends before its start")
        return self


class Relation(Wire):
    id: Id
    kind: Literal["owned_by", "extension_of", "related_to"]
    subject_id: Id
    target_id: Id
    revision: Revision
    active: bool


class Observation(Wire):
    id: Id
    item_handle: Id
    field_key: Id
    raw_input: str
    typed_value: JsonValue
    evidence: list[SourceSpan]
    owner_relations: list[Relation]
    proposal_hash: Sha256
    admission: Literal["provisional", "accepted", "rejected", "uncertain"]
    receipt_ids: list[Id]


class ExtensionCell(Wire):
    id: Id
    field_key: Id
    revision: Revision
    raw_input: str
    typed_value: JsonValue
    state: Literal["admitted", "human_raw", "pending_manual", "uncertain"]
    origin: Literal["model", "source", "human"]
    user_corrected: bool
    evidence: list[SourceSpan]
    observation_ids: list[Id]
    admission_receipt_ids: list[Id]
    manual_scope_id: Id | None

    @property
    def raw_text(self):
        return self.raw_input

    @model_validator(mode="after")
    def authority(self):
        if self.state in {"human_raw", "pending_manual", "uncertain"} and self.typed_value is not None:
            raise ValueError("raw/pending/uncertain cell cannot claim a current typed value")
        if self.state in {"human_raw", "pending_manual"} and (self.origin != "human" or not self.user_corrected):
            raise ValueError("human cells require human correction authority")
        if (self.state == "pending_manual") != (self.manual_scope_id is not None):
            raise ValueError("pending manual cell requires its exact edit scope")
        if self.state == "admitted" and self.origin == "model" and not self.admission_receipt_ids:
            raise ValueError("model cell requires admission receipts")
        return self


class ExtensionRecord(Wire):
    schema_version: Literal[1]
    id: Id
    item_handle: Id
    revision: Revision
    semantic_type: Id
    semantic_schema_hash: Sha256
    cells: list[ExtensionCell]
    relations: list[Relation]
    observation_ids: list[Id]
    active: bool
    copy_of_record_id: Id | None = Field(default=None, exclude_if=lambda value: value is None)
    # Removed cells keep their identities for historical scopes and Redo, without current values.
    retired_cell_ids: dict[Id, Id] = Field(default_factory=dict, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def identity(self):
        _unique([cell.id for cell in self.cells] + list(self.retired_cell_ids.values()), "extension cell")
        _unique([cell.field_key for cell in self.cells] + list(self.retired_cell_ids), "extension field")
        _unique([relation.id for relation in self.relations], "extension relation")
        if any(cell.revision > self.revision for cell in self.cells):
            raise ValueError("cell revision exceeds record")
        return self


class ManualEditScope(Wire):
    id: Id
    action_id: Id
    raw_input: str
    cell_ids: list[Id]
    block_ids: list[Id]


class EffectiveExtensionValue(Wire):
    record_id: Id
    semantic_type: Id
    cell: ExtensionCell
    manual_scope: ManualEditScope | None


class CanonicalFieldBinding(Wire):
    field_key: Id
    cell_id: Id
    period_id: Id | None


class CanonicalItemIdentity(Wire):
    semantic_type: Id
    item_handle: Id
    record_id: Id
    cell_ids: dict[str, Id]
    period_ids: dict[str, Id] = Field(default_factory=dict, exclude_if=lambda value: not value)
    canonical_fields: dict[str, CanonicalFieldBinding] = Field(default_factory=dict, exclude_if=lambda value: not value)

    @model_validator(mode='after')
    def canonical_identity(self):
        _unique(list(self.cell_ids.values()), 'allocated cell')
        if not self.canonical_fields and not self.period_ids:
            return self
        from ..rich_fields import field_key
        if set(self.canonical_fields) != set(self.cell_ids):
            raise ValueError('canonical field map must cover every allocated builtin cell')
        for key, value in self.canonical_fields.items():
            if value.cell_id != self.cell_ids[key] or value.cell_id != field_key(self.record_id, value.field_key):
                raise ValueError('canonical cell identity mismatch')
            if value.period_id is not None and (value.period_id not in self.period_ids.values()
                    or value.field_key not in {'period:' + value.period_id + ':' + name for name in ['start', 'end', 'present']}):
                raise ValueError('canonical period identity mismatch')
            if value.period_id is None and value.field_key.startswith('period:'):
                raise ValueError('canonical period field needs its allocated period')
        if len(set(self.period_ids.values())) != len(self.period_ids):
            raise ValueError('duplicate allocated period identity')
        if set(self.period_ids.values()) != {value.period_id for value in self.canonical_fields.values()
                if value.period_id is not None}:
            raise ValueError('unused allocated period identity')
        return self


class BuiltinItemIdentity(CanonicalItemIdentity):
    semantic_schema_hash: Sha256


class CapturedItemIdentity(BuiltinItemIdentity):
    record_revision: Revision


class HandleAllocation(CanonicalItemIdentity):
    operation_id: Id
    task_id: Id
    discovery_attempt_id: Id
    key: Id
    discovery_hash: Sha256


class Lineage(Wire):
    kind: Literal["add", "split", "merge"]
    parents: list[Id]
    children: list[Id]
    attempt_id: Id


class WorkingFactsV2(WorkingFacts):
    schema_version: Literal[2]
    extensions: list[ExtensionRecord]
    observations: list[Observation]
    relations: list[Relation]
    manual_scopes: list[ManualEditScope]
    builtin_manual_scopes: dict[str, Id] = Field(default_factory=dict, exclude_if=lambda value: not value)
    builtin_identities: list[BuiltinItemIdentity] = Field(default_factory=list, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def generic_identity(self):
        from ..rich_fields import builtin_cell_values, field_key, working_field
        builtin_cells = builtin_cell_values(self.records)
        _unique([r.id for r in self.extensions], "extension record")
        _unique([r.item_handle for r in self.extensions], "extension item handle")
        retained_cells = [identifier for record in self.extensions for identifier in record.retired_cell_ids.values()]
        _unique([c.id for r in self.extensions for c in r.cells] + retained_cells, "extension cell")
        _unique([o.id for o in self.observations], "observation")
        _unique([r.id for r in self.relations], "effective relation")
        _unique([s.id for s in self.manual_scopes], "manual scope")
        _unique([value.record_id for value in self.builtin_identities], 'builtin record identity')
        _unique([value.item_handle for value in self.builtin_identities], 'builtin item handle')
        reserved_periods = [period for value in self.builtin_identities for period in value.period_ids.values()]
        _unique(reserved_periods, 'builtin allocated period')
        _unique([r.id for r in self.records] + [r.id for r in self.extensions]
                + [r.item_handle for r in self.extensions] + [c.id for r in self.extensions for c in r.cells]
                + retained_cells + list(builtin_cells) + [value.item_handle for value in self.builtin_identities]
                + sorted(set(reserved_periods) | {period.id for record in self.records for period in getattr(record, 'periods', [])}),
                "persistent semantic identity")
        removed = {t.record_id for t in self.tombstones}
        builtins = {r.id for r in self.records}
        extensions = {r.id for r in self.extensions}
        if builtins & extensions: raise ValueError("built-in/extension identity collision")
        current = builtins | {r.id for r in self.extensions if r.active}
        if current & {t.record_id for t in self.tombstones}:
            raise ValueError("tombstoned extension cannot remain active")
        observations = {o.id for o in self.observations}
        scopes = {s.id:s for s in self.manual_scopes}
        relations = {r.id:r for r in self.relations}
        extension_records = {record.id: record for record in self.extensions}
        cells = {c.id for r in self.extensions for c in r.cells} | set(retained_cells)
        builtin_records = {record.id: record for record in self.records}
        period_owners = {period.id: record.id for record in self.records for period in getattr(record, 'periods', [])}
        for identity in self.builtin_identities:
            if identity.record_id not in builtins | (removed - extensions) or not identity.canonical_fields:
                raise ValueError('builtin identity needs a retained builtin record and canonical map')
            if any(period in period_owners and period_owners[period] != identity.record_id
                    for period in identity.period_ids.values()):
                raise ValueError('builtin identity references another record period')
        def historical_builtin(identifier):
            try:
                parsed = json.loads(identifier)
            except ValueError:
                return False
            if (not isinstance(parsed, list) or len(parsed) != 3 or parsed[0] != 'fact'
                    or not all(isinstance(value, str) and value for value in parsed[1:])):
                return False
            record_id, key = parsed[1:]
            if identifier != field_key(record_id, key):
                return False
            record = builtin_records.get(record_id)
            period, _separator, part = key.removeprefix('period:').rpartition(':')
            period_key = key.startswith('period:') and bool(period) and part in {'start', 'end', 'present'}
            if record is not None:
                return working_field(record, key) is not None or period_key and hasattr(record, 'periods')
            return record_id in removed - extensions and (period_key or key in {
                'name', 'title', 'location', 'value', 'employer', 'role', 'display', 'canonicalId', 'experience',
                'institution', 'qualification', 'specialty', 'completion', 'language', 'level', 'issuer', 'date'})
        for scope in self.manual_scopes:
            _unique(scope.cell_ids, 'manual scope cell')
            if not scope.cell_ids or any(identifier not in cells and not historical_builtin(identifier) for identifier in scope.cell_ids):
                raise ValueError('manual scope references missing cells')
        for identifier, scope_id in self.builtin_manual_scopes.items():
            scope, current_cell = scopes.get(scope_id), builtin_cells.get(identifier)
            if current_cell is None or scope is None or identifier not in scope.cell_ids:
                raise ValueError('builtin manual scope references a missing current field or scope')
            value = current_cell[2]
            if (value.status != 'pending' or value.value is not None or not value.user_corrected
                    or value.pending_raw_text != scope.raw_input):
                raise ValueError('builtin manual scope must preserve exact pending human text without a typed assertion')
        for record in self.extensions:
            if record.copy_of_record_id is not None and (
                    record.copy_of_record_id == record.id or record.copy_of_record_id not in extensions):
                raise ValueError('invalid entity copy lineage')
            ancestor = record
            copied = set()
            while ancestor.copy_of_record_id is not None:
                if ancestor.id in copied:
                    raise ValueError('cyclic entity copy lineage')
                copied.add(ancestor.id)
                parent = extension_records.get(ancestor.copy_of_record_id)
                if parent is None:
                    raise ValueError('invalid entity copy lineage')
                if (parent.semantic_type, parent.semantic_schema_hash) != (ancestor.semantic_type, ancestor.semantic_schema_hash):
                    raise ValueError('incompatible entity copy lineage')
                ancestor = parent
            if not set(record.observation_ids) <= observations: raise ValueError("missing retained observation")
            for cell in record.cells:
                if not set(cell.observation_ids) <= observations: raise ValueError("missing cell observation")
                if cell.manual_scope_id is not None:
                    scope = scopes.get(cell.manual_scope_id)
                    if scope is None or cell.id not in scope.cell_ids: raise ValueError("missing manual cell scope")
            for relation in record.relations:
                if relation.subject_id != record.id or relations.get(relation.id) != relation:
                    raise ValueError("extension/effective relation mismatch")
            if {r.id for r in record.relations} != {r.id for r in self.relations if r.subject_id == record.id}:
                raise ValueError('extension is missing its retained effective relation')
        for relation in self.relations:
            if relation.subject_id not in builtins | extensions | removed or relation.target_id not in builtins | extensions | removed:
                raise ValueError("relation references an unknown record")
            if relation.active and (relation.subject_id not in current or relation.target_id not in current):
                raise ValueError("active relation references a removed record")
            if relation.active and relation.kind == 'owned_by':
                subject = next((record for record in self.records if record.id == relation.subject_id), None)
                if subject is not None and hasattr(subject, 'job_id'):
                    owner = getattr(subject, 'subproject_id', None) or subject.job_id
                    if relation.target_id != owner:
                        raise ValueError('built-in and effective ownership disagree')
        # Ownership and subject attachment must remain acyclic for atomic deletion.
        edges = {}
        subjects = set()
        for relation in self.relations:
            if relation.active and relation.kind in {"owned_by","extension_of"}:
                key = (relation.subject_id, relation.kind)
                if key in subjects:
                    raise ValueError('multiple effective owners or extension subjects')
                subjects.add(key)
                edges.setdefault(relation.subject_id,[]).append(relation.target_id)
        def visit(record,chain):
            if record in chain: raise ValueError("cyclic effective ownership")
            for owner in edges.get(record,[]): visit(owner,chain|{record})
        for record in edges: visit(record,set())
        return self
