export type Batchid = string;
export type Clientmutationid = string;
export type Disposition =
  | "prepared"
  | "offered"
  | "applying"
  | "saved"
  | "stale"
  | "rejected"
  | "cancelled"
  | "save_failed"
  | "outcome_unknown";
export type Documentrevision = number | null;
export type Durable = boolean;
export type Code =
  | "AGENT_DISABLED"
  | "AGENT_MODEL_REQUIRED"
  | "AGENT_MODEL_UNAVAILABLE"
  | "AGENT_MODEL_INCOMPATIBLE"
  | "AGENT_SETTINGS_CONFLICT"
  | "AGENT_SETTINGS_CORRUPT"
  | "AGENT_SETTINGS_SAVE_FAILED"
  | "AGENT_CONNECTION_UNAVAILABLE"
  | "AGENT_CONNECTION_CHANGED"
  | "AGENT_AUTH_REQUIRED"
  | "AGENT_QUOTA"
  | "AGENT_BUSY"
  | "AGENT_CANCELLED"
  | "AGENT_INTERRUPTED"
  | "AGENT_DEADLINE"
  | "AGENT_STARTUP_TIMEOUT"
  | "AGENT_PROTOCOL"
  | "AGENT_PROCESS_FAILED"
  | "AGENT_CLEANUP_FAILED"
  | "AGENT_RUNTIME_UNSUPPORTED"
  | "AGENT_MODEL_REROUTED"
  | "AGENT_UNEXPECTED_COMPACTION"
  | "AGENT_TOOL_DENIED"
  | "AGENT_TOOL_LIMIT"
  | "AGENT_OUTPUT_LIMIT"
  | "AGENT_CONTEXT_LIMIT"
  | "AGENT_ARGUMENT_INVALID"
  | "AGENT_WEB_DISABLED"
  | "AGENT_SOURCE_UNAVAILABLE"
  | "AGENT_SOURCE_DENIED"
  | "AGENT_SOURCE_LIMIT"
  | "AGENT_SCOPE_INVALID"
  | "AGENT_STALE_READ"
  | "AGENT_EDIT_INVALID"
  | "AGENT_EDIT_LIMIT"
  | "AGENT_EVIDENCE_INVALID"
  | "AGENT_NO_OWNER"
  | "AGENT_LEASE_EXPIRED"
  | "AGENT_OWNER_MISMATCH"
  | "AGENT_TICKET_INVALID"
  | "AGENT_RECEIPT_TIMEOUT"
  | "AGENT_SAVE_FAILED"
  | "AGENT_OUTCOME_UNKNOWN"
  | "AGENT_IDEMPOTENCY_CONFLICT"
  | "AGENT_NOT_FOUND"
  | "AGENT_CONVERSATION_FULL"
  | "AGENT_PROJECT_FULL"
  | "AGENT_STORE_CORRUPT"
  | "AGENT_STORE_UNAVAILABLE"
  | "AGENT_STORE_SAVE_FAILED"
  | "AGENT_PROJECT_DELETED"
  | "AGENT_CLEANUP_INCOMPLETE"
  | "AGENT_RESYNC_REQUIRED";
export type Factsrevision = number | null;
export type Projectrevision = number | null;
export type Requestsha256 = string;
export type Runid = string;
export type Toolkey = string;
/**
 * @maxItems 100
 */
export type Receipts = AgentEditReceipt[];
export type Accessrevision = number;
export type Allowedits = boolean;
export type Allowweb = boolean;
export type Clientrequestid = string;
export type Connectionepoch = string;
export type Conversationid = string;
export type Createdat = string;
export type Deadline = string;
export type Finishedat = string | null;
export type Id = string;
export type Model = string;
export type Outcomeunknown = boolean;
export type Ownerepoch = number;
export type Projectid = string;
export type Savedbatchid = string | null;
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
export type Id1 = string;
export type Kind2 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Kind3 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Settingsrevision = number;
export type State =
  "queued" | "running" | "waiting_for_editor" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Cachedinputtokens = number;
export type Inputtokens = number;
export type Outputtokens = number;
export type Totaltokens = number;

export interface AgentRunRead {
  receipts: Receipts;
  run: AgentRun;
}
export interface AgentEditReceipt {
  batchId: Batchid;
  clientMutationId: Clientmutationid;
  disposition: Disposition;
  documentRevision: Documentrevision;
  durable: Durable;
  error: AgentError | null;
  factsRevision: Factsrevision;
  projectRevision: Projectrevision;
  requestSha256: Requestsha256;
  runId: Runid;
  toolKey: Toolkey;
}
export interface AgentError {
  code: Code;
}
export interface AgentRun {
  accessRevision?: Accessrevision;
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  clientRequestId: Clientrequestid;
  connectionEpoch: Connectionepoch;
  conversationId: Conversationid;
  createdAt: Createdat;
  deadline: Deadline;
  error: AgentError | null;
  finishedAt: Finishedat;
  id: Id;
  model: Model;
  outcomeUnknown: Outcomeunknown;
  ownerEpoch: Ownerepoch;
  projectId: Projectid;
  savedBatchId: Savedbatchid;
  scope: Scope;
  selectionContext?: RichSelection | null;
  settingsRevision: Settingsrevision;
  state: State;
  usage: AgentUsage | null;
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
  id: Id1;
  kind: Kind2;
  revision: Revision;
}
export interface AgentUsage {
  cachedInputTokens: Cachedinputtokens;
  inputTokens: Inputtokens;
  outputTokens: Outputtokens;
  totalTokens: Totaltokens;
}
