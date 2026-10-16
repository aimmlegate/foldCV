export type Aftergenerationssha256 = string;
export type Afterworkspacesha256 = string;
/**
 * @maxItems 100
 */
export type Assetpins = string[];
export type Barriergeneration = number | null;
export type Beforegenerationssha256 = string | null;
export type Beforeworkspacesha256 = string;
export type Candidateref = string;
export type Candidatesha256 = string | null;
export type Clientmutationid = string;
export type Id = string;
export type Incarnation = string | null;
export type Jobid = string;
export type Lineage = string;
export type Phase =
  | "intent_stored"
  | "commit_claimed"
  | "workspace_replaced"
  | "workspace_durable"
  | "generation_history_durable"
  | "receipt_stored"
  | "fenced"
  | "reconciled";
export type Previousref = string;
export type Projectid = string;
export type Proposalid = string;
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
export type Requestsha256 = string;
export type Resolvedat = string | null;
export type Schemaversion = 1;
export type Writerepoch = number | null;

export interface PublicationIntentV1 {
  afterGenerationsSha256: Aftergenerationssha256;
  afterWorkspaceSha256: Afterworkspacesha256;
  assetPins: Assetpins;
  barrierGeneration: Barriergeneration;
  beforeGenerationsSha256?: Beforegenerationssha256;
  beforeWorkspaceSha256: Beforeworkspacesha256;
  candidateRef: Candidateref;
  candidateSha256?: Candidatesha256;
  clientMutationId: Clientmutationid;
  id: Id;
  incarnation: Incarnation;
  jobId: Jobid;
  lineage: Lineage;
  phase: Phase;
  previousRef: Previousref;
  projectId: Projectid;
  proposalId: Proposalid;
  reconciledReason?: JobFailure | null;
  requestSha256: Requestsha256;
  resolvedAt?: Resolvedat;
  schemaVersion: Schemaversion;
  writerEpoch: Writerepoch;
}
export interface JobFailure {
  code: Code;
}
