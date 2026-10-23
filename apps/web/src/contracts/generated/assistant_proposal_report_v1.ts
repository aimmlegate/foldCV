export type Contentsha256 = string;
export type Epoch = number;
export type Token = string;
export type Proposalid = string;
export type Protocolversion = 1;
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
export type Schemaversion = 1;
export type Version = number;

export interface AssistantProposalReportV1 {
  contentSha256: Contentsha256;
  owner: AgentOwner;
  proposalId: Proposalid;
  protocolVersion: Protocolversion;
  receipt: AgentEditReceipt;
  schemaVersion?: Schemaversion;
  version: Version;
}
export interface AgentOwner {
  epoch: Epoch;
  token: Token;
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
