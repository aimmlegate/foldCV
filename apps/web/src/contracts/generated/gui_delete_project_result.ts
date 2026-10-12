export type Errorcode = string | null;
export type Projectid = string;
export type Status = "deleted" | "cleanup_incomplete";

export interface GuiDeleteProjectResult {
  errorCode: Errorcode;
  projectId: Projectid;
  status: Status;
}
