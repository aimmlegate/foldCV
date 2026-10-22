export type WriterPreparedSaveResultV2 = WriterPreparedSaveAckV2 | WriterPreparedSaveRecoveryV2;
export type Clientmutationid = string;
export type Actioncursor = number;
export type Draftid = string | null;
export type Draftsequence = number | null;
export type Draftsha256 = string | null;
export type Epoch = number;
export type Incarnation = string;
export type Touchgeneration = number;
export type Kind = "set";
export type Pointer = string;
export type Valuewire = string;
export type Kind1 = "insert";
export type Pointer1 = string;
export type Valuewire1 = string;
export type Kind2 = "remove";
export type Pointer2 = string;
export type Beforetexthash = string;
export type End = number;
export type Kind3 = "splice_text";
export type Pointer3 = string;
export type Start = number;
export type Text = string;
/**
 * @maxItems 1000
 */
export type Commitpatch = (PatchSet | PatchInsert | PatchRemove | PatchSpliceText)[];
export type Errorcode = string | null;
export type Id = string;
export type Stage = "assess_resume" | "normalize_semantics" | "draft_prose" | "assemble" | "render";
export type Startedat = string | null;
export type Status = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Subtitle = string;
export type Title = string;
export type Documenthash = string;
export type Documentrevision = number;
export type Factshash = string;
export type Packagehash = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;
export type Committedworkspacesha256 = string;
export type Currentcanonicalrevision = number;
export type Currentcanonicalsha256 = string;
export type Currentequalscommitted = boolean;
export type Kind4 = "committed";
export type Actionid = string;
export type Generation = number;
export type Mutationsha256 = string;
export type Preparationrequesthash = string;
export type Preparedworkspacesha256 = string;
export type Clientmutationid1 = string;
export type Requestsha256 = string;
export type Resultingrevision = number;
export type Replayed = boolean;
export type Schemaversion = 2;
export type Abandonedepoch = number | null;
export type Acknowledgedcursor = number;
export type Acknowledgedrevision = number;
export type Acknowledgedsha256 = string | null;
export type Barriergeneration = number;
export type Draftid1 = string | null;
export type Draftsequencefloor = number;
export type Epoch1 = number;
export type Incarnation1 = string;
export type Leaseexpiresat = string;
export type Lineage = string;
export type Projectid1 = string;
export type Resumecredentialsha256 = string;
export type Schemaversion1 = 1;
export type Sessionid = string;
export type Status1 = "attached" | "recovering" | "clean_detached" | "fenced";
export type Touchfloor = number;
export type Touchgeneration1 = number;
export type Clientmutationid2 = string;
export type Currentcanonicalrevision1 = number;
export type Currentcanonicalsha2561 = string;
export type Kind5 = "committed_recovery_required";
export type Mutationsha2561 = string;
export type Preparationrequesthash1 = string;
export type Reason = "compact_commit_proof_expired";
export type Schemaversion2 = 2;

export interface WriterPreparedSaveAckV2 {
  clientMutationId: Clientmutationid;
  commitBinding: WriterCommitBindingV1;
  commitPatch: Commitpatch;
  committedGeneration: RichGenerationState | null;
  committedIdentity: ResumeIdentity | null;
  committedSnapshot: TemplateSnapshotIdentity;
  committedWorkspaceSha256: Committedworkspacesha256;
  currentCanonicalRevision: Currentcanonicalrevision;
  currentCanonicalSha256: Currentcanonicalsha256;
  currentEqualsCommitted: Currentequalscommitted;
  kind: Kind4;
  localHistoryAck: LocalHistoryAckV2 | null;
  mutationSha256: Mutationsha256;
  preparationRequestHash: Preparationrequesthash;
  preparedWorkspaceSha256: Preparedworkspacesha256;
  replay: RichMutationReplay;
  replayed: Replayed;
  schemaVersion: Schemaversion;
  writer: WriterSessionV1;
}
export interface WriterCommitBindingV1 {
  actionCursor: Actioncursor;
  draftId?: Draftid;
  draftSequence?: Draftsequence;
  draftSha256?: Draftsha256;
  epoch: Epoch;
  incarnation: Incarnation;
  touchGeneration: Touchgeneration;
}
export interface PatchSet {
  kind: Kind;
  pointer: Pointer;
  valueWire: Valuewire;
}
export interface PatchInsert {
  kind: Kind1;
  pointer: Pointer1;
  valueWire: Valuewire1;
}
export interface PatchRemove {
  kind: Kind2;
  pointer: Pointer2;
}
export interface PatchSpliceText {
  beforeTextHash: Beforetexthash;
  end: End;
  kind: Kind3;
  pointer: Pointer3;
  start: Start;
  text: Text;
}
export interface RichGenerationState {
  errorCode: Errorcode;
  id: Id;
  stage: Stage;
  startedAt?: Startedat;
  status: Status;
}
export interface ResumeIdentity {
  subtitle: Subtitle;
  title: Title;
}
export interface TemplateSnapshotIdentity {
  documentHash: Documenthash;
  documentRevision: Documentrevision;
  factsHash: Factshash;
  packageHash: Packagehash;
  presentationHash: Presentationhash;
  projectId: Projectid;
  projectRevision: Projectrevision;
}
export interface LocalHistoryAckV2 {
  actionId: Actionid;
  generation: Generation;
}
export interface RichMutationReplay {
  clientMutationId: Clientmutationid1;
  requestSha256: Requestsha256;
  resultingRevision: Resultingrevision;
}
export interface WriterSessionV1 {
  abandonedEpoch?: Abandonedepoch;
  acknowledgedCursor: Acknowledgedcursor;
  acknowledgedRevision: Acknowledgedrevision;
  acknowledgedSha256?: Acknowledgedsha256;
  barrierGeneration: Barriergeneration;
  draftId: Draftid1;
  draftSequenceFloor?: Draftsequencefloor;
  epoch: Epoch1;
  incarnation: Incarnation1;
  leaseExpiresAt: Leaseexpiresat;
  lineage: Lineage;
  projectId: Projectid1;
  resumeCredentialSha256: Resumecredentialsha256;
  schemaVersion: Schemaversion1;
  sessionId: Sessionid;
  status: Status1;
  touchFloor?: Touchfloor;
  touchGeneration: Touchgeneration1;
}
export interface WriterPreparedSaveRecoveryV2 {
  clientMutationId: Clientmutationid2;
  currentCanonicalRevision: Currentcanonicalrevision1;
  currentCanonicalSha256: Currentcanonicalsha2561;
  kind: Kind5;
  mutationSha256: Mutationsha2561;
  preparationRequestHash: Preparationrequesthash1;
  reason: Reason;
  replay: RichMutationReplay;
  schemaVersion: Schemaversion2;
  writer: WriterSessionV1;
}
