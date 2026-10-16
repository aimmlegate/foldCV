export type Cursor = number;
export type Generation = number;
export type Jobid = string;
export type Lineage = string;
export type Projectid = string;
export type Schemaversion = 1;
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
  | "PROJECT_DELETED";
export type Executiongeneration = number;
export type Id = string;
export type Nativestarted = boolean;
export type Schemaversion1 = 1;
export type Stage = "agent" | "assessment" | "extraction" | "rewrite" | "reconciliation";
export type Startupdeadline = string;
export type State =
  "reserved" | "starting" | "running" | "completed" | "failed" | "cancelled" | "interrupted" | "cleanup_failed";
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
export type Jobid1 = string;
export type Lineage1 = string;
export type Persistedat = string;
export type Projectid1 = string;
export type Projectrevision = number;
export type Proposalid1 = string;
export type Proposalsha256 = string;
export type Requestsha256 = string;
export type Schemaversion2 = 1;
export type Workspacesha256 = string;
export type Schemaversion3 = 1;
export type Accountgeneration = number;
export type Allowedits = boolean;
export type Allowweb = boolean;
export type Fingerprint = string;
export type Generation1 = number;
export type Key = string;
export type Kind = "entity" | "structure" | "query" | "source" | "rules";
/**
 * @maxItems 100
 */
export type Reads = GenerationStamp[];
export type Schemaversion4 = 1;
/**
 * @maxItems 100
 */
export type Writes = GenerationStamp[];
export type Lineage2 = string;
export type Projectid2 = string;
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
export type Schemaversion5 = 1;
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
export type Actionid = string;
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
 * @maxItems 10
 */
export type Tools =
  | []
  | [
      | "get_resume_context"
      | "find_resume_content"
      | "get_working_facts"
      | "get_original_source"
      | "get_conversation_context"
      | "check_resume"
      | "read_public_page"
      | "publish_findings"
      | "prepare_edit_batch"
      | "apply_edit_batch"
    ]
  | [
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      )
    ]
  | [
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      )
    ]
  | [
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      )
    ]
  | [
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      )
    ]
  | [
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      )
    ]
  | [
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      )
    ]
  | [
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      )
    ]
  | [
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      )
    ]
  | [
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      ),
      (
        | "get_resume_context"
        | "find_resume_content"
        | "get_working_facts"
        | "get_original_source"
        | "get_conversation_context"
        | "check_resume"
        | "read_public_page"
        | "publish_findings"
        | "prepare_edit_batch"
        | "apply_edit_batch"
      )
    ];
export type Updatedat = string;
export type Type = "job.snapshot" | "cursor.gap";
/**
 * @maxItems 512
 */
export type Events = JobEventV1[];
export type Schemaversion6 = 1;

export interface JobReplayV1 {
  events: Events;
  schemaVersion: Schemaversion6;
}
export interface JobEventV1 {
  cursor: Cursor;
  generation: Generation;
  jobId: Jobid;
  lineage: Lineage;
  projectId: Projectid;
  schemaVersion: Schemaversion;
  snapshot: JobSnapshotV1;
  type: Type;
}
export interface JobSnapshotV1 {
  attempts: Attempts;
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
  schemaVersion: Schemaversion3;
  submission: JobSubmissionV1;
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
  schemaVersion: Schemaversion1;
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
  jobId: Jobid1;
  lineage: Lineage1;
  persistedAt: Persistedat;
  projectId: Projectid1;
  projectRevision: Projectrevision;
  proposalId: Proposalid1;
  proposalSha256: Proposalsha256;
  requestSha256: Requestsha256;
  schemaVersion: Schemaversion2;
  workspaceSha256: Workspacesha256;
}
export interface JobSubmissionV1 {
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
  schemaVersion: Schemaversion5;
  scope: Scope;
  submittedAt: Submittedat;
  tools: Tools;
}
export interface ScopeGuardV1 {
  reads: Reads;
  schemaVersion: Schemaversion4;
  writes: Writes;
}
export interface GenerationStamp {
  fingerprint: Fingerprint;
  generation: Generation1;
  key: Key;
  kind: Kind;
}
export interface JobIdentity {
  lineage: Lineage2;
  projectId: Projectid2;
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
  actionId: Actionid;
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
