export type Actionid = string;
export type Dependencyrevision = number;
export type Id = string;
export type Liveblocks = number;
export type Projectid = string;
export type Retainedbytes = number;
export type Sessionid = string;
export type Status = "reserved" | "decoding" | "published" | "cancelled" | "stale" | "failed";

export interface AssetReservation {
  actionId: Actionid;
  dependencyRevision: Dependencyrevision;
  id: Id;
  liveBlocks: Liveblocks;
  projectId: Projectid;
  retainedBytes: Retainedbytes;
  sessionId: Sessionid;
  status: Status;
}
