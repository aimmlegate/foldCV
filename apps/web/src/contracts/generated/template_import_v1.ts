export type Admittedat = string | null;
export type Cellid = string;
export type Fieldkey = string;
export type Periodid = string | null;
export type Discoveryattemptid = string;
export type Discoveryhash = string;
export type Itemhandle = string;
export type Key = string;
export type Operationid = string;
export type Recordid = string;
export type Semantictype = string;
export type Taskid = string;
export type Allocations = HandleAllocation[];
export type Authorizationid = string | null;
export type Evidencehash = string | null;
export type State = "pending" | "verified" | "unknown";
export type Witness = string | null;
export type Dispatchedat = string | null;
export type Errorcode = string | null;
export type Id = string;
export type Inputhash = string;
export type Adapter = string;
export type Capabilityprofile = string;
export type Capabilityversion = string;
export type Configurationhash = string;
export type Effort = string;
export type Model = string;
export type Operationid1 = string;
export type Outcome =
  | (
      | "completed"
      | "invalid_payload"
      | "refused"
      | "incomplete"
      | "timed_out"
      | "cancelled"
      | "transport_failure"
      | "cleanup_failure"
    )
  | null;
export type Generation = number;
export type Incarnationid = string;
export type Leaseid = string;
export type Pid = number | null;
export type Processstartwitness = string | null;
export type Reservationid = string;
export type Transportsessionid = string | null;
export type Transportturnid = string | null;
export type Proposalrecordid = string | null;
export type Rawreturn = string | null;
export type Rawreturnhash = string | null;
export type Requestvalue = {
  [k: string]: JsonValue;
} | null;
export type JsonValue = unknown;
export type Reservedat = string;
export type Returnhash = string | null;
export type Returnedat = string | null;
export type Reviewinputrecordid = string | null;
export type Reviewreceiptid = string | null;
export type Slot = "initial" | "review" | "primary_repair" | "fallback_repair" | "replacement_review";
export type State1 = "reserved" | "dispatch_started" | "returned" | "outcome_unknown" | "reconciled" | "released";
export type Taskid1 = string;
export type Cachedinputtokens = number | null;
export type Complete = boolean;
export type Inputtokens = number | null;
export type Outputtokens = number | null;
export type Attempts = ImportAttempt[];
export type Authorityhash = string;
export type Authorizedat = string;
export type Dependencyhash = string;
export type Id1 = string;
export type Kind = "start" | "resume";
export type State2 = "active" | "cancelled";
export type Authorizations = ImportAuthorization[];
export type Allowtextrewrite = boolean;
export type Authorityhash1 = string;
export type Dependencyhash1 = string;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Packagehash = string;
export type Callcap = number;
export type Cleanupseconds = 5;
export type Concurrency = 1;
export type Fallbackrepairs = 1;
export type Finalizationseconds = number;
export type Primaryrepairs = 1;
export type Processingseconds = number;
export type Itemhandle1 = string;
export type Recordid1 = string;
export type Recordrevision = number;
export type Semanticschemahash = string;
export type Semantictype1 = string;
export type Captureditems = CapturedItemIdentity[];
export type Attemptid = string;
export type Evidencehash1 = string;
export type Neverdispatched = boolean;
export type Ownerhash = string;
export type Verifiedat = string;
export type Witness1 = string;
export type Cleanuprecords = AttemptCleanupRecord[];
export type Clientrequestid = string | null;
export type Expiresat = string | null;
export type Artifacthash = string | null;
export type Assetshash = string;
export type Documenthash = string;
export type Errorcode1 = string | null;
export type Factshash = string;
export type Id2 = string;
export type Packagehash1 = string;
export type Presentationhash = string;
export type Publicationintentid = string | null;
export type Rendererhash = string;
export type State3 = "pending" | "running" | "completed" | "failed";
export type Exportattempts = ExportAttempt[];
export type Authorityhash2 = string;
export type Authorizationid1 = string;
export type Candidatehash = string;
export type Coveragehash = string;
export type Dependencyhash2 = string;
export type Documenthash1 = string;
export type Expiresat1 = string;
export type Factshash1 = string;
export type Id3 = string;
export type Issueshash = string;
export type Operationid2 = string;
export type Packagehash2 = string;
export type Sourcehash = string;
export type Startedat = string;
export type Finalizationhistory = FinalizationCandidate[];
export type Id4 = string;
export type Inferenceclosed = boolean;
export type Blockids = string[];
export type Category = "content_violation" | "uncertain_interpretation" | "check_not_completed";
export type Code = string;
export type Id5 = string;
export type Importedfingerprint = string;
export type Lifecycleid = string;
export type Message = string;
export type Retiredbyaction = string | null;
export type Reviewinputhash = string | null;
export type Ruleid = string | null;
export type State4 = "active" | "retired";
export type Targetids = string[];
export type Taskid2 = string;
export type Issues = ImportIssue[];
export type Lastobservedat = string | null;
export type Projectid = string;
export type Admittedcellids = string[];
export type Admittedrelationids = string[];
export type Appliedreceiptid = string | null;
export type Attemptid1 = string;
export type Errors = string[];
export type Id6 = string;
export type Inputhash1 = string;
export type Attemptid2 = string;
export type Children = string[];
export type Kind1 = "add" | "split" | "merge";
export type Parents = string[];
export type Lineage = Lineage1[];
export type Proposalhash = string;
export type Rawreturn1 = string;
export type Rawreturnhash1 = string;
export type Key1 = string;
export type Pointer = string;
export type Semantictype2 = string;
export type Discoveries = Discovery[];
export type Effectivecellids = string[];
export type End = number;
export type Slicehash = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Start = number;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = SourceSpan[];
export type Fieldkey1 = string;
export type Item = DiscoverySelector | HandleSelector;
export type Key2 = string;
export type Kind2 = "discovery_key";
export type Itemhandle2 = string;
export type Kind3 = "handle";
export type Pointer1 = string;
export type Fields = ProposalField[];
export type Children1 = string[];
export type Kind4 = "add" | "split" | "merge";
export type Parents1 = string[];
export type Lineage2 = ProposalLineage[];
export type Evidence1 = SourceSpan[];
export type Kind5 = "owned_by" | "extension_of" | "related_to";
export type Relation = RelationDiscoverySelector | ExistingRelationSelector;
export type Key3 = string;
export type Kind6 = "discovery_key";
export type Kind7 = "relation_id";
export type Relationid = string;
export type Subject = DiscoverySelector | HandleSelector;
export type Target = DiscoverySelector | HandleSelector;
export type Relations = ProposalRelation[];
export type Schemaversion = 1;
export type Effectivecellids1 = string[];
export type Evidence2 = SourceSpan[];
export type Fieldkey2 = string;
export type Itemhandle3 = string;
export type Pointer2 = string;
export type Resolvedfields = FieldSidecar[];
export type Active = boolean;
export type Id7 = string;
export type Kind8 = "owned_by" | "extension_of" | "related_to";
export type Revision = number;
export type Subjectid = string;
export type Targetid = string;
export type Resolvedrelations = Relation1[];
export type State5 = "invalid" | "provisional" | "accepted" | "rejected";
export type Proposals = ProposalRecord[];
export type Errorcode2 = string | null;
export type Intentid = string | null;
export type State6 = "pending" | "saved" | "failed_before_replacement" | "outcome_unknown" | "cancelled";
export type Workspacehash = string | null;
export type Attemptid3 = string;
export type Completedat = string;
export type Ruleid1 = string;
export type Targetid1 = string;
export type Expectedchecks = CheckTarget[];
export type Id8 = string;
export type Actionable = boolean;
export type Disposition = "satisfied" | "violation" | "uncertain";
export type Evidence3 = SourceSpan[];
export type Reason = string;
export type Ruleid2 = string;
export type Targetid2 = string;
export type Results = ReviewDisposition[];
export type Reviewinputhash1 = string;
export type Receipts = ReviewReceipt[];
export type Discoveryattemptid1 = string;
export type Key4 = string;
export type Kind9 = "owned_by" | "extension_of" | "related_to";
export type Operationid3 = string;
export type Relationid1 = string;
export type Subjectid1 = string;
export type Targetid3 = string;
export type Taskid3 = string;
export type Relationallocations = RelationAllocation[];
export type Attemptid4 = string;
export type Id9 = string;
export type Inputhash2 = string;
export type Allowtextrewrite1 = boolean;
export type Admissionreceiptids = string[];
export type Evidence4 = SourceSpan[];
export type Fieldkey3 = string;
export type Id10 = string;
export type Manualscopeid = string | null;
export type Observationids = string[];
export type Origin = "model" | "source" | "human";
export type Rawinput = string;
export type Revision1 = number;
export type State7 = "admitted" | "human_raw" | "pending_manual" | "uncertain";
export type Usercorrected = boolean;
export type Effectivecells = ExtensionCell[];
export type Ref = string;
export type Text = string;
export type Evidence5 = EvidenceOption[];
export type Handlemap = (HandleAllocation | CapturedItemIdentity)[];
export type Occurrenceindependent = boolean;
export type Packagehash3 = string;
export type Proposalhash1 = string;
export type Protocol = "template_import_v1";
export type Relations1 = Relation1[];
export type Id11 = string;
export type Kind10 =
  | "content_schema"
  | "evidence_identity"
  | "protected_values"
  | "claim_ownership"
  | "complete_assignment"
  | "semantic_support"
  | "task_result_separation"
  | "attribution";
