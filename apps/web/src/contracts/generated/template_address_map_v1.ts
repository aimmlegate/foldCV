export type Documenthash = string;
export type Documentrevision = number;
export type Factshash = string;
export type Packagehash = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;
export type Clientmutationid = string;
export type Aftercontenthash = string;
export type Afterlength = number;
export type Beforecontenthash = string | null;
export type Beforelength = number | null;
export type After = (FieldInsertionTarget | LiteralInsertionTarget | ManualScopeInsertionTarget) | null;
export type Bindingid = string;
export type Kind = "field";
export type Kind1 = "literal";
export type Fragmentid = string;
export type Kind2 = "manual_scope";
export type Before = (FieldInsertionTarget | LiteralInsertionTarget | ManualScopeInsertionTarget) | null;
export type Offset = number;
/**
 * @maxItems 2000
 */
export type Boundaries = AddressBoundaryV1[];
export type Correspondence = "exact" | "none";
export type Opid = string;
export type Slot = string;
export type Input = (TextContainerRef | CellContainerRef) | null;
export type Blockid = string;
export type Kind3 = "content" | "caption";
export type Revision = number;
export type Blockid1 = string;
export type Cellid = string;
export type Cellrevision = number;
export type Kind4 = "cell";
export type Revision1 = number;
export type Output = TextContainerRef | CellContainerRef;
/**
 * @maxItems 3
 */
export type Regions =
  [] | [AddressRegionV1] | [AddressRegionV1, AddressRegionV1] | [AddressRegionV1, AddressRegionV1, AddressRegionV1];
export type End = number;
export type Start = number;
export type Role = "retained_prefix" | "retained_suffix" | "retained" | "restyled" | "inserted";
export type End1 = number;
export type Span = LiteralSpanRef | FieldSpanRef | ScopeSpanRef | BoundTextSpanRef;
export type Kind5 = "literal";
/**
 * @minItems 1
 * @maxItems 2
 */
export type Path = [number] | [number, number];
export type Bindingid1 = string;
export type Cellid1 = string | null;
export type Fieldkey = string;
export type Kind6 = "field";
export type Occurrenceid = string;
export type Recordid = string;
export type Fragmentid1 = string;
export type Kind7 = "manual_scope";
export type Occurrenceid1 = string;
export type Scopeid = string;
export type Binding = "label" | "url";
export type Cellid2 = string;
export type Fieldkey1 = string;
export type Kind8 = "bound_text";
export type Occurrenceid2 = string;
/**
 * @minItems 2
 * @maxItems 2
 */
export type Path1 = [number, number];
export type Recordid1 = string;
export type Start1 = number;
export type Role1 = "retained_prefix" | "retained_suffix" | "retained" | "restyled" | "inserted";
export type Target = (FieldInsertionTarget | LiteralInsertionTarget | ManualScopeInsertionTarget) | null;
/**
 * @maxItems 1000
 */
export type Segments = AddressSegmentV1[];
/**
 * @maxItems 10000
 */
export type Containers = AddressContainerV1[];
export type Requesthash = string;
export type Schemaversion = 1;

export interface PreparedAddressMapV1 {
  baseSnapshot: TemplateSnapshotIdentity;
  clientMutationId: Clientmutationid;
  containers: Containers;
  requestHash: Requesthash;
  resultSnapshot: TemplateSnapshotIdentity;
  schemaVersion: Schemaversion;
}
export interface TemplateSnapshotIdentity {
  documentHash: Documenthash;
  documentRevision: Documentrevision;
  factsHash: Factshash;
  packageHash: Packagehash;
  presentationHash: Presentationhash;
  projectId: Projectid;
  projectRevision: Projectrevision;
}
export interface AddressContainerV1 {
  afterContentHash: Aftercontenthash;
  afterLength: Afterlength;
  beforeContentHash: Beforecontenthash;
  beforeLength: Beforelength;
  boundaries: Boundaries;
  correspondence: Correspondence;
  created: AllocationSlotV1 | null;
  input: Input;
  output: Output;
  regions: Regions;
  segments: Segments;
}
export interface AddressBoundaryV1 {
  after: After;
  before: Before;
  offset: Offset;
}
export interface FieldInsertionTarget {
  bindingId: Bindingid;
  kind: Kind;
}
export interface LiteralInsertionTarget {
  kind: Kind1;
}
export interface ManualScopeInsertionTarget {
  fragmentId: Fragmentid;
  kind: Kind2;
}
export interface AllocationSlotV1 {
  opId: Opid;
  slot: Slot;
}
export interface TextContainerRef {
  blockId: Blockid;
  kind: Kind3;
  revision: Revision;
}
export interface CellContainerRef {
  blockId: Blockid1;
  cellId: Cellid;
  cellRevision: Cellrevision;
  kind: Kind4;
  revision: Revision1;
}
export interface AddressRegionV1 {
  result: AddressInterval;
  role: Role;
  source: AddressInterval | null;
}
export interface AddressInterval {
  end: End;
  start: Start;
}
export interface AddressSegmentV1 {
  result: SpanPieceV1;
  role: Role1;
  slot: AllocationSlotV1 | null;
  source: SpanPieceV1 | null;
  target: Target;
}
export interface SpanPieceV1 {
  end: End1;
  span: Span;
  start: Start1;
}
export interface LiteralSpanRef {
  kind: Kind5;
  path: Path;
}
export interface FieldSpanRef {
  bindingId: Bindingid1;
  cellId: Cellid1;
  fieldKey: Fieldkey;
  kind: Kind6;
  occurrenceId: Occurrenceid;
  recordId: Recordid;
}
export interface ScopeSpanRef {
  fragmentId: Fragmentid1;
  kind: Kind7;
  occurrenceId: Occurrenceid1;
  scopeId: Scopeid;
}
export interface BoundTextSpanRef {
  binding: Binding;
  cellId: Cellid2;
  fieldKey: Fieldkey1;
  kind: Kind8;
  occurrenceId: Occurrenceid2;
  path: Path1;
  recordId: Recordid1;
}
