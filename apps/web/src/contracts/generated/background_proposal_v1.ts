export type Acceptedat = string;
export type Accountgeneration = number;
export type Authority = "active" | "revoked";
export type Executiondeadline = string;
export type Executiongeneration = number;
export type Fingerprint = string;
export type Generation = number;
export type Key = string;
export type Kind = "entity" | "structure" | "query" | "source" | "rules";
/**
 * @maxItems 100
 */
export type Reads = GenerationStamp[];
export type Schemaversion = 1;
/**
 * @maxItems 100
 */
export type Writes = GenerationStamp[];
export type Id = string;
export type Jobid = string;
export type Lineage = string;
export type Payload = AgentPayloadReference | FixedPayloadReference | ProcessingPayloadReference;
export type Batchid = string;
export type Conversationid = string;
export type Kind1 = "agent_journal";
export type Runid = string;
export type Kind2 = "rich_sync";
export type Syncid = string;
export type Candidateid = string;
export type Kind3 = "processing";
export type Payloadbytes = number;
export type Payloadsha256 = string;
export type Projectid = string;
export type Revocation = ("stop" | "discard" | "superseded" | "deleted" | "account_changed") | null;
export type Schemaversion1 = 1;
export type Scope = WholeResumeScope | SelectionScope;
export type Kind4 = "resume";
export type Kind5 = "selection";
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
export type Kind6 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Kind7 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Turnid = string;

export interface ProposalBindingV1 {
  acceptedAt: Acceptedat;
  accountGeneration: Accountgeneration;
  authority: Authority;
  executionDeadline: Executiondeadline;
  executionGeneration: Executiongeneration;
  guards: ScopeGuardV1;
  id: Id;
  jobId: Jobid;
  lineage: Lineage;
  payload: Payload;
  payloadBytes: Payloadbytes;
  payloadSha256: Payloadsha256;
  projectId: Projectid;
  revocation: Revocation;
  schemaVersion: Schemaversion1;
  scope: Scope;
  turnId: Turnid;
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
export interface AgentPayloadReference {
  batchId: Batchid;
  conversationId: Conversationid;
  kind: Kind1;
  runId: Runid;
}
export interface FixedPayloadReference {
  kind: Kind2;
  syncId: Syncid;
}
export interface ProcessingPayloadReference {
  candidateId: Candidateid;
  kind: Kind3;
}
export interface WholeResumeScope {
  kind: Kind4;
}
export interface SelectionScope {
  kind: Kind5;
  selection: RichSelection;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind7;
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
  kind: Kind6;
  revision: Revision;
}
