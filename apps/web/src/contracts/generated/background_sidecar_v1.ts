export type Accountgeneration = number;
export type Activerequestepoch = number;
export type Kind = "job" | "proposal" | "export" | "inverse" | "draft" | "session";
export type Owner = string;
export type Id = string;
export type Kind1 = "image" | "source";
export type Path = string;
export type Sha256 = string;
export type Size = number;
/**
 * @maxItems 100
 */
export type References = AssetReferenceV1[];
/**
 * @maxItems 4096
 */
export type Assetpins = AssetPinV1[];
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
/**
 * @maxItems 4096
 */
export type Cleanuprefs = string[];
export type Actioncursor1 = number;
export type Assetpinssha256 = string | null;
export type Baserevision = number;
export type Basesha256 = string;
export type Checkpointedat = string;
export type Id1 = string;
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
export type Kind2 = "entity" | "structure" | "query" | "source" | "rules";
/**
 * @maxItems 100
 */
export type Touches = GenerationStamp[];
export type Writerepoch1 = number;
/**
 * @maxItems 4096
 */
export type Drafts = DraftCheckpointV1[];
export type Expiredthroughepoch = number;
export type Actionid = string;
export type Actiontoken = number;
export type Requestepoch = number;
export type Sessionid = string;
/**
 * @maxItems 4096
 */
export type Fixedinvalidations = FixedInvalidationV1[];
/**
 * @maxItems 4096
 */
export type Generations = GenerationStamp[];
export type Key1 = string;
export type Selector = AgentEntityDependency | AgentQueryDependency;
export type Kind3 = "entity";
export type Fingerprint1 = string | null;
export type Id2 = string;
export type Kind4 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Fingerprint2 = string;
export type Kind5 = "query";
export type Cursor = string | null;
/**
 * @maxItems 100
 */
export type Ids = string[];
export type Kind6 = "context" | "document" | "find" | "facts" | "source" | "history" | "resources";
export type Parentid = string | null;
export type Text = string;
/**
 * @maxItems 4096
 */
export type Definitions = HistoryDefinitionV1[];
export type Namespace = string;
export type Phase = "initializing" | "ready" | "fenced";
export type Schemaversion2 = 1;
export type Workspacesha256 = string;
export type Candidateref = string;
export type Clientmutationid = string;
export type Commandid = string;
export type Commandsha256 = string;
export type Completedat = string;
export type Jobid = string;
export type Proposalid = string;
export type Requestsha256 = string;
export type Resultingrevision = number;
/**
 * @maxItems 4096
 */
export type Historycommands = HistoryCommandReceiptV1[];
export type Historynamespace = string | null;
export type Aftergenerationssha256 = string;
export type Afterworkspacesha256 = string;
/**
 * @maxItems 100
 */
export type Assetpins1 = string[];
export type Barriergeneration = number | null;
export type Beforegenerationssha256 = string | null;
export type Beforeworkspacesha256 = string;
export type Candidateref1 = string;
export type Candidatesha256 = string | null;
export type Clientmutationid1 = string;
export type Id3 = string;
export type Incarnation2 = string | null;
export type Jobid1 = string;
export type Lineage2 = string;
export type Phase1 =
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
export type Proposalid1 = string;
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
export type Requestsha2561 = string;
export type Resolvedat = string | null;
export type Schemaversion3 = 1;
export type Writerepoch2 = number | null;
/**
 * @maxItems 4096
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
export type Assetpinssha2561 = string | null;
export type Commandinversebytes = number | null;
export type Commandinversesha256 = string | null;
export type Commandref = string | null;
export type Direction = "undo" | "redo" | "closed";
export type Expiresat1 = string;
/**
 * @maxItems 4096
 */
export type Reads = GenerationStamp[];
export type Schemaversion4 = 1;
/**
 * @maxItems 4096
 */
