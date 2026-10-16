export type Accountgeneration = number;
export type Activerequestepoch = number;
export type Acknowledgedrevision = number;
export type Actioncursor = number;
export type Expiresat = string;
export type Generation = number;
export type Incarnation = string;
export type Lineage = string;
export type Projectid = string;
export type Schemaversion = 1;
export type State = "acked" | "revoked" | "commit_claimed" | "resolved";
export type Token = string;
export type Touchgeneration = number;
export type Writerepoch = number;
export type Actioncursor1 = number;
export type Baserevision = number;
export type Basesha256 = string;
export type Checkpointedat = string;
export type Id = string;
export type Incarnation1 = string;
export type Lineage1 = string;
export type Payloadbytes = number;
export type Payloadref = string;
export type Payloadsha256 = string;
export type Projectid1 = string;
export type Schemaversion1 = 1;
export type Sequence = number;
export type Fingerprint = string;
export type Generation1 = number;
export type Key = string;
export type Kind = "entity" | "structure" | "query" | "source" | "rules";
/**
 * @maxItems 100
 */
export type Touches = GenerationStamp[];
export type Writerepoch1 = number;
/**
 * @maxItems 512
 */
export type Drafts = DraftCheckpointV1[];
export type Expiredthroughepoch = number;
/**
 * @maxItems 512
 */
export type Generations = GenerationStamp[];
export type Aftergenerationssha256 = string;
export type Afterworkspacesha256 = string;
/**
 * @maxItems 100
 */
export type Assetpins = string[];
export type Barriergeneration = number | null;
export type Beforeworkspacesha256 = string;
export type Candidateref = string;
export type Clientmutationid = string;
export type Id1 = string;
export type Incarnation2 = string | null;
export type Jobid = string;
export type Lineage2 = string;
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
export type Projectid2 = string;
export type Proposalid = string;
export type Requestsha256 = string;
export type Schemaversion2 = 1;
export type Writerepoch2 = number | null;
/**
 * @maxItems 512
 */
export type Intents = PublicationIntentV1[];
/**
 * @maxItems 20
 */
export type Inverses =
  | []
  | [UndoOwnershipV1]
  | [UndoOwnershipV1, UndoOwnershipV1]
  | [UndoOwnershipV1, UndoOwnershipV1, UndoOwnershipV1]
  | [UndoOwnershipV1, UndoOwnershipV1, UndoOwnershipV1, UndoOwnershipV1]
  | [UndoOwnershipV1, UndoOwnershipV1, UndoOwnershipV1, UndoOwnershipV1, UndoOwnershipV1]
  | [UndoOwnershipV1, UndoOwnershipV1, UndoOwnershipV1, UndoOwnershipV1, UndoOwnershipV1, UndoOwnershipV1]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ]
  | [
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1,
      UndoOwnershipV1
    ];
export type Expiresat1 = string;
/**
 * @maxItems 100
 */
export type Reads = GenerationStamp[];
export type Schemaversion3 = 1;
/**
 * @maxItems 100
 */
export type Writes = GenerationStamp[];
export type Incarnation3 = string | null;
export type Inversebytes = number;
export type Inverseref = string;
export type Inversesha256 = string;
export type Jobid1 = string;
export type Owner = "session" | "backend" | "transferring" | "expired";
export type Proposalid1 = string;
export type Schemaversion4 = 1;
export type Transferid = string;
export type Writerepoch3 = number | null;
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
  | "DEPENDENCY_CHANGED"
  | "WRITER_UNKNOWN"
  | "SAVE_FAILED"
  | "OUTCOME_UNKNOWN"
  | "PROJECT_DELETED";
export type Executiongeneration = number;
export type Id2 = string;
export type Nativestarted = boolean;
export type Schemaversion5 = 1;
export type Stage = "agent" | "assessment" | "extraction" | "rewrite" | "reconciliation";
export type Startupdeadline = string;
export type State1 =
  "reserved" | "starting" | "running" | "completed" | "failed" | "cancelled" | "interrupted" | "cleanup_failed";
export type Createdat = string;
export type Eventcursor = number;
export type Execution =
  "queued" | "starting" | "running" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Executiongeneration1 = number;
export type Id3 = string;
export type Proposalid2 = string | null;
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
export type Clientmutationid1 = string;
export type Documentrevision = number;
export type Durable = true;
export type Factsrevision = number;
export type Generationssha256 = string;
export type Jobid2 = string;
export type Lineage3 = string;
export type Persistedat = string;
export type Projectid3 = string;
export type Projectrevision = number;
export type Proposalid3 = string;
export type Proposalsha256 = string;
export type Requestsha2561 = string;
export type Schemaversion6 = 1;
export type Workspacesha256 = string;
export type Schemaversion7 = 1;
export type Accountgeneration1 = number;
export type Allowedits = boolean;
export type Allowweb = boolean;
export type Lineage4 = string;
export type Projectid4 = string;
export type Requestepoch = number;
export type Requestid = string;
export type Id4 = string;
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
export type Payloadsha2561 = string;
export type Schedulingclass = "background" | "interactive" | "reconciliation";
export type Schemaversion8 = 1;
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
export type Id5 = string;
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
/**
 * @maxItems 512
 */
