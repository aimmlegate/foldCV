export type Acknowledgedcursor = number;
export type Acknowledgedrevision = number;
export type Barriergeneration = number;
export type Draftid = string | null;
export type Epoch = number;
export type Incarnation = string;
export type Leaseexpiresat = string;
export type Lineage = string;
export type Projectid = string;
export type Resumecredentialsha256 = string;
export type Schemaversion = 1;
export type Sessionid = string;
export type Status = "attached" | "recovering" | "clean_detached" | "fenced";
export type Touchgeneration = number;

export interface WriterSessionV1 {
  acknowledgedCursor: Acknowledgedcursor;
  acknowledgedRevision: Acknowledgedrevision;
  barrierGeneration: Barriergeneration;
  draftId: Draftid;
  epoch: Epoch;
  incarnation: Incarnation;
  leaseExpiresAt: Leaseexpiresat;
  lineage: Lineage;
  projectId: Projectid;
  resumeCredentialSha256: Resumecredentialsha256;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
  status: Status;
  touchGeneration: Touchgeneration;
}
