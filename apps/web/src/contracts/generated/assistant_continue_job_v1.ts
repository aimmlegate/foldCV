export type Contentsha256 = string;
export type Proposalid = string;
export type Protocolversion = 1;
export type Schemaversion = 1;
export type Version = number;
export type Protocolversion1 = 1;
export type Lineage = string;
export type Allowedits = boolean;
export type Allowweb = boolean;
export type Clientrequestid = string;
export type Conversationid = string;
export type Documentrevision = number;
export type Factsrevision = number;
export type Message = string;
export type Projectrevision = number;
export type Scope = WholeResumeScope | SelectionScope;
export type Kind = "resume";
export type Kind1 = "selection";
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
export type Fingerprint = string | null;
export type Id = string;
export type Kind2 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Kind3 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Settingsrevision = number;
export type Requestepoch = number;
export type Schemaversion1 = 1;
export type Schemaversion2 = 1;

export interface AssistantContinueJobV1 {
  proposal: AssistantProposalRequestV1;
  protocolVersion: Protocolversion1;
  request: JobAgentRequestV1;
  schemaVersion?: Schemaversion2;
}
export interface AssistantProposalRequestV1 {
  contentSha256: Contentsha256;
  proposalId: Proposalid;
  protocolVersion: Protocolversion;
  schemaVersion?: Schemaversion;
  version: Version;
}
export interface JobAgentRequestV1 {
  lineage: Lineage;
  request: AgentJournalRequest;
  requestEpoch: Requestepoch;
  schemaVersion: Schemaversion1;
}
export interface AgentJournalRequest {
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  clientRequestId: Clientrequestid;
  conversationId: Conversationid;
  documentRevision: Documentrevision;
  factsRevision: Factsrevision;
  message: Message;
  projectRevision: Projectrevision;
  scope: Scope;
  selectionContext?: RichSelection | null;
  settingsRevision: Settingsrevision;
}
export interface WholeResumeScope {
  kind: Kind;
}
export interface SelectionScope {
  kind: Kind1;
  selection: RichSelection;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind3;
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
  fingerprint: Fingerprint;
  id: Id;
  kind: Kind2;
  revision: Revision;
}
