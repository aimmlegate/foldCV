export type Changedslotids = string[];
export type Documentrevision = number;
export type Persistence = "memory" | "durable" | "pending" | "failed";
export type Projectrevision = number;
export type Rejectionreason = string | null;
export type Status = "applied" | "replayed" | "stale" | "rejected";

export interface MutationResult {
  changedSlotIds: Changedslotids;
  documentRevision: Documentrevision;
  persistence: Persistence;
  projectRevision: Projectrevision;
  rejectionReason: Rejectionreason;
  status: Status;
}