export type Fields1 = string[];
export type Instructions = string[];
export type Version = 1;
export type Rules = Check[];
export type Schemaversion1 = 1 | 2;
export type Sourcespans = SourceSpan[];
export type Targets = CheckTarget[];
export type Reviewinputs = ReviewInputRecord[];
export type Schemaversion2 = 1;
export type State8 =
  "captured" | "processing" | "cleanup_pending" | "finalizing" | "published" | "cancelled" | "failed" | "fenced";
export type Capturedat = string;
export type Id12 = string;
export type Inputhash3 = string;
export type Taskid4 = string;
export type Taskinputs = TaskInputRecord[];
export type Disposition1 = "admitted" | "derived" | "source_fallback" | "empty";
export type Id13 = string;
export type Inputhash4 = string;
export type Issueids = string[];
export type Itemhandles = string[];
export type Sourcespans1 = SourceSpan[];
export type Taskid5 = string;
export type Taskresults = TaskResultRecord[];
export type Allowedhandles = string[];
export type Attemptids = string[];
export type Blockid = string;
export type Dependencies = string[];
export type Expectedchecks1 = CheckTarget[];
export type Id14 = string;
export type Inputhash5 = string;
export type Issueids1 = string[];
export type Kind11 = "extract" | "rewrite" | "derive" | "source_copy";
export type Operationid4 = string;
export type Proposalhash2 = string | null;
export type Receiptids = string[];
export type State9 =
  | "pending"
  | "running"
  | "proposed"
  | "checking"
  | "repairing"
  | "accepted"
  | "empty"
  | "source_fallback"
  | "cancelled"
  | "technical_failure";
