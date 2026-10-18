export type AgentEvent = MessageDelta | ToolEvent | ResourceEvent | EditEvent | UsageEvent | RunStateEvent;
export type Conversationid = string;
export type Id = string;
export type Text = string;
export type Projectid = string;
export type Runid = string;
export type Schemaversion = 1;
export type Sequence = number;
export type Timestamp = string;
export type Type = "message.delta";
export type Conversationid1 = string;
export type Id1 = string;
export type Callid = string;
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
export type Name = string;
export type Projectid1 = string;
export type Runid1 = string;
export type Schemaversion1 = 1;
export type Sequence1 = number;
export type Timestamp1 = string;
export type Type1 = "tool.started" | "tool.completed" | "tool.failed";
export type Conversationid2 = string;
export type Id2 = string;
export type Id3 = string;
export type Projectid2 = string;
export type Runid2 = string;
export type Schemaversion2 = 1;
export type Sequence2 = number;
export type Timestamp2 = string;
export type Type2 = "source.ready" | "finding.ready";
export type Conversationid3 = string;
export type Id4 = string;
export type Batchid = string;
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
export type Projectid3 = string;
export type Runid3 = string;
export type Schemaversion3 = 1;
export type Sequence3 = number;
export type Timestamp3 = string;
export type Type3 = "edit.offered" | "edit.result";
export type Conversationid4 = string;
export type Id5 = string;
export type Cachedinputtokens = number;
export type Inputtokens = number;
export type Outputtokens = number;
export type Totaltokens = number;
export type Projectid4 = string;
export type Runid4 = string;
export type Schemaversion4 = 1;
export type Sequence4 = number;
export type Timestamp4 = string;
export type Type4 = "usage.reported";
export type Conversationid5 = string;
export type Id6 = string;
export type Outcomeunknown = boolean;
export type Savedbatchid = string | null;
export type State =
  "queued" | "running" | "waiting_for_editor" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Projectid5 = string;
export type Runid5 = string;
export type Schemaversion5 = 1;
export type Sequence5 = number;
export type Timestamp5 = string;
export type Type5 = "run.state_changed";

export interface MessageDelta {
  conversationId: Conversationid;
  id: Id;
  payload: MessageDeltaPayload;
  projectId: Projectid;
  runId: Runid;
  schemaVersion: Schemaversion;
  sequence: Sequence;
  timestamp: Timestamp;
  type: Type;
}
export interface MessageDeltaPayload {
  text: Text;
}
export interface ToolEvent {
  conversationId: Conversationid1;
  id: Id1;
  payload: ToolPayload;
  projectId: Projectid1;
  runId: Runid1;
  schemaVersion: Schemaversion1;
  sequence: Sequence1;
  timestamp: Timestamp1;
  type: Type1;
}
export interface ToolPayload {
  callId: Callid;
  error: AgentError | null;
  name: Name;
}
export interface AgentError {
  code: Code;
}
export interface ResourceEvent {
  conversationId: Conversationid2;
  id: Id2;
  payload: ResourcePayload;
  projectId: Projectid2;
  runId: Runid2;
  schemaVersion: Schemaversion2;
  sequence: Sequence2;
  timestamp: Timestamp2;
  type: Type2;
}
export interface ResourcePayload {
  id: Id3;
}
export interface EditEvent {
  conversationId: Conversationid3;
  id: Id4;
  payload: EditPayload;
  projectId: Projectid3;
  runId: Runid3;
  schemaVersion: Schemaversion3;
  sequence: Sequence3;
  timestamp: Timestamp3;
  type: Type3;
}
export interface EditPayload {
  batchId: Batchid;
  disposition: Disposition;
  error: AgentError | null;
}
export interface UsageEvent {
  conversationId: Conversationid4;
  id: Id5;
  payload: AgentUsage;
  projectId: Projectid4;
  runId: Runid4;
  schemaVersion: Schemaversion4;
  sequence: Sequence4;
  timestamp: Timestamp4;
  type: Type4;
}
export interface AgentUsage {
  cachedInputTokens: Cachedinputtokens;
  inputTokens: Inputtokens;
  outputTokens: Outputtokens;
  totalTokens: Totaltokens;
}
export interface RunStateEvent {
  conversationId: Conversationid5;
  id: Id6;
  payload: RunStatePayload;
  projectId: Projectid5;
  runId: Runid5;
  schemaVersion: Schemaversion5;
  sequence: Sequence5;
  timestamp: Timestamp5;
  type: Type5;
}
export interface RunStatePayload {
  error: AgentError | null;
  outcomeUnknown: Outcomeunknown;
  savedBatchId: Savedbatchid;
  state: State;
}
