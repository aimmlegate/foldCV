export type Clientmutationid = string;
export type Documentrevision = number;
export type Durable = true;
export type Factsrevision = number;
export type Generationssha256 = string;
export type Jobid = string;
export type Lineage = string;
export type Persistedat = string;
export type Projectid = string;
export type Projectrevision = number;
export type Proposalid = string;
export type Proposalsha256 = string;
export type Requestsha256 = string;
export type Schemaversion = 1;
export type Workspacesha256 = string;

export interface CanonicalReceiptV1 {
  clientMutationId: Clientmutationid;
  documentRevision: Documentrevision;
  durable: Durable;
  factsRevision: Factsrevision;
  generationsSha256: Generationssha256;
  jobId: Jobid;
  lineage: Lineage;
  persistedAt: Persistedat;
  projectId: Projectid;
  projectRevision: Projectrevision;
  proposalId: Proposalid;
  proposalSha256: Proposalsha256;
  requestSha256: Requestsha256;
  schemaVersion: Schemaversion;
  workspaceSha256: Workspacesha256;
}