export type Tasks = ImportTask[];

export interface ImportOperation {
  admittedAt: Admittedat;
  allocations: Allocations;
  attempts: Attempts;
  authorizations?: Authorizations;
  capture: ImportCapture;
  capturedItems?: Captureditems;
  capturedRelationRevisions?: Capturedrelationrevisions;
  cleanupRecords?: Cleanuprecords;
  clientRequestId?: Clientrequestid;
  expiresAt: Expiresat;
  exportAttempts: Exportattempts;
  finalization: FinalizationCandidate | null;
  finalizationHistory?: Finalizationhistory;
  id: Id4;
  inferenceClosed?: Inferenceclosed;
  issues?: Issues;
  lastObservedAt: Lastobservedat;
  projectId: Projectid;
  proposals: Proposals;
  publication: PublicationOutcome;
  receipts: Receipts;
  relationAllocations?: Relationallocations;
  reviewInputs: Reviewinputs;
  schemaVersion: Schemaversion2;
  state: State8;
  taskInputs?: Taskinputs;
  taskResults?: Taskresults;
  tasks: Tasks;
}
export interface HandleAllocation {
  canonicalFields?: Canonicalfields;
  cellIds: Cellids;
  discoveryAttemptId: Discoveryattemptid;
  discoveryHash: Discoveryhash;
  itemHandle: Itemhandle;
  key: Key;
  operationId: Operationid;
  periodIds?: Periodids;
  recordId: Recordid;
  semanticType: Semantictype;
  taskId: Taskid;
}
export interface Canonicalfields {
  [k: string]: CanonicalFieldBinding;
}
export interface CanonicalFieldBinding {
  cellId: Cellid;
  fieldKey: Fieldkey;
  periodId: Periodid;
}
export interface Cellids {
  [k: string]: string;
}
export interface Periodids {
  [k: string]: string;
}
export interface ImportAttempt {
  authorizationId?: Authorizationid;
  cleanup: CleanupOutcome;
  dispatchedAt: Dispatchedat;
  errorCode?: Errorcode;
  id: Id;
  inputHash: Inputhash;
  model: ModelCapture;
  operationId: Operationid1;
  outcome?: Outcome;
  owner: LaunchOwner;
  proposalRecordId: Proposalrecordid;
  rawReturn: Rawreturn;
  rawReturnHash: Rawreturnhash;
  requestValue?: Requestvalue;
  reservedAt: Reservedat;
  returnHash: Returnhash;
  returnedAt?: Returnedat;
  reviewInputRecordId: Reviewinputrecordid;
  reviewReceiptId: Reviewreceiptid;
  slot: Slot;
  state: State1;
  taskId: Taskid1;
  usage: ObservedUsage;
}
export interface CleanupOutcome {
  evidenceHash: Evidencehash;
  state: State;
  witness: Witness;
}
export interface ModelCapture {
  adapter: Adapter;
  capabilityProfile: Capabilityprofile;
  capabilityVersion: Capabilityversion;
  configurationHash: Configurationhash;
  effort: Effort;
  model: Model;
}
export interface LaunchOwner {
  generation: Generation;
  incarnationId: Incarnationid;
  leaseId: Leaseid;
  pid: Pid;
  processStartWitness: Processstartwitness;
  reservationId: Reservationid;
  transportSessionId: Transportsessionid;
  transportTurnId: Transportturnid;
}
export interface ObservedUsage {
  cachedInputTokens: Cachedinputtokens;
  complete: Complete;
  inputTokens: Inputtokens;
  outputTokens: Outputtokens;
}
export interface ImportAuthorization {
  authorityHash: Authorityhash;
  authorizedAt: Authorizedat;
  dependencyHash: Dependencyhash;
  id: Id1;
  kind: Kind;
  state: State2;
}
export interface ImportCapture {
  allowTextRewrite: Allowtextrewrite;
  authorityHash: Authorityhash1;
  dependencyHash: Dependencyhash1;
  factRevisions: Factrevisions;
  fallback: ModelCapture | null;
  formattingAsOf: PartialDate;
  packageHash: Packagehash;
  policy: RuntimePolicy;
  primary: ModelCapture;
  sourceHashes: Sourcehashes;
}
export interface Factrevisions {
  [k: string]: number;
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
export interface CapturedItemIdentity {
  canonicalFields?: Canonicalfields1;
  cellIds: Cellids1;
  itemHandle: Itemhandle1;
  periodIds?: Periodids1;
  recordId: Recordid1;
  recordRevision: Recordrevision;
  semanticSchemaHash: Semanticschemahash;
  semanticType: Semantictype1;
}
export interface Canonicalfields1 {
  [k: string]: CanonicalFieldBinding;
}
export interface Cellids1 {
  [k: string]: string;
}
export interface Periodids1 {
  [k: string]: string;
}
export interface Capturedrelationrevisions {
  [k: string]: number;
}
export interface AttemptCleanupRecord {
  attemptId: Attemptid;
  evidenceHash: Evidencehash1;
  neverDispatched: Neverdispatched;
  ownerHash: Ownerhash;
  verifiedAt: Verifiedat;
  witness: Witness1;
}
export interface ExportAttempt {
  artifactHash: Artifacthash;
  assetsHash: Assetshash;
  documentHash: Documenthash;
  errorCode: Errorcode1;
  factsHash: Factshash;
  id: Id2;
  packageHash: Packagehash1;
  presentationHash: Presentationhash;
  publicationIntentId: Publicationintentid;
  rendererHash: Rendererhash;
  state: State3;
}
export interface FinalizationCandidate {
  authorityHash: Authorityhash2;
  authorizationId: Authorizationid1;
  candidateHash: Candidatehash;
  coverageHash: Coveragehash;
  dependencyHash: Dependencyhash2;
  documentHash: Documenthash1;
  expiresAt: Expiresat1;
  factsHash: Factshash1;
  id: Id3;
  issuesHash: Issueshash;
  operationId: Operationid2;
  packageHash: Packagehash2;
  sourceHash: Sourcehash;
  startedAt: Startedat;
}
export interface ImportIssue {
  blockIds: Blockids;
  category: Category;
  code: Code;
  id: Id5;
  importedFingerprint: Importedfingerprint;
  lifecycleId: Lifecycleid;
  message: Message;
  retiredByAction: Retiredbyaction;
  reviewInputHash: Reviewinputhash;
  ruleId: Ruleid;
  state: State4;
  targetIds: Targetids;
  taskId: Taskid2;
}
export interface ProposalRecord {
  admittedCellIds?: Admittedcellids;
  admittedRecordRevisions?: Admittedrecordrevisions;
  admittedRelationIds?: Admittedrelationids;
  admittedRelationRevisions?: Admittedrelationrevisions;
  appliedReceiptId?: Appliedreceiptid;
  attemptId: Attemptid1;
  errors: Errors;
  id: Id6;
  inputHash: Inputhash1;
  lineage: Lineage;
  proposalHash: Proposalhash;
  rawReturn: Rawreturn1;
  rawReturnHash: Rawreturnhash1;
  reply: ProposalReply | null;
  resolvedFields: Resolvedfields;
  resolvedRelations?: Resolvedrelations;
  state: State5;
}
export interface Admittedrecordrevisions {
  [k: string]: number;
}
export interface Admittedrelationrevisions {
  [k: string]: number;
}
export interface Lineage1 {
  attemptId: Attemptid2;
  children: Children;
  kind: Kind1;
  parents: Parents;
}
export interface ProposalReply {
  discoveries: Discoveries;
  fields: Fields;
  lineage: Lineage2;
  payload: JsonValue;
  relations?: Relations;
  schemaVersion: Schemaversion;
}
export interface Discovery {
  key: Key1;
  pointer: Pointer;
  semanticType: Semantictype2;
}
export interface ProposalField {
  effectiveCellIds: Effectivecellids;
  evidence: Evidence;
  fieldKey: Fieldkey1;
  item: Item;
  pointer: Pointer1;
}
export interface SourceSpan {
  end: End;
  sliceHash: Slicehash;
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  start: Start;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface DiscoverySelector {
  key: Key2;
  kind: Kind2;
}
export interface HandleSelector {
  itemHandle: Itemhandle2;
  kind: Kind3;
}
export interface ProposalLineage {
  children: Children1;
  kind: Kind4;
  parents: Parents1;
}
export interface ProposalRelation {
  evidence: Evidence1;
  kind: Kind5;
  relation: Relation;
  subject: Subject;
  target: Target;
}
export interface RelationDiscoverySelector {
  key: Key3;
  kind: Kind6;
}
export interface ExistingRelationSelector {
  kind: Kind7;
  relationId: Relationid;
}
export interface FieldSidecar {
  effectiveCellIds: Effectivecellids1;
  evidence: Evidence2;
  fieldKey: Fieldkey2;
  itemHandle: Itemhandle3;
  pointer: Pointer2;
}
export interface Relation1 {
  active: Active;
  id: Id7;
  kind: Kind8;
  revision: Revision;
  subjectId: Subjectid;
  targetId: Targetid;
}
export interface PublicationOutcome {
  errorCode: Errorcode2;
  intentId: Intentid;
  state: State6;
  workspaceHash: Workspacehash;
}
export interface ReviewReceipt {
  attemptId: Attemptid3;
  completedAt: Completedat;
  expectedChecks: Expectedchecks;
  id: Id8;
  reply: ReviewReply;
  reviewInputHash: Reviewinputhash1;
}
export interface CheckTarget {
  ruleId: Ruleid1;
  targetId: Targetid1;
}
export interface ReviewReply {
  results: Results;
}
export interface ReviewDisposition {
  actionable: Actionable;
  disposition: Disposition;
  evidence: Evidence3;
  reason: Reason;
  ruleId: Ruleid2;
  targetId: Targetid2;
}
export interface RelationAllocation {
  discoveryAttemptId: Discoveryattemptid1;
  key: Key4;
  kind: Kind9;
  operationId: Operationid3;
  relationId: Relationid1;
  subjectId: Subjectid1;
  targetId: Targetid3;
  taskId: Taskid3;
}
export interface ReviewInputRecord {
  attemptId: Attemptid4;
  id: Id9;
  inputHash: Inputhash2;
  value: ReviewInput;
}
export interface ReviewInput {
  allowTextRewrite: Allowtextrewrite1;
  effectiveCells: Effectivecells;
  evidence?: Evidence5;
  handleMap: Handlemap;
  occurrenceContext: JsonValue;
  occurrenceIndependent: Occurrenceindependent;
  packageHash: Packagehash3;
  policy: ModelCapture;
  proposalHash: Proposalhash1;
  protocol: Protocol;
  relations: Relations1;
  rules: Rules;
  schemaVersion: Schemaversion1;
  semanticContext: Semanticcontext;
  sourceSpans: Sourcespans;
  sourceTexts: Sourcetexts;
  targets: Targets;
}
export interface ExtensionCell {
  admissionReceiptIds: Admissionreceiptids;
  evidence: Evidence4;
  fieldKey: Fieldkey3;
  id: Id10;
  manualScopeId: Manualscopeid;
  observationIds: Observationids;
  origin: Origin;
  rawInput: Rawinput;
  revision: Revision1;
  state: State7;
  typedValue: JsonValue;
  userCorrected: Usercorrected;
}
export interface EvidenceOption {
  ref: Ref;
  span: SourceSpan;
  text: Text;
}
export interface Check {
  id: Id11;
  kind: Kind10;
  parameters: CheckParameters;
  version: Version;
}
export interface CheckParameters {
  fields: Fields1;
  instructions: Instructions;
}
export interface Semanticcontext {
  [k: string]: JsonValue;
}
export interface Sourcetexts {
  [k: string]: string;
}
export interface TaskInputRecord {
  capturedAt: Capturedat;
  id: Id12;
  inputHash: Inputhash3;
  taskId: Taskid4;
  value: Value;
}
export interface Value {
  [k: string]: JsonValue;
}
export interface TaskResultRecord {
  disposition: Disposition1;
  id: Id13;
  inputHash: Inputhash4;
  issueIds: Issueids;
  itemHandles: Itemhandles;
  sourceSpans: Sourcespans1;
  taskId: Taskid5;
  value: JsonValue;
}
export interface ImportTask {
  allowedHandles: Allowedhandles;
  attemptIds: Attemptids;
  blockId: Blockid;
  dependencies: Dependencies;
  expectedChecks: Expectedchecks1;
  id: Id14;
  inputHash: Inputhash5;
  issueIds: Issueids1;
  kind: Kind11;
  operationId: Operationid4;
  proposalHash: Proposalhash2;
  receiptIds: Receiptids;
  state: State9;
}
