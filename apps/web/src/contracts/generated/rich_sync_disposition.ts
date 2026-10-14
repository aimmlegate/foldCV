export type Errorcode = string | null;
export type Status = "applied" | "stale" | "conflict";

export interface RichSyncDisposition {
  errorCode?: Errorcode;
  status: Status;
}
