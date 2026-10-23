export type Documenthash = string;
export type Documentrevision = number;
export type Factshash = string;
export type Packagehash = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;
export type Baseworkspacesha256 = string;
export type Actionid = string;
export type Actiontoken = number;
export type Fingerprint = string | null;
export type Id = string;
export type Kind =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Clientmutationid = string;
export type Mutationwire = string | null;
export type Afterhash = string;
export type Beforehash = string;
export type Afterhash1 = string;
export type Beforehash1 = string;
export type Kind1 = "set";
export type Pointer = string;
export type Valuewire = string;
export type Kind2 = "insert";
export type Pointer1 = string;
export type Valuewire1 = string;
export type Kind3 = "remove";
export type Pointer2 = string;
export type Beforetexthash = string;
export type End = number;
export type Kind4 = "splice_text";
export type Pointer3 = string;
export type Start = number;
export type Text = string;
/**
 * @maxItems 1000
 */
export type Steps = (PatchSet | PatchInsert | PatchRemove | PatchSpliceText)[];
export type Remove = string[];
export type Itemhandle = string | null;
export type Nodeindex = number | null;
export type Alignment = ("left" | "center" | "right" | "justify") | null;
export type Bold = boolean | null;
export type Color = string | null;
export type Font = string | null;
export type Italic = boolean | null;
export type Size = number | null;
export type Packagehash1 = string;
export type Styletoken = string;
export type Templateinstanceid = string | null;
export type Viewkey = string;
export type Requesthash = string;
export type Errorcode = string | null;
export type Id1 = string;
export type Stage = "assess_resume" | "normalize_semantics" | "draft_prose" | "assemble" | "render";
export type Startedat = string | null;
export type Status = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Subtitle = string;
export type Title = string;
export type Resultworkspacesha256 = string;
export type Schemaversion = 1;
/**
 * @maxItems 1000
 */
export type Workspacepatch = (PatchSet | PatchInsert | PatchRemove | PatchSpliceText)[];

export interface TemplatePreparedEditDeltaV1 {
  baseSnapshot: TemplateSnapshotIdentity;
  baseWorkspaceSha256: Baseworkspacesha256;
  capture: ActionCapture;
  clientMutationId: Clientmutationid;
  createdIds: Createdids;
  mutationWire: Mutationwire;
  presentationPatch: PresentationPatchV1;
  requestHash: Requesthash;
  resultGeneration: RichGenerationState | null;
  resultIdentity: ResumeIdentity | null;
  resultSnapshot: TemplateSnapshotIdentity;
  resultWorkspaceSha256: Resultworkspacesha256;
  schemaVersion: Schemaversion;
  workspacePatch: Workspacepatch;
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
export interface ActionCapture {
  actionId: Actionid;
  actionToken: Actiontoken;
  dependencies: Dependencies;
  sessionId: Sessionid;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id;
  kind: Kind;
  revision: Revision;
}
export interface Createdids {
  [k: string]: {
    [k: string]: string;
  };
}
export interface PresentationPatchV1 {
  afterHash: Afterhash;
  beforeHash: Beforehash;
  editor?: EditorPlanPatchV1 | null;
  remove: Remove;
  set: Set;
}
/**
 * The editor plan changes with the document; its patch is checked by hashes of the exact plans.
 */
export interface EditorPlanPatchV1 {
  afterHash: Afterhash1;
  beforeHash: Beforehash1;
  steps: Steps;
}
export interface PatchSet {
  kind: Kind1;
  pointer: Pointer;
  valueWire: Valuewire;
}
export interface PatchInsert {
  kind: Kind2;
  pointer: Pointer1;
  valueWire: Valuewire1;
}
export interface PatchRemove {
  kind: Kind3;
  pointer: Pointer2;
}
export interface PatchSpliceText {
  beforeTextHash: Beforetexthash;
  end: End;
  kind: Kind4;
  pointer: Pointer3;
  start: Start;
  text: Text;
}
export interface Set {
  [k: string]: AuthoredPresentation;
}
export interface AuthoredPresentation {
  itemHandle: Itemhandle;
  nodeIndex?: Nodeindex;
  overrides: StyleOverrides;
  packageHash: Packagehash1;
  styleToken: Styletoken;
  templateInstanceId: Templateinstanceid;
  viewKey: Viewkey;
}
export interface StyleOverrides {
  alignment: Alignment;
  bold: Bold;
  color: Color;
  font: Font;
  italic: Italic;
  size: Size;
}
export interface RichGenerationState {
  errorCode: Errorcode;
  id: Id1;
  stage: Stage;
  startedAt?: Startedat;
  status: Status;
}
export interface ResumeIdentity {
  subtitle: Subtitle;
  title: Title;
}
