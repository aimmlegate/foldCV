export type Clientcaptureid = string;
export type Editortoken = string;
export type Selection = ClipboardRangeSelection | ClipboardBlocksSelection;
export type Kind = "range";
export type Beforerevision = number;
export type Blockid = string;
export type Cellid = string | null;
export type End = number;
export type Field = "content" | "caption";
export type Insertiontarget = (FieldInsertionTarget | LiteralInsertionTarget | ManualScopeInsertionTarget) | null;
export type Bindingid = string;
export type Kind1 = "field";
export type Kind2 = "literal";
export type Fragmentid = string;
export type Kind3 = "manual_scope";
export type Start = number;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Blocks = [BlockTarget, ...BlockTarget[]];
export type Beforerevision1 = number;
export type Blockid1 = string;
export type Kind4 = "blocks";
export type Documenthash = string;
export type Documentrevision = number;
export type Factshash = string;
export type Packagehash = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;

export interface ClipboardCaptureRequestV1 {
  clientCaptureId: Clientcaptureid;
  editorToken: Editortoken;
  selection: Selection;
  snapshot: TemplateSnapshotIdentity;
}
export interface ClipboardRangeSelection {
  kind: Kind;
  range: AuthoredRange;
}
export interface AuthoredRange {
  beforeRevision: Beforerevision;
  blockId: Blockid;
  cellId: Cellid;
  end: End;
  field: Field;
  insertionTarget?: Insertiontarget;
  start: Start;
}
export interface FieldInsertionTarget {
  bindingId: Bindingid;
  kind: Kind1;
}
export interface LiteralInsertionTarget {
  kind: Kind2;
}
export interface ManualScopeInsertionTarget {
  fragmentId: Fragmentid;
  kind: Kind3;
}
export interface ClipboardBlocksSelection {
  blocks: Blocks;
  kind: Kind4;
}
export interface BlockTarget {
  beforeRevision: Beforerevision1;
  blockId: Blockid1;
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
