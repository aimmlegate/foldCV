export type Elapsed = number;
export type Error = string | null;
export type Id = string;
export type Kind = "import" | "export" | "rewrite";
export type Projectid = string;
export type Stage = string | null;
export type Startedat = string;
export type State = "running" | "succeeded" | "failed" | "cancelled";

export interface TaskStatusV1 {
  detail: Detail;
  elapsed: Elapsed;
  error: Error;
  id: Id;
  kind: Kind;
  projectId: Projectid;
  stage: Stage;
  startedAt: Startedat;
  state: State;
}
export interface Detail {
  [k: string]: unknown;
}
