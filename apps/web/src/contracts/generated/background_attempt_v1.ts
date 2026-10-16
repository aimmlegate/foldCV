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
  | "DEPENDENCY_CHANGED"
  | "WRITER_UNKNOWN"
  | "SAVE_FAILED"
  | "OUTCOME_UNKNOWN"
  | "PROJECT_DELETED";
export type Executiongeneration = number;
export type Id = string;
export type Nativestarted = boolean;
export type Schemaversion = 1;
export type Stage = "agent" | "assessment" | "extraction" | "rewrite" | "reconciliation";
export type Startupdeadline = string;
export type State =
  "reserved" | "starting" | "running" | "completed" | "failed" | "cancelled" | "interrupted" | "cleanup_failed";

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
