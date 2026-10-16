export type Expiresat = string;
export type Fingerprint = string;
export type Generation = number;
export type Key = string;
export type Kind = "entity" | "structure" | "query" | "source" | "rules";
/**
 * @maxItems 100
 */
export type Reads = GenerationStamp[];
export type Schemaversion = 1;
/**
 * @maxItems 100
 */
export type Writes = GenerationStamp[];
export type Incarnation = string | null;
export type Inversebytes = number;
export type Inverseref = string;
export type Inversesha256 = string;
export type Jobid = string;
export type Owner = "session" | "backend" | "transferring" | "expired";
export type Proposalid = string;
export type Schemaversion1 = 1;
export type Transferid = string;
export type Writerepoch = number | null;

export interface UndoOwnershipV1 {
  expiresAt: Expiresat;
  guards: ScopeGuardV1;
  incarnation: Incarnation;
  inverseBytes: Inversebytes;
  inverseRef: Inverseref;
  inverseSha256: Inversesha256;
  jobId: Jobid;
  owner: Owner;
  proposalId: Proposalid;
  schemaVersion: Schemaversion1;
  transferId: Transferid;
  writerEpoch: Writerepoch;
}
export interface ScopeGuardV1 {
  reads: Reads;
  schemaVersion: Schemaversion;
  writes: Writes;
}
export interface GenerationStamp {
  fingerprint: Fingerprint;
  generation: Generation;
  key: Key;
  kind: Kind;
}
