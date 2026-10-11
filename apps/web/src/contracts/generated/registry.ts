export type Cleanupstatus = "none" | "pending" | "complete" | "failed";
export type Projectid = string;
export type Title = string;
export type Tombstoned = boolean;
export type Updatedat = string;
export type Entries = RegistryEntry[];
export type Schemaversion = 1;

export interface Registry {
  entries: Entries;
  schemaVersion: Schemaversion;
}
export interface RegistryEntry {
  cleanupStatus: Cleanupstatus;
  projectId: Projectid;
  title: Title;
  tombstoned: Tombstoned;
  updatedAt: Updatedat;
}
