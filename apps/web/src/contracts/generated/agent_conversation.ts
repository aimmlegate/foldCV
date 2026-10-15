export type Createdat = string;
/**
 * @maxItems 20
 */
export type Anchors =
  | []
  | [AgentAnchor]
  | [AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ];
export type Blockid = string | null;
export type Cellid = string | null;
export type Fingerprint = string | null;
export type Id = string;
export type Kind =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
/**
 * @maxItems 100
 */
export type Dependencies = DependencyStamp[];
export type End = number | null;
export type Fieldkey = string | null;
export type Recordid = string | null;
export type Start = number | null;
export type Text = string;
export type Id1 = string;
export type Message = string;
export type Runid = string;
export type Severity = "info" | "warning" | "error";
/**
 * @maxItems 20
 */
export type Sourceids =
  | []
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ];
export type Findings = AgentFinding[];
export type Id2 = string;
export type AgentMessage = {
  [k: string]: unknown;
};
/**
 * @maxItems 200
 */
export type Messages = AgentMessage[];
export type Projectid = string;
export type Allowedits = boolean;
export type Allowweb = boolean;
export type Clientrequestid = string;
export type Connectionepoch = string;
export type Conversationid = string;
export type Createdat1 = string;
export type Deadline = string;
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
export type Finishedat = string | null;
export type Id3 = string;
export type Model = string;
export type Outcomeunknown = boolean;
export type Ownerepoch = number;
export type Projectid1 = string;
export type Savedbatchid = string | null;
export type Scope = WholeResumeScope | SelectionScope;
export type Kind1 = "resume";
export type Kind2 = "selection";
export type Blockid1 = string;
export type Cellid1 = string | null;
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
export type Dependencies1 = DependencyStamp[];
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
export type Runs = AgentRun[];
export type Schemaversion = 1;
export type Contentsha256 = string;
export type Finalurl = string;
export type Id4 = string;
export type Originalbytes = number;
export type Requestedurl = string;
export type Retrievedat = string;
export type Runid1 = string;
export type Text1 = string;
export type Title = string;
export type Truncated = boolean;
export type Sources = AgentWebSource[];
export type Updatedat = string;

export interface AgentConversation {
  createdAt: Createdat;
  findings: Findings;
  id: Id2;
  messages: Messages;
  projectId: Projectid;
  runs: Runs;
  schemaVersion: Schemaversion;
  sources: Sources;
  updatedAt: Updatedat;
}
export interface AgentFinding {
  anchors: Anchors;
  id: Id1;
  message: Message;
  runId: Runid;
  severity: Severity;
  sourceIds: Sourceids;
}
export interface AgentAnchor {
  blockId: Blockid;
  cellId: Cellid;
  dependencies: Dependencies;
  end: End;
  fieldKey: Fieldkey;
  recordId: Recordid;
  start: Start;
  text: Text;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id;
  kind: Kind;
  revision: Revision;
}
export interface AgentRun {
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  clientRequestId: Clientrequestid;
  connectionEpoch: Connectionepoch;
  conversationId: Conversationid;
  createdAt: Createdat1;
  deadline: Deadline;
  error: AgentError | null;
  finishedAt: Finishedat;
  id: Id3;
  model: Model;
  outcomeUnknown: Outcomeunknown;
  ownerEpoch: Ownerepoch;
  projectId: Projectid1;
  savedBatchId: Savedbatchid;
  scope: Scope;
  settingsRevision: Settingsrevision;
  state: State;
  usage: AgentUsage | null;
}
export interface AgentError {
  code: Code;
}
export interface WholeResumeScope {
  kind: Kind1;
}
export interface SelectionScope {
  kind: Kind2;
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
  blockId: Blockid1;
  cellId: Cellid1;
  offset: Offset;
}
export interface ActionCapture {
  actionId: Actionid;
  actionToken: Actiontoken;
  dependencies: Dependencies1;
  sessionId: Sessionid;
}
export interface AgentUsage {
  cachedInputTokens: Cachedinputtokens;
  inputTokens: Inputtokens;
  outputTokens: Outputtokens;
  totalTokens: Totaltokens;
}
export interface AgentWebSource {
  contentSha256: Contentsha256;
  finalUrl: Finalurl;
  id: Id4;
  originalBytes: Originalbytes;
  requestedUrl: Requestedurl;
  retrievedAt: Retrievedat;
  runId: Runid1;
  text: Text1;
  title: Title;
  truncated: Truncated;
}
