export type Actioncursor = number;
export type Assetpinssha256 = string | null;
export type Baserevision = number;
export type Basesha256 = string;
export type Checkpointedat = string;
export type Id = string;
export type Incarnation = string;
export type Lineage = string;
export type Payloadbytes = number;
export type Payloadref = string;
export type Payloadsha256 = string;
export type Projectid = string;
export type Schemaversion = 1;
export type Sequence = number;
export type Fingerprint = string;
export type Generation = number;
export type Key = string;
export type Kind = "entity" | "structure" | "query" | "source" | "rules";
/**
 * @maxItems 100
 */
export type Touches = GenerationStamp[];
export type Writerepoch = number;

export interface DraftCheckpointV1 {
  actionCursor: Actioncursor;
  assetPinsSha256?: Assetpinssha256;
  baseRevision: Baserevision;
  baseSha256: Basesha256;
  checkpointedAt: Checkpointedat;
  id: Id;
  incarnation: Incarnation;
  lineage: Lineage;
  payloadBytes: Payloadbytes;
  payloadRef: Payloadref;
  payloadSha256: Payloadsha256;
  projectId: Projectid;
  schemaVersion: Schemaversion;
  sequence: Sequence;
  touches: Touches;
  writerEpoch: Writerepoch;
}
export interface GenerationStamp {
  fingerprint: Fingerprint;
  generation: Generation;
  key: Key;
  kind: Kind;
}
