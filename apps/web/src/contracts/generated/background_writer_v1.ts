export type Abandonedepoch = number | null;
export type Acknowledgedcursor = number;
export type Acknowledgedrevision = number;
export type Acknowledgedsha256 = string | null;
export type Barriergeneration = number;
export type Draftid = string | null;
export type Draftsequencefloor = number;
export type Epoch = number;
export type Incarnation = string;
export type Leaseexpiresat = string;
export type Lineage = string;
export type Projectid = string;
export type Resumecredentialsha256 = string;
export type Schemaversion = 1;
export type Sessionid = string;
export type Status = "attached" | "recovering" | "clean_detached" | "fenced";
export type Touchfloor = number;
export type Touchgeneration = number;

export interface WriterSessionV1 {
  abandonedEpoch?: Abandonedepoch;
  acknowledgedCursor: Acknowledgedcursor;
  acknowledgedRevision: Acknowledgedrevision;
  acknowledgedSha256?: Acknowledgedsha256;
  barrierGeneration: Barriergeneration;
  draftId: Draftid;
  draftSequenceFloor?: Draftsequencefloor;
  epoch: Epoch;
  incarnation: Incarnation;
  leaseExpiresAt: Leaseexpiresat;
  lineage: Lineage;
  projectId: Projectid;
  resumeCredentialSha256: Resumecredentialsha256;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
  status: Status;
  touchFloor?: Touchfloor;
  touchGeneration: Touchgeneration;
}
