export type Monthsmax = number | null;
export type Monthsmin = number | null;
export type Reason = string | null;
export type Scopeid = string;
export type Estimates = TimelineEstimate[];
export type Certainty = ("possible" | "certain") | null;
export type Code = string;
export type Id = string;
export type Jobids = string[];
export type Kind = "overlap" | "quality" | "future";
export type Periodids = string[];
export type Warnings = TimelineWarning[];

export interface TimelineReport {
  estimates: Estimates;
  warnings: Warnings;
}
export interface TimelineEstimate {
  monthsMax: Monthsmax;
  monthsMin: Monthsmin;
  reason: Reason;
  scopeId: Scopeid;
}
export interface TimelineWarning {
  certainty: Certainty;
  code: Code;
  id: Id;
  jobIds: Jobids;
  kind: Kind;
  periodIds: Periodids;
}
