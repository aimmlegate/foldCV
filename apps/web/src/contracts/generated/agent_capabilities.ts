export type Binarysha256 = string | null;
export type Binaryversion = string;
export type Configsha256 = string | null;
export type Connectionepoch = string | null;
export type Accountepoch = string;
export type Binarysha2561 = string;
export type Configsha2561 = string;
export type Model = string;
export type Protocolsha256 = string;
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
export type State = "unverified" | "verified" | "incompatible";
/**
 * @maxItems 100
 */
export type Models = AgentModelCapability[];
export type Modes = ("edit" | "check_only")[];
export type Protocolsha2561 = string | null;
export type Ready = boolean;
export type Schemaversion = 1;
/**
 * @maxItems 32
 */
export type Tools = string[];
export type Webavailable = boolean;

export interface AgentCapabilities {
  binarySha256: Binarysha256;
  binaryVersion: Binaryversion;
  configSha256: Configsha256;
  connectionEpoch: Connectionepoch;
  models: Models;
  modes: Modes;
  protocolSha256: Protocolsha2561;
  ready: Ready;
  schemaVersion: Schemaversion;
  tools: Tools;
  unavailable: AgentError | null;
  webAvailable: Webavailable;
}
export interface AgentModelCapability {
  accountEpoch: Accountepoch;
  binarySha256: Binarysha2561;
  configSha256: Configsha2561;
  model: Model;
  protocolSha256: Protocolsha256;
  reason: AgentError | null;
  state: State;
}
export interface AgentError {
  code: Code;
}
