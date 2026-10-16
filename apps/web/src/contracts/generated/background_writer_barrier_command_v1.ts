export type Generation = number;
export type Credential = string;
export type Epoch = number;
export type Incarnation = string;
export type Lineage = string;
export type Schemaversion = 1;
export type Sessionid = string;
export type Schemaversion1 = 1;
export type Token = string;

export interface WriterBarrierCommandV1 {
  generation: Generation;
  proof: WriterProofV1;
  schemaVersion: Schemaversion1;
  token: Token;
}
export interface WriterProofV1 {
  credential: Credential;
  epoch: Epoch;
  incarnation: Incarnation;
  lineage: Lineage;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
}