export type Jobs = JobSnapshotV1[];
export type Lineage5 = string;
export type Projectid5 = string;
export type Acceptedat = string;
export type Accountgeneration2 = number;
export type Authority = "active" | "revoked";
export type Executiondeadline = string;
export type Executiongeneration2 = number;
export type Id6 = string;
export type Jobid3 = string;
export type Lineage6 = string;
export type Payload = AgentPayloadReference | FixedPayloadReference | ProcessingPayloadReference;
export type Batchid = string;
export type Conversationid = string;
export type Kind7 = "agent_journal";
export type Runid = string;
export type Kind8 = "rich_sync";
export type Syncid = string;
export type Candidateid = string;
export type Kind9 = "processing";
export type Payloadbytes1 = number;
export type Payloadsha2562 = string;
export type Projectid6 = string;
export type Revocation = ("stop" | "discard" | "superseded" | "deleted" | "account_changed") | null;
export type Schemaversion9 = 1;
export type Scope1 = WholeResumeScope | SelectionScope;
export type Turnid = string;
/**
 * @maxItems 512
 */
export type Proposals = ProposalBindingV1[];
export type Requestepochexpiresat = string;
export type Expiresat2 = string;
export type Jobid4 = string;
export type Payloadsha2563 = string;
/**
 * @maxItems 512
 */
export type Requests = RequestReplayV1[];
export type Schemaversion10 = 1;
export type Tombstoned = boolean;
export type Acknowledgedcursor = number;
export type Acknowledgedrevision1 = number;
export type Barriergeneration1 = number;
export type Draftid = string | null;
export type Epoch = number;
export type Incarnation4 = string;
export type Leaseexpiresat = string;
export type Lineage7 = string;
export type Projectid7 = string;
export type Resumecredentialsha256 = string;
export type Schemaversion11 = 1;
export type Sessionid1 = string;
export type Status = "attached" | "recovering" | "clean_detached" | "fenced";
export type Touchgeneration1 = number;

