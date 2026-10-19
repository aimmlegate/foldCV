export type AgentEvent =
  MessageDelta | ActivityEvent | ToolEvent | ResourceEvent | EditEvent | UsageEvent | RunStateEvent;
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
export type Itemid = string;
export type Kind = "summary";
export type Text1 = string;
export type Projectid1 = string;
export type Runid1 = string;
export type Schemaversion1 = 1;
export type Sequence1 = number;
export type Timestamp1 = string;
export type Type1 = "activity.updated";
export type Conversationid2 = string;
export type Id2 = string;
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
export type Projectid2 = string;
export type Runid2 = string;
export type Schemaversion2 = 1;
export type Sequence2 = number;
export type Timestamp2 = string;
export type Type2 = "tool.started" | "tool.completed" | "tool.failed";
export type Conversationid3 = string;
export type Id3 = string;
export type Id4 = string;
export type Projectid3 = string;
export type Runid3 = string;
export type Schemaversion3 = 1;
export type Sequence3 = number;
export type Timestamp3 = string;
export type Type3 = "source.ready" | "finding.ready";
export type Conversationid4 = string;
export type Id5 = string;
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
export type Projectid4 = string;
export type Runid4 = string;
export type Schemaversion4 = 1;
export type Sequence4 = number;
export type Timestamp4 = string;
export type Type4 = "edit.offered" | "edit.result";
export type Conversationid5 = string;
export type Id6 = string;
export type Cachedinputtokens = number;
export type Inputtokens = number;
export type Outputtokens = number;
export type Totaltokens = number;
export type Projectid5 = string;
export type Runid5 = string;
export type Schemaversion5 = 1;
export type Sequence5 = number;
export type Timestamp5 = string;
export type Type5 = "usage.reported";
export type Conversationid6 = string;
export type Id7 = string;
export type Outcomeunknown = boolean;
export type Savedbatchid = string | null;
export type State =
  "queued" | "running" | "waiting_for_editor" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Projectid6 = string;
export type Runid6 = string;
export type Schemaversion6 = 1;
export type Sequence6 = number;
export type Timestamp6 = string;
export type Type6 = "run.state_changed";
/**
 * @maxItems 40
 */
export type Activity = AgentEvent[];
export type Assetpinssha256 = string | null;
/**
 * @maxItems 2
 */
export type Attempts = [] | [JobAttemptV1] | [JobAttemptV1, JobAttemptV1];
export type Activedeadline = string;
export type Childstartedat = string | null;
export type Cleanupverified = boolean;
export type Dispatchedat = string;
export type Code1 =
  | "AUTH_REQUIRED"
  | "RATE_LIMITED"
  | "BUSY"
  | "MODEL_DENIED"
  | "CANCELLED"
  | "DEADLINE"
  | "STARTUP_TIMEOUT"
  | "PROCESS_FAILED"
  | "CLEANUP_FAILED"
  | "INTERRUPTED"
  | "PROTOCOL"
  | "JOB_QUEUE_FULL"
  | "JOB_STORAGE_FULL"
  | "JOB_IDEMPOTENCY_CONFLICT"
  | "REQUEST_EXPIRED"
  | "JOB_NOT_FOUND"
  | "JOB_STORE_CORRUPT"
  | "JOB_STORE_UNAVAILABLE"
  | "JOB_DISABLED"
  | "JOB_SCOPE_INVALID"
  | "ACCOUNT_CHANGED"
  | "DEPENDENCY_CHANGED"
  | "WRITER_UNKNOWN"
  | "SAVE_FAILED"
  | "OUTCOME_UNKNOWN"
  | "PROJECT_DELETED"
  | "INVALID_RESULT"
  | "TEMP_FAILED"
  | "CLI_MISSING"
  | "CLI_UNSUPPORTED"
  | "CLI_PROFILE_UNSAFE"
  | "AUTH_MODE_MISMATCH"
  | "INPUT_TOO_LARGE"
  | "OUTPUT_TOO_LARGE"
  | "BUDGET_EXCEEDED"
  | "INVALID_INPUT"
  | "INVALID_SCHEMA"
  | "CLI_FAILED"
  | "UNSAFE_TEMP_ROOT"
  | "INCOMPLETE_STREAM";
