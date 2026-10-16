export type Credential = string;
export type Epoch = number;
export type Incarnation = string;
export type Lineage = string;
export type Schemaversion = 1;
export type Sessionid = string;

export interface WriterProofV1 {
  credential: Credential;
  epoch: Epoch;
  incarnation: Incarnation;
  lineage: Lineage;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
}
