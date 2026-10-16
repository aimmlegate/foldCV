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
export type Requestsha256 = string;
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
  requestSha256: Requestsha256;
  schemaVersion: Schemaversion;
  writerEpoch: Writerepoch;
}
