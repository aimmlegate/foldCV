export type Instruction = string;
export type Credential = string;
export type Epoch = number;
export type Incarnation = string;
export type Lineage = string;
export type Schemaversion = 1;
export type Sessionid = string;
export type Beforerevision = number;
export type Blockid = string;
export type Cellid = string | null;
export type End = number;
export type Field = "content" | "caption";
export type Insertiontarget = (FieldInsertionTarget | LiteralInsertionTarget | ManualScopeInsertionTarget) | null;
export type Bindingid = string;
export type Kind = "field";
export type Kind1 = "literal";
export type Fragmentid = string;
export type Kind2 = "manual_scope";
export type Start = number;
export type Requestid = string;
export type Schemaversion1 = 2;
export type Documenthash = string;
export type Documentrevision = number;
export type Factshash = string;
export type Packagehash = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;

/**
 * Selected-text rewrite in one text block or cell; generation never changes the document.
 */
export interface WriterRewritePreviewV2 {
  instruction: Instruction;
  proof: WriterProofV1;
  range: AuthoredRange;
  requestId: Requestid;
  schemaVersion: Schemaversion1;
  snapshot: TemplateSnapshotIdentity;
}
export interface WriterProofV1 {
  credential: Credential;
  epoch: Epoch;
  incarnation: Incarnation;
  lineage: Lineage;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
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
  kind: Kind;
}
export interface LiteralInsertionTarget {
  kind: Kind1;
}
export interface ManualScopeInsertionTarget {
  fragmentId: Fragmentid;
  kind: Kind2;
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
