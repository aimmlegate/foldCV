export type Allowtextrewrite = boolean;
export type Clientrequestid = string;
export type Effort = ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Kind = "start" | "resume" | "cancel";
export type Operationid = string | null;
export type Taskid = string | null;

export interface ImportCommand {
  allowTextRewrite?: Allowtextrewrite;
  clientRequestId?: Clientrequestid;
  effort?: Effort;
  kind: Kind;
  operationId?: Operationid;
  taskId?: Taskid;
}
