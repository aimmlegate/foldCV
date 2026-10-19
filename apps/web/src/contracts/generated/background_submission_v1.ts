export type Accessrevision = number;
export type Accountgeneration = number;
export type Allowedits = boolean;
export type Allowweb = boolean;
export type Approvalrequired = boolean;
export type Fingerprint = string;
export type Generation = number;
export type Key = string;
export type Kind = "entity" | "structure" | "query" | "source" | "rules";
/**
 * @maxItems 4096
 */
export type Reads = GenerationStamp[];
export type Schemaversion = 1;
/**
 * @maxItems 4096
 */
export type Writes = GenerationStamp[];
export type Lineage = string;
export type Projectid = string;
export type Requestepoch = number;
export type Requestid = string;
export type Id = string;
export type Kind1 = "agent_journal" | "rich_sync" | "processing";
export type Sha256 = string;
export type Kind2 = "agent" | "processing" | "rewrite" | "reconciliation";
/**
 * @minItems 1
 * @maxItems 2
 */
export type Models = [ModelCapture] | [ModelCapture, ModelCapture];
export type Configsha256 = string;
export type Model = string;
export type Stage = "agent" | "assessment" | "extraction" | "rewrite" | "reconciliation";
export type Payloadsha256 = string;
export type Schedulingclass = "background" | "interactive" | "reconciliation";
export type Schemaversion1 = 1;
export type Scope = WholeResumeScope | SelectionScope;
export type Kind3 = "resume";
export type Kind4 = "selection";
export type Blockid = string;
export type Cellid = string | null;
/**
 * UTF-16 code units within the block or cell.
 */
export type Offset = number;
/**
 * @minItems 1
 */
export type Blockids = [string, ...string[]];
export type Actionid = string;
export type Actiontoken = number;
export type Fingerprint1 = string | null;
export type Id1 = string;
export type Kind5 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Kind6 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Submittedat = string;
/**
 * @maxItems 32
 */
export type Tools = (
  | "get_resume_context"
  | "find_resume_content"
  | "get_working_facts"
  | "get_original_source"
  | "get_conversation_context"
  | "get_project_resources"
  | "check_resume"
  | "read_public_page"
  | "publish_findings"
  | "prepare_edit_batch"
  | "apply_edit_batch"
  | "project_action"
  | "read_import"
  | "save_import"
  | "finish_import"
)[];

export interface JobSubmissionV1 {
  accessRevision?: Accessrevision;
  accountGeneration: Accountgeneration;
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  approvalRequired?: Approvalrequired;
  guards: ScopeGuardV1;
  identity: JobIdentity;
  input: InputReference;
  kind: Kind2;
  models: Models;
  payloadSha256: Payloadsha256;
  schedulingClass: Schedulingclass;
  schemaVersion: Schemaversion1;
  scope: Scope;
  submittedAt: Submittedat;
  tools: Tools;
}
export interface ScopeGuardV1 {
  reads: Reads;
  schemaVersion: Schemaversion;
  writes: Writes;
}
export interface GenerationStamp {
  fingerprint: Fingerprint;
  generation: Generation;
  key: Key;
  kind: Kind;
}
export interface JobIdentity {
  lineage: Lineage;
  projectId: Projectid;
  requestEpoch: Requestepoch;
  requestId: Requestid;
}
export interface InputReference {
  id: Id;
  kind: Kind1;
  sha256: Sha256;
}
export interface ModelCapture {
  configSha256: Configsha256;
  model: Model;
  stage: Stage;
}
export interface WholeResumeScope {
  kind: Kind3;
}
export interface SelectionScope {
  kind: Kind4;
  selection: RichSelection;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind6;
  textSha256: Textsha256;
}
export interface RichPosition {
  blockId: Blockid;
  cellId: Cellid;
  offset: Offset;
}
export interface ActionCapture {
  actionId: Actionid;
  actionToken: Actiontoken;
  dependencies: Dependencies;
  sessionId: Sessionid;
}
export interface DependencyStamp {
  fingerprint: Fingerprint1;
  id: Id1;
  kind: Kind5;
  revision: Revision;
}
