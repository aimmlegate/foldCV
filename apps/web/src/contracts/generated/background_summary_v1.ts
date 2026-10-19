export type Allowedits = boolean;
export type Approvalrequired = boolean;
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
export type Eventcursor = number;
export type Execution =
  "queued" | "starting" | "running" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Executiongeneration = number;
export type Jobid = string;
export type Kind = "agent" | "processing" | "rewrite" | "reconciliation";
export type Lineage = string;
export type Projectid = string;
export type Projecttitle = string;
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
export type Saved = boolean;
export type Schemaversion = 1;
export type Stage = ("agent" | "assessment" | "extraction" | "rewrite" | "reconciliation") | null;
export type Updatedat = string;

export interface JobSummaryV1 {
  allowEdits: Allowedits;
  approvalRequired?: Approvalrequired;
  error: JobFailure | null;
  eventCursor: Eventcursor;
  execution: Execution;
  executionGeneration: Executiongeneration;
  jobId: Jobid;
  kind: Kind;
  lineage: Lineage;
  projectId: Projectid;
  projectTitle: Projecttitle;
  publication: Publication;
  publicationError: JobFailure | null;
  saved: Saved;
  schemaVersion: Schemaversion;
  stage: Stage;
  updatedAt: Updatedat;
}
export interface JobFailure {
  code: Code;
}
