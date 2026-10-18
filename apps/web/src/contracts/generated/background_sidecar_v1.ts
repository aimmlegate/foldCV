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
export type Id4 = string;
export type Nativestarted = boolean;
export type Schemaversion6 = 1;
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
export type Id5 = string;
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
export type Projectid3 = string;
export type Projectrevision = number;
export type Proposalid4 = string;
export type Proposalsha256 = string;
export type Requestsha2562 = string;
export type Schemaversion7 = 1;
export type Workspacesha2561 = string;
export type Schemaversion8 = 1;
export type Accessrevision = number;
export type Accountgeneration1 = number;
export type Allowedits = boolean;
export type Allowweb = boolean;
export type Lineage4 = string;
export type Projectid4 = string;
export type Requestepoch1 = number;
export type Requestid = string;
export type Id6 = string;
export type Kind7 = "agent_journal" | "rich_sync" | "processing";
export type Sha2561 = string;
export type Kind8 = "agent" | "processing" | "rewrite" | "reconciliation";
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
export type Schemaversion9 = 1;
export type Scope = WholeResumeScope | SelectionScope;
export type Kind9 = "resume";
export type Kind10 = "selection";
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
export type Kind11 = "text" | "blocks" | "table_cells";
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
export type Id7 = string;
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
export type Projectid5 = string;
export type Requestsha2563 = string;
export type Resolvedat1 = string | null;
export type Schemaversion10 = 1;
export type Stepssha256 = string | null;
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
export type Projectid6 = string;
export type Acceptedat = string;
export type Accountgeneration2 = number;
export type Authority = "active" | "revoked";
export type Executiondeadline = string;
export type Executiongeneration2 = number;
export type Id8 = string;
export type Jobid4 = string;
export type Lineage7 = string;
export type Payload = AgentPayloadReference | FixedPayloadReference | ProcessingPayloadReference;
export type Batchid = string;
export type Conversationid = string;
export type Kind12 = "agent_journal";
export type Runid = string;
export type Kind13 = "rich_sync";
export type Syncid = string;
export type Candidateid = string;
export type Kind14 = "processing";
export type Payloadbytes1 = number;
export type Payloadsha2562 = string;
export type Projectid7 = string;
export type Revocation = ("stop" | "discard" | "superseded" | "deleted" | "account_changed") | null;
export type Schemaversion11 = 1;
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
export type Schemaversion12 = 1;
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
export type Projectid8 = string;
export type Resumecredentialsha256 = string;
export type Schemaversion13 = 1;
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
  projectId: Projectid6;
  proposals: Proposals;
  requestEpochExpiresAt: Requestepochexpiresat;
  requests: Requests;
  schemaVersion: Schemaversion12;
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
  assetPinsSha256?: Assetpinssha2562;
  attempts: Attempts;
  captureInvalidated?: Captureinvalidated;
  createdAt: Createdat;
  error: JobFailure | null;
  eventCursor: Eventcursor;
  execution: Execution;
  executionGeneration: Executiongeneration1;
  id: Id5;
  proposalId: Proposalid3;
  publication: Publication;
  publicationError?: JobFailure | null;
  receipt: CanonicalReceiptV1 | null;
  schemaVersion: Schemaversion8;
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
  id: Id4;
  nativeStarted: Nativestarted;
  schemaVersion: Schemaversion6;
  stage: Stage;
  startupDeadline: Startupdeadline;
  state: State1;
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
  projectId: Projectid3;
  projectRevision: Projectrevision;
  proposalId: Proposalid4;
  proposalSha256: Proposalsha256;
  requestSha256: Requestsha2562;
  schemaVersion: Schemaversion7;
  workspaceSha256: Workspacesha2561;
}
export interface JobSubmissionV1 {
  accessRevision?: Accessrevision;
  accountGeneration: Accountgeneration1;
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  guards: ScopeGuardV1;
  identity: JobIdentity;
  input: InputReference;
  kind: Kind8;
  models: Models;
  payloadSha256: Payloadsha2561;
  schedulingClass: Schedulingclass;
  schemaVersion: Schemaversion9;
  scope: Scope;
  submittedAt: Submittedat;
  tools: Tools;
}
export interface JobIdentity {
  lineage: Lineage4;
  projectId: Projectid4;
  requestEpoch: Requestepoch1;
  requestId: Requestid;
}
export interface InputReference {
  id: Id6;
  kind: Kind7;
  sha256: Sha2561;
}
export interface ModelCapture {
  configSha256: Configsha256;
  model: Model;
  stage: Stage1;
}
export interface WholeResumeScope {
  kind: Kind9;
}
export interface SelectionScope {
  kind: Kind10;
  selection: RichSelection;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind11;
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
  id: Id7;
  incarnation: Incarnation4;
  lineage: Lineage6;
  phase: Phase2;
  previousRef: Previousref1;
  projectId: Projectid5;
  reconciledReason?: JobFailure | null;
  requestSha256: Requestsha2563;
  resolvedAt?: Resolvedat1;
  schemaVersion: Schemaversion10;
  stepsSha256?: Stepssha256;
  writerEpoch: Writerepoch4;
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
  id: Id8;
  jobId: Jobid4;
  lineage: Lineage7;
  payload: Payload;
  payloadBytes: Payloadbytes1;
  payloadSha256: Payloadsha2562;
  projectId: Projectid7;
  revocation: Revocation;
  schemaVersion: Schemaversion11;
  scope: Scope1;
  turnId: Turnid;
}
export interface AgentPayloadReference {
  batchId: Batchid;
  conversationId: Conversationid;
  kind: Kind12;
  runId: Runid;
}
export interface FixedPayloadReference {
  kind: Kind13;
  syncId: Syncid;
}
export interface ProcessingPayloadReference {
  candidateId: Candidateid;
  kind: Kind14;
}
export interface RequestReplayV1 {
  archivedResult: JobSnapshotV1 | null;
  expiresAt: Expiresat2;
  identity: JobIdentity;
  jobId: Jobid5;
  payloadSha256: Payloadsha2563;
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
  projectId: Projectid8;
  resumeCredentialSha256: Resumecredentialsha256;
  schemaVersion: Schemaversion13;
  sessionId: Sessionid2;
  status: Status;
  touchFloor?: Touchfloor;
  touchGeneration: Touchgeneration1;
}
export interface WriterTouchReceiptV1 {
  cursor: Cursor1;
  sha256: Sha2562;
}
