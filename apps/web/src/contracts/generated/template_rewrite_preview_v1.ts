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
export type Schemaversion = 1;
export type Documenthash = string;
export type Documentrevision = number;
export type Factshash = string;
export type Packagehash = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;
export type Source = string;
export type Text = string;

/**
 * A rewrite preview: the selected source and the model's text; the document changes only through Apply.
 */
export interface TemplateRewritePreviewV1 {
  range: AuthoredRange;
  requestId: Requestid;
  schemaVersion: Schemaversion;
  snapshot: TemplateSnapshotIdentity;
  source: Source;
  text: Text;
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
