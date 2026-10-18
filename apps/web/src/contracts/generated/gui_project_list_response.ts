export type Archived = boolean;
export type Cleanupstatus = "none" | "pending" | "complete" | "failed";
export type Lastopenedat = string | null;
export type Projectid = string;
export type Subtitle = string | null;
export type Title = string;
export type Tombstoned = boolean;
export type Updatedat = string;
export type Entries = GuiProjectListEntry[];
export type Errorcode = string;
export type Projectid1 = string;
export type Errors = ProjectReadError[];

export interface GuiProjectListResponse {
  entries: Entries;
  errors: Errors;
}
export interface GuiProjectListEntry {
  archived?: Archived;
  cleanupStatus: Cleanupstatus;
  lastOpenedAt?: Lastopenedat;
  projectId: Projectid;
  subtitle?: Subtitle;
  title: Title;
  tombstoned: Tombstoned;
  updatedAt: Updatedat;
}
export interface ProjectReadError {
  errorCode: Errorcode;
  projectId: Projectid1;
}
