export type Anchorjobid = string;
export type Anchorperiodid = string;
export type Actionid = string;
export type Actiontoken = number;
export type Fingerprint = string | null;
export type Id = string;
export type Kind =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Id1 = string;
export type Periodorder = string[];
export type Reason = string | null;
export type Pendingrawtext = string | null;
export type Rawtext = string;
export type Revision1 = number;
export type Status = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Sourceid = string;
export type Sourcerevision = number;
export type Text = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Id2 = string;
export type Pendingrawtext1 = string | null;
export type Rawtext1 = string;
export type Revision2 = number;
export type Status1 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Value = boolean | null;
export type Revision3 = number;
export type Inclusivespan = number;
export type Jobid = string;
export type Periodid = string;
export type Unit = "month" | "day";
export type Shifts = DateShift[];
export type Status2 = "available" | "unavailable" | "stale" | "applied" | "dismissed";
export type Warnings = string[];

export interface DateCascadeProposal {
  anchorJobId: Anchorjobid;
  anchorPeriodId: Anchorperiodid;
  capture: ActionCapture;
  formattingAsOf: PartialDate;
  id: Id1;
  periodOrder: Periodorder;
  reason: Reason;
  shifts: Shifts;
  status: Status2;
  warnings: Warnings;
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
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface DateShift {
  after: WorkingPeriod;
  before: WorkingPeriod;
  inclusiveSpan: Inclusivespan;
  jobId: Jobid;
  periodId: Periodid;
  unit: Unit;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence;
  id: Id2;
  present: WorkingFieldBool;
  revision: Revision3;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext;
  revision: Revision1;
  status: Status;
  value: PartialDate | null;
}
export interface EvidenceSpan {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  text: Text;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface WorkingFieldBool {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext1;
  revision: Revision2;
  status: Status1;
  value: Value;
}