export interface BackgroundSidecarV1 {
  accountGeneration: Accountgeneration;
  activeRequestEpoch: Activerequestepoch;
  barrier: PublicationBarrierV1 | null;
  drafts: Drafts;
  expiredThroughEpoch: Expiredthroughepoch;
  generations: Generations;
  intents: Intents;
  inverses: Inverses;
  jobs: Jobs;
  lineage: Lineage5;
  projectId: Projectid5;
  proposals: Proposals;
  requestEpochExpiresAt: Requestepochexpiresat;
  requests: Requests;
  schemaVersion: Schemaversion10;
  tombstoned: Tombstoned;
  writer: WriterSessionV1 | null;
}
export interface PublicationBarrierV1 {
  acknowledgedRevision: Acknowledgedrevision;
  actionCursor: Actioncursor;
  expiresAt: Expiresat;
  generation: Generation;
  incarnation: Incarnation;
  lineage: Lineage;
  projectId: Projectid;
  schemaVersion: Schemaversion;
  state: State;
  token: Token;
  touchGeneration: Touchgeneration;
  writerEpoch: Writerepoch;
}
export interface DraftCheckpointV1 {
  actionCursor: Actioncursor1;
  baseRevision: Baserevision;
  baseSha256: Basesha256;
  checkpointedAt: Checkpointedat;
  id: Id;
  incarnation: Incarnation1;
  lineage: Lineage1;
  payloadBytes: Payloadbytes;
  payloadRef: Payloadref;
  payloadSha256: Payloadsha256;
  projectId: Projectid1;
  schemaVersion: Schemaversion1;
  sequence: Sequence;
  touches: Touches;
  writerEpoch: Writerepoch1;
}
export interface GenerationStamp {
  fingerprint: Fingerprint;
  generation: Generation1;
  key: Key;
  kind: Kind;
}
export interface PublicationIntentV1 {
  afterGenerationsSha256: Aftergenerationssha256;
  afterWorkspaceSha256: Afterworkspacesha256;
  assetPins: Assetpins;
  barrierGeneration: Barriergeneration;
  beforeWorkspaceSha256: Beforeworkspacesha256;
  candidateRef: Candidateref;
  clientMutationId: Clientmutationid;
  id: Id1;
  incarnation: Incarnation2;
  jobId: Jobid;
  lineage: Lineage2;
  phase: Phase;
  previousRef: Previousref;
  projectId: Projectid2;
  proposalId: Proposalid;
  requestSha256: Requestsha256;
  schemaVersion: Schemaversion2;
  writerEpoch: Writerepoch2;
}
export interface UndoOwnershipV1 {
  expiresAt: Expiresat1;
  guards: ScopeGuardV1;
  incarnation: Incarnation3;
  inverseBytes: Inversebytes;
  inverseRef: Inverseref;
  inverseSha256: Inversesha256;
  jobId: Jobid1;
  owner: Owner;
  proposalId: Proposalid1;
  schemaVersion: Schemaversion4;
  transferId: Transferid;
  writerEpoch: Writerepoch3;
}
export interface ScopeGuardV1 {
  reads: Reads;
  schemaVersion: Schemaversion3;
  writes: Writes;
}
export interface JobSnapshotV1 {
  attempts: Attempts;
  createdAt: Createdat;
  error: JobFailure | null;
  eventCursor: Eventcursor;
  execution: Execution;
  executionGeneration: Executiongeneration1;
  id: Id3;
  proposalId: Proposalid2;
  publication: Publication;
  receipt: CanonicalReceiptV1 | null;
  schemaVersion: Schemaversion7;
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
  id: Id2;
  nativeStarted: Nativestarted;
  schemaVersion: Schemaversion5;
  stage: Stage;
  startupDeadline: Startupdeadline;
  state: State1;
}
export interface JobFailure {
  code: Code;
}
export interface CanonicalReceiptV1 {
  clientMutationId: Clientmutationid1;
  documentRevision: Documentrevision;
  durable: Durable;
  factsRevision: Factsrevision;
  generationsSha256: Generationssha256;
  jobId: Jobid2;
  lineage: Lineage3;
  persistedAt: Persistedat;
  projectId: Projectid3;
  projectRevision: Projectrevision;
  proposalId: Proposalid3;
  proposalSha256: Proposalsha256;
  requestSha256: Requestsha2561;
  schemaVersion: Schemaversion6;
  workspaceSha256: Workspacesha256;
}
export interface JobSubmissionV1 {
  accountGeneration: Accountgeneration1;
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  guards: ScopeGuardV1;
  identity: JobIdentity;
  input: InputReference;
  kind: Kind2;
  models: Models;
  payloadSha256: Payloadsha2561;
  schedulingClass: Schedulingclass;
  schemaVersion: Schemaversion8;
  scope: Scope;
  submittedAt: Submittedat;
  tools: Tools;
}
export interface JobIdentity {
  lineage: Lineage4;
  projectId: Projectid4;
  requestEpoch: Requestepoch;
  requestId: Requestid;
}
export interface InputReference {
  id: Id4;
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
  id: Id5;
  kind: Kind5;
  revision: Revision;
}
export interface ProposalBindingV1 {
  acceptedAt: Acceptedat;
  accountGeneration: Accountgeneration2;
  authority: Authority;
  executionDeadline: Executiondeadline;
  executionGeneration: Executiongeneration2;
  guards: ScopeGuardV1;
  id: Id6;
  jobId: Jobid3;
  lineage: Lineage6;
  payload: Payload;
  payloadBytes: Payloadbytes1;
  payloadSha256: Payloadsha2562;
  projectId: Projectid6;
  revocation: Revocation;
  schemaVersion: Schemaversion9;
  scope: Scope1;
  turnId: Turnid;
}
export interface AgentPayloadReference {
  batchId: Batchid;
  conversationId: Conversationid;
  kind: Kind7;
  runId: Runid;
}
export interface FixedPayloadReference {
  kind: Kind8;
  syncId: Syncid;
}
export interface ProcessingPayloadReference {
  candidateId: Candidateid;
  kind: Kind9;
}
export interface RequestReplayV1 {
  archivedResult: JobSnapshotV1 | null;
  expiresAt: Expiresat2;
  identity: JobIdentity;
  jobId: Jobid4;
  payloadSha256: Payloadsha2563;
}
export interface WriterSessionV1 {
  acknowledgedCursor: Acknowledgedcursor;
  acknowledgedRevision: Acknowledgedrevision1;
  barrierGeneration: Barriergeneration1;
  draftId: Draftid;
  epoch: Epoch;
  incarnation: Incarnation4;
  leaseExpiresAt: Leaseexpiresat;
  lineage: Lineage7;
  projectId: Projectid7;
  resumeCredentialSha256: Resumecredentialsha256;
  schemaVersion: Schemaversion11;
  sessionId: Sessionid1;
  status: Status;
  touchGeneration: Touchgeneration1;
}
