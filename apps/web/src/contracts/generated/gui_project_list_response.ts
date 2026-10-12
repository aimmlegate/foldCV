export type Cleanupstatus = "none" | "pending" | "complete" | "failed";
export type Projectid = string;
export type Title = string;
export type Tombstoned = boolean;
export type Updatedat = string;
export type Entries = RegistryEntry[];
export type Errorcode = string;
export type Projectid1 = string;
export type Errors = ProjectReadError[];

export interface GuiProjectListResponse {
  entries: Entries;
  errors: Errors;
}
export interface RegistryEntry {
  cleanupStatus: Cleanupstatus;
  projectId: Projectid;
  title: Title;
  tombstoned: Tombstoned;
  updatedAt: Updatedat;
}
export interface ProjectReadError {
  errorCode: Errorcode;
  projectId: Projectid1;
}
