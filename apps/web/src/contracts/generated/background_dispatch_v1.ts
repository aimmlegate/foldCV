export type Accountgeneration = number;
export type Paused = ("RATE_LIMITED" | "AUTH_REQUIRED") | null;
export type Schemaversion = 1;

export interface DispatchStateV1 {
  accountGeneration: Accountgeneration;
  paused: Paused;
  schemaVersion: Schemaversion;
}
