export type After = number;
export type Generation = number;
export type Schemaversion = 1;

export interface JobReplayRequestV1 {
  after: After;
  generation: Generation;
  schemaVersion: Schemaversion;
}
