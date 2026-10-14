export type Actionid = string;
export type Actiontoken = number;
export type Fingerprint = string | null;
export type Id = string;
export type Kind =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Documentrevision = number;
export type Factsrevision = number;
export type Jobid = string | null;
export type Operation = "add" | "edit" | "remove" | "add_period" | "remove_period";
export type Periodid = string | null;
export type Recordid = string | null;
export type Recordkind = ("candidate" | "employment" | "technology" | "education" | "language") | null;

export interface RichPanelRequest {
  capture: ActionCapture;
  documentRevision: Documentrevision;
  factsRevision: Factsrevision;
  jobId?: Jobid;
  operation: Operation;
  periodId?: Periodid;
  recordId?: Recordid;
  recordKind?: Recordkind;
  values?: Values;
}
export interface ActionCapture {
  actionId: Actionid;
  actionToken: Actiontoken;
  dependencies: Dependencies;
  sessionId: Sessionid;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id;
  kind: Kind;
  revision: Revision;
}
export interface Values {
  [k: string]: string;
}