export type Executiongeneration = number;
export type Id8 = string;
export type Nativestarted = boolean;
export type Schemaversion7 = 1;
export type Stage = "agent" | "assessment" | "extraction" | "rewrite" | "reconciliation";
export type Startupdeadline = string;
export type State1 =
  "reserved" | "starting" | "running" | "completed" | "failed" | "cancelled" | "interrupted" | "cleanup_failed";
export type Captureinvalidated = boolean;
export type Createdat = string;
export type Eventcursor = number;
export type Execution =
  "queued" | "starting" | "running" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Executiongeneration1 = number;
export type Id9 = string;
export type Proposalid = string | null;
export type Publication =
  | "none"
  | "ready"
  | "waiting_for_sync"
  | "needs_review"
  | "committing"
  | "saved"
  | "no_change"
  | "save_failed"
  | "outcome_unknown"
  | "discarded"
  | "cancelled";
export type Clientmutationid = string;
export type Documentrevision = number;
export type Durable = true;
export type Factsrevision = number;
export type Generationssha256 = string;
export type Jobid = string;
export type Lineage = string;
export type Persistedat = string;
export type Projectid7 = string;
export type Projectrevision = number;
export type Proposalid1 = string;
export type Proposalsha256 = string;
export type Requestsha256 = string;
export type Schemaversion8 = 1;
export type Workspacesha256 = string;
export type Schemaversion9 = 1;
export type Accessrevision = number;
export type Accountgeneration = number;
export type Allowedits = boolean;
export type Allowweb = boolean;
export type Approvalrequired = boolean;
export type Fingerprint = string;
export type Generation = number;
export type Key = string;
export type Kind1 = "entity" | "structure" | "query" | "source" | "rules";
/**
 * @maxItems 4096
 */
export type Reads = GenerationStamp[];
export type Schemaversion10 = 1;
/**
 * @maxItems 4096
 */
export type Writes = GenerationStamp[];
export type Lineage1 = string;
export type Projectid8 = string;
export type Requestepoch = number;
export type Requestid = string;
export type Id10 = string;
export type Kind2 = "agent_journal" | "rich_sync" | "processing";
export type Sha256 = string;
export type Kind3 = "agent" | "processing" | "rewrite" | "reconciliation";
/**
 * @minItems 1
 * @maxItems 2
 */
export type Models = [ModelCapture] | [ModelCapture, ModelCapture];
export type Configsha256 = string;
export type Model = string;
export type Stage1 = "agent" | "assessment" | "extraction" | "rewrite" | "reconciliation";
export type Payloadsha256 = string;
export type Schedulingclass = "background" | "interactive" | "reconciliation";
export type Schemaversion11 = 1;
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
export type Id11 = string;
export type Kind6 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Kind7 = "text" | "blocks" | "table_cells";
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
export type Undoexpired = boolean;
export type Updatedat = string;
/**
 * @maxItems 4096
 */
export type Jobs = JobSnapshotV1[];
export type Lineage2 = string;
export type Projectid9 = string;
export type Requestepoch1 = number;
export type Schemaversion12 = 1;

