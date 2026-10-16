export type Id = string;
export type Credential = string;
export type Epoch = number;
export type Incarnation = string;
export type Lineage = string;
export type Schemaversion = 1;
export type Sessionid = string;
export type Schemaversion1 = 1;

export interface WriterDraftReferenceV1 {
  id: Id;
  proof: WriterProofV1;
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
