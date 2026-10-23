export type Credential = string;
export type Epoch = number;
export type Incarnation = string;
export type Lineage = string;
export type Schemaversion = 1;
export type Sessionid = string;
export type Requestid = string;
export type Schemaversion1 = 2;

export interface WriterRewriteCancelV2 {
  proof: WriterProofV1;
  requestId: Requestid;
  schemaVersion: Schemaversion1;
}
export interface WriterProofV1 {
  credential: Credential;
  epoch: Epoch;
  incarnation: Incarnation;
  lineage: Lineage;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
}