export interface JobProjectV1 {
  jobs: Jobs;
  lineage: Lineage2;
  projectId: Projectid9;
  requestEpoch: Requestepoch1;
  schemaVersion: Schemaversion12;
}
export interface JobSnapshotV1 {
  activity?: Activity;
  assetPinsSha256?: Assetpinssha256;
  attempts: Attempts;
  captureInvalidated?: Captureinvalidated;
  createdAt: Createdat;
  error: JobFailure | null;
  eventCursor: Eventcursor;
  execution: Execution;
  executionGeneration: Executiongeneration1;
  id: Id9;
  proposalId: Proposalid;
  publication: Publication;
  publicationError?: JobFailure | null;
  receipt: CanonicalReceiptV1 | null;
  schemaVersion: Schemaversion9;
  submission: JobSubmissionV1;
  undoExpired?: Undoexpired;
  updatedAt: Updatedat;
}
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
export interface ActivityEvent {
  conversationId: Conversationid1;
  id: Id1;
  payload: ActivityPayload;
  projectId: Projectid1;
  runId: Runid1;
  schemaVersion: Schemaversion1;
  sequence: Sequence1;
  timestamp: Timestamp1;
  type: Type1;
}
export interface ActivityPayload {
  itemId: Itemid;
  kind: Kind;
  text: Text1;
}
export interface ToolEvent {
  conversationId: Conversationid2;
  id: Id2;
  payload: ToolPayload;
  projectId: Projectid2;
  runId: Runid2;
  schemaVersion: Schemaversion2;
  sequence: Sequence2;
  timestamp: Timestamp2;
  type: Type2;
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
  conversationId: Conversationid3;
  id: Id3;
  payload: ResourcePayload;
  projectId: Projectid3;
  runId: Runid3;
  schemaVersion: Schemaversion3;
  sequence: Sequence3;
  timestamp: Timestamp3;
  type: Type3;
}
export interface ResourcePayload {
  id: Id4;
}
export interface EditEvent {
  conversationId: Conversationid4;
  id: Id5;
  payload: EditPayload;
  projectId: Projectid4;
  runId: Runid4;
  schemaVersion: Schemaversion4;
  sequence: Sequence4;
  timestamp: Timestamp4;
  type: Type4;
}
export interface EditPayload {
  batchId: Batchid;
  disposition: Disposition;
  error: AgentError | null;
}
export interface UsageEvent {
  conversationId: Conversationid5;
  id: Id6;
  payload: AgentUsage;
  projectId: Projectid5;
  runId: Runid5;
  schemaVersion: Schemaversion5;
  sequence: Sequence5;
  timestamp: Timestamp5;
  type: Type5;
}
export interface AgentUsage {
  cachedInputTokens: Cachedinputtokens;
  inputTokens: Inputtokens;
  outputTokens: Outputtokens;
  totalTokens: Totaltokens;
}
export interface RunStateEvent {
  conversationId: Conversationid6;
  id: Id7;
  payload: RunStatePayload;
  projectId: Projectid6;
  runId: Runid6;
  schemaVersion: Schemaversion6;
  sequence: Sequence6;
  timestamp: Timestamp6;
  type: Type6;
}
export interface RunStatePayload {
  error: AgentError | null;
  outcomeUnknown: Outcomeunknown;
  savedBatchId: Savedbatchid;
  state: State;
}
export interface JobAttemptV1 {
  activeDeadline: Activedeadline;
  childStartedAt: Childstartedat;
  cleanupVerified: Cleanupverified;
  dispatchedAt: Dispatchedat;
  error: JobFailure | null;
  executionGeneration: Executiongeneration;
  id: Id8;
  nativeStarted: Nativestarted;
  schemaVersion: Schemaversion7;
  stage: Stage;
  startupDeadline: Startupdeadline;
  state: State1;
}
export interface JobFailure {
  code: Code1;
}
export interface CanonicalReceiptV1 {
  clientMutationId: Clientmutationid;
  documentRevision: Documentrevision;
  durable: Durable;
  factsRevision: Factsrevision;
  generationsSha256: Generationssha256;
  jobId: Jobid;
  lineage: Lineage;
  persistedAt: Persistedat;
  projectId: Projectid7;
  projectRevision: Projectrevision;
  proposalId: Proposalid1;
  proposalSha256: Proposalsha256;
  requestSha256: Requestsha256;
  schemaVersion: Schemaversion8;
  workspaceSha256: Workspacesha256;
}
export interface JobSubmissionV1 {
  accessRevision?: Accessrevision;
  accountGeneration: Accountgeneration;
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  approvalRequired?: Approvalrequired;
  guards: ScopeGuardV1;
  identity: JobIdentity;
  input: InputReference;
  kind: Kind3;
  models: Models;
  payloadSha256: Payloadsha256;
  schedulingClass: Schedulingclass;
  schemaVersion: Schemaversion11;
  scope: Scope;
  submittedAt: Submittedat;
  tools: Tools;
}
export interface ScopeGuardV1 {
  reads: Reads;
  schemaVersion: Schemaversion10;
  writes: Writes;
}
export interface GenerationStamp {
  fingerprint: Fingerprint;
  generation: Generation;
  key: Key;
  kind: Kind1;
}
export interface JobIdentity {
  lineage: Lineage1;
  projectId: Projectid8;
  requestEpoch: Requestepoch;
  requestId: Requestid;
}
export interface InputReference {
  id: Id10;
  kind: Kind2;
  sha256: Sha256;
}
export interface ModelCapture {
  configSha256: Configsha256;
  model: Model;
  stage: Stage1;
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
  id: Id11;
  kind: Kind6;
  revision: Revision;
}
