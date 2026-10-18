export type Action = string;
export type Downloadurl = string | null;
export type Durable = boolean;
export type Errorcode = string | null;
export type Id = string;
export type Projectid = string;
export type Runid = string;
export type Status = string;
/**
 * @maxItems 500
 */
export type Items = AgentProjectOperation[];

export interface AgentProjectOperations {
  items: Items;
}
export interface AgentProjectOperation {
  action: Action;
  downloadUrl: Downloadurl;
  durable: Durable;
  errorCode: Errorcode;
  id: Id;
  projectId: Projectid;
  runId: Runid;
  status: Status;
}
