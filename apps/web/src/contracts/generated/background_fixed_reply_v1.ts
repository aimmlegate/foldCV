export type Actionid = string | null;
export type Assetpinssha256 = string | null;
/**
 * @maxItems 2
 */
export type Attempts = [] | [JobAttemptV1] | [JobAttemptV1, JobAttemptV1];
export type Activedeadline = string;
export type Childstartedat = string | null;
export type Cleanupverified = boolean;
export type Dispatchedat = string;
export type Code =
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
export type Id = string;
export type Nativestarted = boolean;
export type Schemaversion = 1;
export type Stage = "agent" | "assessment" | "extraction" | "rewrite" | "reconciliation";
export type Startupdeadline = string;
export type State =
  "reserved" | "starting" | "running" | "completed" | "failed" | "cancelled" | "interrupted" | "cleanup_failed";
export type Captureinvalidated = boolean;
export type Createdat = string;
export type Eventcursor = number;
export type Execution =
  "queued" | "starting" | "running" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Executiongeneration1 = number;
export type Id1 = string;
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
export type Projectid = string;
export type Projectrevision = number;
export type Proposalid1 = string;
export type Proposalsha256 = string;
export type Requestsha256 = string;
export type Schemaversion1 = 1;
export type Workspacesha256 = string;
export type Schemaversion2 = 1;
export type Accessrevision = number;
export type Accountgeneration = number;
export type Allowedits = boolean;
export type Allowweb = boolean;
export type Fingerprint = string;
export type Generation = number;
export type Key = string;
export type Kind = "entity" | "structure" | "query" | "source" | "rules";
/**
 * @maxItems 4096
 */
export type Reads = GenerationStamp[];
export type Schemaversion3 = 1;
/**
 * @maxItems 4096
 */
export type Writes = GenerationStamp[];
export type Lineage1 = string;
export type Projectid1 = string;
export type Requestepoch = number;
export type Requestid = string;
export type Id2 = string;
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
export type Stage1 = "agent" | "assessment" | "extraction" | "rewrite" | "reconciliation";
export type Payloadsha256 = string;
export type Schedulingclass = "background" | "interactive" | "reconciliation";
export type Schemaversion4 = 1;
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
export type Actionid1 = string;
export type Actiontoken = number;
export type Fingerprint1 = string | null;
export type Id3 = string;
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
export type Undoexpired = boolean;
export type Updatedat = string;
export type Projectid2 = string;
export type Schemaversion5 = 1;
export type Syncid = string | null;

export interface JobFixedReplyV1 {
  actionId: Actionid;
  job: JobSnapshotV1;
  projectId: Projectid2;
  schemaVersion: Schemaversion5;
  syncId: Syncid;
}
export interface JobSnapshotV1 {
  assetPinsSha256?: Assetpinssha256;
  attempts: Attempts;
  captureInvalidated?: Captureinvalidated;
  createdAt: Createdat;
  error: JobFailure | null;
  eventCursor: Eventcursor;
  execution: Execution;
  executionGeneration: Executiongeneration1;
  id: Id1;
  proposalId: Proposalid;
  publication: Publication;
  publicationError?: JobFailure | null;
  receipt: CanonicalReceiptV1 | null;
  schemaVersion: Schemaversion2;
  submission: JobSubmissionV1;
  undoExpired?: Undoexpired;
  updatedAt: Updatedat;
}
export interface JobAttemptV1 {
  activeDeadline: Activedeadline;
  childStartedAt: Childstartedat;
  cleanupVerified: Cleanupverified;
  dispatchedAt: Dispatchedat;
  error: JobFailure | null;
  executionGeneration: Executiongeneration;
  id: Id;
  nativeStarted: Nativestarted;
  schemaVersion: Schemaversion;
  stage: Stage;
  startupDeadline: Startupdeadline;
  state: State;
}
export interface JobFailure {
  code: Code;
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
  projectId: Projectid;
  projectRevision: Projectrevision;
  proposalId: Proposalid1;
  proposalSha256: Proposalsha256;
  requestSha256: Requestsha256;
  schemaVersion: Schemaversion1;
  workspaceSha256: Workspacesha256;
}
export interface JobSubmissionV1 {
  accessRevision?: Accessrevision;
  accountGeneration: Accountgeneration;
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  guards: ScopeGuardV1;
  identity: JobIdentity;
  input: InputReference;
  kind: Kind2;
  models: Models;
  payloadSha256: Payloadsha256;
  schedulingClass: Schedulingclass;
  schemaVersion: Schemaversion4;
  scope: Scope;
  submittedAt: Submittedat;
  tools: Tools;
}
export interface ScopeGuardV1 {
  reads: Reads;
  schemaVersion: Schemaversion3;
  writes: Writes;
}
export interface GenerationStamp {
  fingerprint: Fingerprint;
  generation: Generation;
  key: Key;
  kind: Kind;
}
export interface JobIdentity {
  lineage: Lineage1;
  projectId: Projectid1;
  requestEpoch: Requestepoch;
  requestId: Requestid;
}
export interface InputReference {
  id: Id2;
  kind: Kind1;
  sha256: Sha256;
}
export interface ModelCapture {
  configSha256: Configsha256;
  model: Model;
  stage: Stage1;
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
  actionId: Actionid1;
  actionToken: Actiontoken;
  dependencies: Dependencies;
  sessionId: Sessionid;
}
export interface DependencyStamp {
  fingerprint: Fingerprint1;
  id: Id3;
  kind: Kind5;
  revision: Revision;
}