export type Writes = GenerationStamp[];
export type Incarnation3 = string | null;
export type Inversebytes = number;
export type Inverseref = string;
export type Inversesha256 = string;
export type Jobid2 = string;
export type Owner1 = "session" | "backend" | "transferring" | "expired";
export type Proposalid2 = string;
export type Schemaversion5 = 1;
export type Transferid = string;
export type Writerepoch3 = number | null;
export type AgentEvent =
  MessageDelta | ActivityEvent | ToolEvent | ResourceEvent | EditEvent | UsageEvent | RunStateEvent;
export type Conversationid = string;
export type Id4 = string;
export type Text1 = string;
export type Projectid3 = string;
export type Runid = string;
export type Schemaversion6 = 1;
export type Sequence1 = number;
export type Timestamp = string;
export type Type = "message.delta";
export type Conversationid1 = string;
export type Id5 = string;
export type Itemid = string;
export type Kind7 = "summary";
export type Text2 = string;
export type Projectid4 = string;
export type Runid1 = string;
export type Schemaversion7 = 1;
export type Sequence2 = number;
export type Timestamp1 = string;
export type Type1 = "activity.updated";
export type Conversationid2 = string;
export type Id6 = string;
export type Callid = string;
export type Code1 =
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
export type Projectid5 = string;
export type Runid2 = string;
export type Schemaversion8 = 1;
export type Sequence3 = number;
export type Timestamp2 = string;
export type Type2 = "tool.started" | "tool.completed" | "tool.failed";
export type Conversationid3 = string;
export type Id7 = string;
export type Id8 = string;
export type Projectid6 = string;
export type Runid3 = string;
export type Schemaversion9 = 1;
export type Sequence4 = number;
export type Timestamp3 = string;
export type Type3 = "source.ready" | "finding.ready";
export type Conversationid4 = string;
export type Id9 = string;
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
export type Projectid7 = string;
export type Runid4 = string;
export type Schemaversion10 = 1;
export type Sequence5 = number;
export type Timestamp4 = string;
export type Type4 = "edit.offered" | "edit.result";
export type Conversationid5 = string;
export type Id10 = string;
export type Cachedinputtokens = number;
export type Inputtokens = number;
export type Outputtokens = number;
export type Totaltokens = number;
export type Projectid8 = string;
export type Runid5 = string;
export type Schemaversion11 = 1;
export type Sequence6 = number;
export type Timestamp5 = string;
export type Type5 = "usage.reported";
export type Conversationid6 = string;
export type Id11 = string;
export type Outcomeunknown = boolean;
export type Savedbatchid = string | null;
export type State1 =
  "queued" | "running" | "waiting_for_editor" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Projectid9 = string;
export type Runid6 = string;
export type Schemaversion12 = 1;
export type Sequence7 = number;
export type Timestamp6 = string;
export type Type6 = "run.state_changed";
/**
 * @maxItems 40
 */
export type Activity = AgentEvent[];
export type Assetpinssha2562 = string | null;
/**
 * @maxItems 2
 */
export type Attempts = [] | [JobAttemptV1] | [JobAttemptV1, JobAttemptV1];
export type Activedeadline = string;
export type Childstartedat = string | null;
export type Cleanupverified = boolean;
export type Dispatchedat = string;
export type Executiongeneration = number;
export type Id12 = string;
export type Nativestarted = boolean;
export type Schemaversion13 = 1;
export type Stage = "agent" | "assessment" | "extraction" | "rewrite" | "reconciliation";
export type Startupdeadline = string;
export type State2 =
  "reserved" | "starting" | "running" | "completed" | "failed" | "cancelled" | "interrupted" | "cleanup_failed";
export type Captureinvalidated = boolean;
export type Createdat = string;
export type Eventcursor = number;
export type Execution =
  "queued" | "starting" | "running" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Executiongeneration1 = number;
