export type Factids = string[];
export type Catalogid = string;
export type Display = string;
export type Factids1 = string[];
export type Focus = PlanFocus[];
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Disposition = "detailed" | "early-career";
export type Factids2 = string[];
export type Jobid = string;
export type Jobs = JobDisposition[];
export type Origin = "model" | "migration";
export type Profilelanguage = ("ru" | "en") | null;
export type Revision = number;
export type Rulesrevision = number | null;
export type Sourcelanguage = "ru" | "en" | "mixed";
export type Factids3 = string[];
export type Title = string;
export type Technologygroups = TechnologyGroup[];

export interface EditorialPlan {
  factIds: Factids;
  focus: Focus;
  formattingAsOf: PartialDate;
  jobs: Jobs;
  origin: Origin;
  profileLanguage: Profilelanguage;
  revision: Revision;
  rulesRevision: Rulesrevision;
  sourceLanguage: Sourcelanguage;
  technologyGroups: Technologygroups;
}
export interface PlanFocus {
  catalogId: Catalogid;
  display: Display;
  factIds: Factids1;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface JobDisposition {
  disposition: Disposition;
  factIds: Factids2;
  jobId: Jobid;
}
export interface TechnologyGroup {
  factIds: Factids3;
  title: Title;
}
