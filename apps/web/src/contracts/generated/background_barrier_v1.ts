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