export type Id13 = string;
export type Proposalid3 = string | null;
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
export type Clientmutationid2 = string;
export type Documentrevision = number;
export type Durable = true;
export type Factsrevision = number;
export type Generationssha256 = string;
export type Jobid3 = string;
export type Lineage3 = string;
export type Persistedat = string;
export type Projectid10 = string;
export type Projectrevision = number;
export type Proposalid4 = string;
export type Proposalsha256 = string;
export type Requestsha2562 = string;
export type Schemaversion14 = 1;
export type Workspacesha2561 = string;
export type Schemaversion15 = 1;
export type Accessrevision = number;
export type Accountgeneration1 = number;
export type Allowedits = boolean;
export type Allowweb = boolean;
export type Approvalrequired = boolean;
export type Lineage4 = string;
export type Projectid11 = string;
export type Requestepoch1 = number;
export type Requestid = string;
export type Id14 = string;
export type Kind8 = "agent_journal" | "rich_sync" | "processing" | "template_import";
export type Sha2561 = string;
export type Kind9 = "agent" | "processing" | "rewrite" | "reconciliation";
/**
 * @minItems 1
 * @maxItems 2
 */
export type Models = [ModelCapture] | [ModelCapture, ModelCapture];
export type Configsha256 = string;
export type Model = string;
export type Stage1 = "agent" | "assessment" | "extraction" | "rewrite" | "reconciliation";
export type Payloadsha2561 = string;
export type Protocol = ("fixed_v1" | "agent_import_v1" | "template_import_v1") | null;
export type Schedulingclass = "background" | "interactive" | "reconciliation";
export type Schemaversion16 = 1;
export type Scope = WholeResumeScope | SelectionScope;
export type Kind10 = "resume";
export type Kind11 = "selection";
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
export type Actiontoken1 = number;
export type Dependencies = DependencyStamp[];
export type Sessionid1 = string;
export type Kind12 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Submittedat = string;
export type Templatecommand = (StartTemplateImportV1 | ResumeTemplateImportV1) | null;
export type Allowtextrewrite = boolean;
export type Authorityhash = string;
export type Dependencyhash = string;
export type Adapter = string;
export type Capabilityprofile = string;
export type Capabilityversion = string;
export type Configurationhash = string;
export type Effort = string;
export type Model1 = string;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Packagehash = string;
export type Callcap = number;
export type Cleanupseconds = 5;
export type Concurrency = 1;
export type Fallbackrepairs = 1;
export type Finalizationseconds = 30;
export type Primaryrepairs = 1;
export type Processingseconds = 300;
export type Clientrequestid = string;
export type Kind13 = "start_new_import";
export type Protocol1 = "template_import_v1";
export type Authorityhash1 = string;
export type Authorizationid = string;
export type Kind14 = "resume_import";
export type Operationid = string;
export type Protocol2 = "template_import_v1";
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
  | "get_application_skills"
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
export type Errorcode = string | null;
export type Intentid = string | null;
export type State3 = "pending" | "saved" | "failed_before_replacement" | "outcome_unknown" | "cancelled";
export type Workspacehash = string | null;
export type Undoexpired = boolean;
export type Updatedat = string;
/**
 * @maxItems 4096
 */
export type Jobs = JobSnapshotV1[];
export type Lineage5 = string;
export type Actionid2 = string | null;
export type Aftergenerationssha2561 = string;
export type Afterworkspacesha2561 = string;
/**
 * @maxItems 100
 */
export type Assetpins2 = string[];
export type Barriergeneration1 = number | null;
export type Beforegenerationssha2561 = string | null;
export type Beforeworkspacesha2561 = string;
export type Candidatepruned = boolean;
export type Candidateref2 = string;
export type Candidatesha2561 = string | null;
export type Clientmutationid3 = string;
export type Historyjobid = string | null;
export type Id15 = string;
export type Incarnation4 = string | null;
export type Lineage6 = string;
export type Phase2 =
  | "intent_stored"
  | "commit_claimed"
  | "workspace_replaced"
  | "workspace_durable"
  | "generation_history_durable"
  | "receipt_stored"
  | "fenced"
  | "reconciled";
export type Previousref1 = string;
export type Projectid12 = string;
export type Requestsha2563 = string;
export type Resolvedat1 = string | null;
export type Schemaversion17 = 1;
export type Stepssha256 = string | null;
export type Authorizationid1 = string;
export type Finalizationid = string;
export type Operationid1 = string;
export type Writerepoch4 = number | null;
/**
 * @maxItems 4096
 */
