export type Cancelled = boolean;
export type Requestid = string;
export type Schemaversion = 2;

export interface WriterRewriteCancelResultV2 {
  cancelled: Cancelled;
  requestId: Requestid;
  schemaVersion: Schemaversion;
}