export type Manualintents = ManualIntentV1[];
export type Orphanedat = string;
export type Path1 = string;
/**
 * @maxItems 4096
 */
export type Orphanassets = OrphanAssetV1[];
export type Projectid13 = string;
export type Acceptedat = string;
export type Accountgeneration2 = number;
export type Authority = "active" | "revoked";
export type Executiondeadline = string;
export type Executiongeneration2 = number;
export type Id16 = string;
export type Jobid4 = string;
export type Lineage7 = string;
export type Payload = AgentPayloadReference | FixedPayloadReference | ProcessingPayloadReference;
export type Batchid1 = string;
export type Conversationid7 = string;
export type Kind15 = "agent_journal";
export type Runid7 = string;
export type Kind16 = "rich_sync";
export type Syncid = string;
export type Candidateid = string;
export type Kind17 = "processing";
export type Payloadbytes1 = number;
export type Payloadsha2562 = string;
export type Projectid14 = string;
export type Revocation = ("stop" | "discard" | "superseded" | "deleted" | "account_changed") | null;
export type Schemaversion18 = 1;
export type Scope1 = WholeResumeScope | SelectionScope;
export type Turnid = string;
/**
 * @maxItems 4096
 */
export type Proposals = ProposalBindingV1[];
export type Requestepochexpiresat = string;
export type Expiresat2 = string;
export type Jobid5 = string;
export type Payloadsha2563 = string;
/**
 * @maxItems 4096
 */
export type Requests = RequestReplayV1[];
export type Schemaversion19 = 1;
export type Accountgeneration3 = number;
export type Authorityhash2 = string;
export type Authorizationid2 = string;
export type Capturehash = string;
export type Generation2 = number;
export type Incarnationid = string;
export type Leaseid = string;
export type Pid = number | null;
export type Processstartwitness = string | null;
export type Reservationid = string;
export type Transportsessionid = string | null;
export type Transportturnid = string | null;
export type Attemptid = string;
export type Evidencehash = string;
export type Neverdispatched = boolean;
export type Ownerhash = string;
export type Verifiedat = string;
export type Witness = string;
export type Records = AttemptCleanupRecord[];
export type Dependencyhash1 = string;
export type Operationid2 = string;
export type Schemaversion20 = 1;
export type State4 = "active" | "cancelled";
/**
 * @maxItems 4096
 */
export type Templateauthorizations = TemplatePublicationAuthorizationV1[];
export type Tombstoned = boolean;
export type Abandonedepoch = number | null;
export type Acknowledgedcursor = number;
export type Acknowledgedrevision1 = number;
export type Acknowledgedsha256 = string | null;
export type Barriergeneration2 = number;
export type Draftid = string | null;
export type Draftsequencefloor = number;
export type Epoch = number;
export type Incarnation5 = string;
export type Leaseexpiresat = string;
export type Lineage8 = string;
export type Projectid15 = string;
export type Resumecredentialsha256 = string;
export type Schemaversion21 = 1;
export type Sessionid2 = string;
export type Status = "attached" | "recovering" | "clean_detached" | "fenced";
export type Touchfloor = number;
export type Touchgeneration1 = number;
export type Writerepoch5 = number;
export type Cursor1 = number;
export type Sha2562 = string;
/**
 * @maxItems 4096
 */
export type Writertouches = WriterTouchReceiptV1[];

export interface BackgroundSidecarV1 {
  accountGeneration: Accountgeneration;
  activeRequestEpoch: Activerequestepoch;
  assetPins?: Assetpins;
  barrier: PublicationBarrierV1 | null;
  cleanupRefs?: Cleanuprefs;
  drafts: Drafts;
  expiredThroughEpoch: Expiredthroughepoch;
  fixedInvalidations?: Fixedinvalidations;
  generations: Generations;
  history?: BackgroundHistoryV1 | null;
  historyCommands?: Historycommands;
  historyNamespace?: Historynamespace;
  intents: Intents;
  inverses: Inverses;
  jobs: Jobs;
  lineage: Lineage5;
  manualIntents?: Manualintents;
  orphanAssets?: Orphanassets;
  projectId: Projectid13;
  proposals: Proposals;
  requestEpochExpiresAt: Requestepochexpiresat;
  requests: Requests;
  schemaVersion: Schemaversion19;
  templateAuthorizations?: Templateauthorizations;
  tombstoned: Tombstoned;
  writer: WriterSessionV1 | null;
  writerEpoch?: Writerepoch5;
  writerTouches?: Writertouches;
}
export interface AssetPinV1 {
  kind: Kind;
  owner: Owner;
  references: References;
}
export interface AssetReferenceV1 {
  id: Id;
  kind: Kind1;
  path: Path;
  sha256: Sha256;
  size: Size;
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
  assetPinsSha256?: Assetpinssha256;
  baseRevision: Baserevision;
  baseSha256: Basesha256;
  checkpointedAt: Checkpointedat;
  id: Id1;
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
  kind: Kind2;
}
export interface FixedInvalidationV1 {
  actionId: Actionid;
  actionToken: Actiontoken;
  requestEpoch: Requestepoch;
  sessionId: Sessionid;
}
export interface BackgroundHistoryV1 {
  definitions: Definitions;
  namespace: Namespace;
  phase: Phase;
  schemaVersion: Schemaversion2;
  workspaceSha256: Workspacesha256;
}
export interface HistoryDefinitionV1 {
  key: Key1;
  selector: Selector;
}
export interface AgentEntityDependency {
  kind: Kind3;
  stamp: DependencyStamp;
}
export interface DependencyStamp {
  fingerprint: Fingerprint1;
  id: Id2;
  kind: Kind4;
  revision: Revision;
}
export interface AgentQueryDependency {
  fingerprint: Fingerprint2;
  kind: Kind5;
  query: AgentQuery;
}
export interface AgentQuery {
  cursor?: Cursor;
  ids?: Ids;
  kind: Kind6;
  parentId?: Parentid;
  text?: Text;
}
export interface HistoryCommandReceiptV1 {
  candidateRef: Candidateref;
  clientMutationId: Clientmutationid;
  commandId: Commandid;
  commandSha256: Commandsha256;
  completedAt: Completedat;
  jobId: Jobid;
  proposalId: Proposalid;
  requestSha256: Requestsha256;
  resultingRevision: Resultingrevision;
}
export interface PublicationIntentV1 {
  afterGenerationsSha256: Aftergenerationssha256;
  afterWorkspaceSha256: Afterworkspacesha256;
  assetPins: Assetpins1;
  barrierGeneration: Barriergeneration;
  beforeGenerationsSha256?: Beforegenerationssha256;
  beforeWorkspaceSha256: Beforeworkspacesha256;
  candidateRef: Candidateref1;
  candidateSha256?: Candidatesha256;
  clientMutationId: Clientmutationid1;
  id: Id3;
  incarnation: Incarnation2;
  jobId: Jobid1;
  lineage: Lineage2;
  phase: Phase1;
  previousRef: Previousref;
  projectId: Projectid2;
  proposalId: Proposalid1;
  reconciledReason?: JobFailure | null;
  requestSha256: Requestsha2561;
  resolvedAt?: Resolvedat;
  schemaVersion: Schemaversion3;
  writerEpoch: Writerepoch2;
}
export interface JobFailure {
  code: Code;
}
export interface UndoOwnershipV1 {
  assetPinsSha256?: Assetpinssha2561;
  commandInverseBytes?: Commandinversebytes;
  commandInverseSha256?: Commandinversesha256;
  commandRef?: Commandref;
  direction?: Direction;
  expiresAt: Expiresat1;
  guards: ScopeGuardV1;
  incarnation: Incarnation3;
  inverseBytes: Inversebytes;
  inverseRef: Inverseref;
  inverseSha256: Inversesha256;
  jobId: Jobid2;
  owner: Owner1;
  proposalId: Proposalid2;
  schemaVersion: Schemaversion5;
  transferId: Transferid;
  writerEpoch: Writerepoch3;
}
export interface ScopeGuardV1 {
  reads: Reads;
  schemaVersion: Schemaversion4;
  writes: Writes;
}
export interface JobSnapshotV1 {
  activity?: Activity;
  assetPinsSha256?: Assetpinssha2562;
  attempts: Attempts;
  captureInvalidated?: Captureinvalidated;
  createdAt: Createdat;
  error: JobFailure | null;
  eventCursor: Eventcursor;
  execution: Execution;
  executionGeneration: Executiongeneration1;
  id: Id13;
  proposalId: Proposalid3;
  publication: Publication;
  publicationError?: JobFailure | null;
  receipt: CanonicalReceiptV1 | null;
  schemaVersion: Schemaversion15;
  submission: JobSubmissionV1;
  templateOutcome?: PublicationOutcome | null;
  undoExpired?: Undoexpired;
  updatedAt: Updatedat;
}
export interface MessageDelta {
  conversationId: Conversationid;
  id: Id4;
  payload: MessageDeltaPayload;
  projectId: Projectid3;
  runId: Runid;
  schemaVersion: Schemaversion6;
  sequence: Sequence1;
  timestamp: Timestamp;
  type: Type;
}
export interface MessageDeltaPayload {
  text: Text1;
}
export interface ActivityEvent {
  conversationId: Conversationid1;
  id: Id5;
  payload: ActivityPayload;
  projectId: Projectid4;
  runId: Runid1;
  schemaVersion: Schemaversion7;
  sequence: Sequence2;
  timestamp: Timestamp1;
  type: Type1;
}
export interface ActivityPayload {
  itemId: Itemid;
  kind: Kind7;
  text: Text2;
}
export interface ToolEvent {
  conversationId: Conversationid2;
  id: Id6;
  payload: ToolPayload;
  projectId: Projectid5;
  runId: Runid2;
  schemaVersion: Schemaversion8;
  sequence: Sequence3;
  timestamp: Timestamp2;
  type: Type2;
}
export interface ToolPayload {
  callId: Callid;
  error: AgentError | null;
  name: Name;
}
export interface AgentError {
  code: Code1;
}
export interface ResourceEvent {
  conversationId: Conversationid3;
  id: Id7;
  payload: ResourcePayload;
  projectId: Projectid6;
  runId: Runid3;
  schemaVersion: Schemaversion9;
  sequence: Sequence4;
  timestamp: Timestamp3;
  type: Type3;
}
export interface ResourcePayload {
  id: Id8;
}
export interface EditEvent {
  conversationId: Conversationid4;
  id: Id9;
  payload: EditPayload;
  projectId: Projectid7;
  runId: Runid4;
  schemaVersion: Schemaversion10;
  sequence: Sequence5;
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
  id: Id10;
  payload: AgentUsage;
  projectId: Projectid8;
  runId: Runid5;
  schemaVersion: Schemaversion11;
  sequence: Sequence6;
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
  id: Id11;
  payload: RunStatePayload;
  projectId: Projectid9;
  runId: Runid6;
  schemaVersion: Schemaversion12;
  sequence: Sequence7;
  timestamp: Timestamp6;
  type: Type6;
}
export interface RunStatePayload {
  error: AgentError | null;
  outcomeUnknown: Outcomeunknown;
  savedBatchId: Savedbatchid;
  state: State1;
}
export interface JobAttemptV1 {
  activeDeadline: Activedeadline;
  childStartedAt: Childstartedat;
  cleanupVerified: Cleanupverified;
  dispatchedAt: Dispatchedat;
  error: JobFailure | null;
  executionGeneration: Executiongeneration;
  id: Id12;
  nativeStarted: Nativestarted;
  schemaVersion: Schemaversion13;
  stage: Stage;
  startupDeadline: Startupdeadline;
  state: State2;
}
export interface CanonicalReceiptV1 {
  clientMutationId: Clientmutationid2;
  documentRevision: Documentrevision;
  durable: Durable;
  factsRevision: Factsrevision;
  generationsSha256: Generationssha256;
  jobId: Jobid3;
  lineage: Lineage3;
  persistedAt: Persistedat;
  projectId: Projectid10;
  projectRevision: Projectrevision;
  proposalId: Proposalid4;
  proposalSha256: Proposalsha256;
  requestSha256: Requestsha2562;
  schemaVersion: Schemaversion14;
  workspaceSha256: Workspacesha2561;
}
export interface JobSubmissionV1 {
  accessRevision?: Accessrevision;
  accountGeneration: Accountgeneration1;
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  approvalRequired?: Approvalrequired;
  guards: ScopeGuardV1;
  identity: JobIdentity;
  input: InputReference;
  kind: Kind9;
  models: Models;
  payloadSha256: Payloadsha2561;
  protocol?: Protocol;
  schedulingClass: Schedulingclass;
  schemaVersion: Schemaversion16;
  scope: Scope;
  submittedAt: Submittedat;
  templateCommand?: Templatecommand;
  tools: Tools;
}
export interface JobIdentity {
  lineage: Lineage4;
  projectId: Projectid11;
  requestEpoch: Requestepoch1;
  requestId: Requestid;
}
export interface InputReference {
  id: Id14;
  kind: Kind8;
  sha256: Sha2561;
}
export interface ModelCapture {
  configSha256: Configsha256;
  model: Model;
  stage: Stage1;
}
export interface WholeResumeScope {
  kind: Kind10;
}
export interface SelectionScope {
  kind: Kind11;
  selection: RichSelection;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind12;
  textSha256: Textsha256;
}
export interface RichPosition {
  blockId: Blockid;
  cellId: Cellid;
  offset: Offset;
}
export interface ActionCapture {
  actionId: Actionid1;
  actionToken: Actiontoken1;
  dependencies: Dependencies;
  sessionId: Sessionid1;
}
export interface StartTemplateImportV1 {
  capture: ImportCapture;
  clientRequestId: Clientrequestid;
  kind: Kind13;
  protocol: Protocol1;
}
export interface ImportCapture {
  allowTextRewrite: Allowtextrewrite;
  authorityHash: Authorityhash;
  dependencyHash: Dependencyhash;
  factRevisions: Factrevisions;
  fallback: ModelCapture1 | null;
  formattingAsOf: PartialDate;
  packageHash: Packagehash;
  policy: RuntimePolicy;
  primary: ModelCapture1;
  sourceHashes: Sourcehashes;
}
export interface Factrevisions {
  [k: string]: number;
}
export interface ModelCapture1 {
  adapter: Adapter;
  capabilityProfile: Capabilityprofile;
  capabilityVersion: Capabilityversion;
  configurationHash: Configurationhash;
  effort: Effort;
  model: Model1;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface RuntimePolicy {
  callCap: Callcap;
  cleanupSeconds: Cleanupseconds;
  concurrency: Concurrency;
  fallbackRepairs: Fallbackrepairs;
  finalizationSeconds: Finalizationseconds;
  primaryRepairs: Primaryrepairs;
  processingSeconds: Processingseconds;
}
export interface Sourcehashes {
  [k: string]: string;
}
export interface ResumeTemplateImportV1 {
  authorityHash: Authorityhash1;
  authorizationId: Authorizationid;
  kind: Kind14;
  operationId: Operationid;
  protocol: Protocol2;
}
export interface PublicationOutcome {
  errorCode: Errorcode;
  intentId: Intentid;
  state: State3;
  workspaceHash: Workspacehash;
}
export interface ManualIntentV1 {
  actionId?: Actionid2;
  afterGenerationsSha256: Aftergenerationssha2561;
  afterWorkspaceSha256: Afterworkspacesha2561;
  assetPins: Assetpins2;
  barrierGeneration: Barriergeneration1;
  beforeGenerationsSha256?: Beforegenerationssha2561;
  beforeWorkspaceSha256: Beforeworkspacesha2561;
  candidatePruned?: Candidatepruned;
  candidateRef: Candidateref2;
  candidateSha256?: Candidatesha2561;
  clientMutationId: Clientmutationid3;
  historyJobId?: Historyjobid;
  id: Id15;
  incarnation: Incarnation4;
  lineage: Lineage6;
  phase: Phase2;
  previousRef: Previousref1;
  projectId: Projectid12;
  reconciledReason?: JobFailure | null;
  requestSha256: Requestsha2563;
  resolvedAt?: Resolvedat1;
  schemaVersion: Schemaversion17;
  stepsSha256?: Stepssha256;
  templateFinalization?: TemplateFinalizationBinding | null;
  writerEpoch: Writerepoch4;
}
export interface TemplateFinalizationBinding {
  authorizationId: Authorizationid1;
  finalizationId: Finalizationid;
  operationId: Operationid1;
}
export interface OrphanAssetV1 {
  orphanedAt: Orphanedat;
  path: Path1;
}
export interface ProposalBindingV1 {
  acceptedAt: Acceptedat;
  accountGeneration: Accountgeneration2;
  authority: Authority;
  executionDeadline: Executiondeadline;
  executionGeneration: Executiongeneration2;
  guards: ScopeGuardV1;
  id: Id16;
  jobId: Jobid4;
  lineage: Lineage7;
  payload: Payload;
  payloadBytes: Payloadbytes1;
  payloadSha256: Payloadsha2562;
  projectId: Projectid14;
  revocation: Revocation;
  schemaVersion: Schemaversion18;
  scope: Scope1;
  turnId: Turnid;
}
export interface AgentPayloadReference {
  batchId: Batchid1;
  conversationId: Conversationid7;
  kind: Kind15;
  runId: Runid7;
}
export interface FixedPayloadReference {
  kind: Kind16;
  syncId: Syncid;
}
export interface ProcessingPayloadReference {
  candidateId: Candidateid;
  kind: Kind17;
}
export interface RequestReplayV1 {
  archivedResult: JobSnapshotV1 | null;
  expiresAt: Expiresat2;
  identity: JobIdentity;
  jobId: Jobid5;
  payloadSha256: Payloadsha2563;
}
export interface TemplatePublicationAuthorizationV1 {
  accountGeneration: Accountgeneration3;
  authorityHash: Authorityhash2;
  authorizationId: Authorizationid2;
  deletedCleanup?: DeletedTemplateCleanupV1 | null;
  dependencyHash: Dependencyhash1;
  operationId: Operationid2;
  schemaVersion: Schemaversion20;
  state: State4;
}
export interface DeletedTemplateCleanupV1 {
  captureHash: Capturehash;
  owners: Owners;
  records: Records;
}
export interface Owners {
  [k: string]: LaunchOwner;
}
export interface LaunchOwner {
  generation: Generation2;
  incarnationId: Incarnationid;
  leaseId: Leaseid;
  pid: Pid;
  processStartWitness: Processstartwitness;
  reservationId: Reservationid;
  transportSessionId: Transportsessionid;
  transportTurnId: Transportturnid;
}
export interface AttemptCleanupRecord {
  attemptId: Attemptid;
  evidenceHash: Evidencehash;
  neverDispatched: Neverdispatched;
  ownerHash: Ownerhash;
  verifiedAt: Verifiedat;
  witness: Witness;
}
export interface WriterSessionV1 {
  abandonedEpoch?: Abandonedepoch;
  acknowledgedCursor: Acknowledgedcursor;
  acknowledgedRevision: Acknowledgedrevision1;
  acknowledgedSha256?: Acknowledgedsha256;
  barrierGeneration: Barriergeneration2;
  draftId: Draftid;
  draftSequenceFloor?: Draftsequencefloor;
  epoch: Epoch;
  incarnation: Incarnation5;
  leaseExpiresAt: Leaseexpiresat;
  lineage: Lineage8;
  projectId: Projectid15;
  resumeCredentialSha256: Resumecredentialsha256;
  schemaVersion: Schemaversion21;
  sessionId: Sessionid2;
  status: Status;
  touchFloor?: Touchfloor;
  touchGeneration: Touchgeneration1;
}
export interface WriterTouchReceiptV1 {
  cursor: Cursor1;
  sha256: Sha2562;
}
