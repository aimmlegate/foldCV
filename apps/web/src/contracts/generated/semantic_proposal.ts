export type Importance = "essential" | "normal" | "minor";
export type Jobtempid = string | null;
export type Kind = "text" | "technology" | "date" | "metric" | "leadership";
export type Sourceid = string;
export type Subprojecttempid = string | null;
export type Tempid = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Unitids = [string, ...string[]];
export type Value = TextValue | TechnologyValue | PartialDate | MetricValue | LeadershipValue;
export type Text = string;
export type Canonicalid = string;
export type Display = string;
export type Scope = "global" | "job" | "subproject";
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Attribution = "personal" | "team" | "organization" | "unknown";
export type Baseline = string | null;
export type Comparator = "exact" | "at_least" | "at_most" | "approximately" | "range";
export type Number = number;
export type Period = string | null;
export type Qualifiers = string[];
export type Result = string | null;
export type Scope1 = string | null;
export type Unit = string;
export type Uppernumber = number | null;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
/**
 * @maxItems 500
 */
export type Facts = ProposedFact[];
export type Employer = string;
/**
 * @maxItems 20
 */
export type Periods =
  | []
  | [Period1]
  | [Period1, Period1]
  | [Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ];
export type Role = string;
export type Sourceid1 = string;
export type Name = string;
export type Tempid1 = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Unitids1 = [string, ...string[]];
/**
 * @maxItems 100
 */
export type Subprojects = ProposedSubproject[];
export type Tempid2 = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Unitids2 = [string, ...string[]];
/**
 * @maxItems 100
 */
export type Jobs = ProposedJob[];
export type Schemaversion = 1;
export type Disposition = "facts" | "administrative" | "duplicate" | "unresolved";
export type Duplicateof = string | null;
export type Facttempids = string[];
export type Sourceid2 = string;
export type Unitid = string;
/**
 * @maxItems 5000
 */
export type Units = UnitProposal[];

export interface SemanticProposal {
  facts: Facts;
  jobs: Jobs;
  schemaVersion: Schemaversion;
  units: Units;
}
export interface ProposedFact {
  importance?: Importance;
  jobTempId?: Jobtempid;
  kind: Kind;
  sourceId: Sourceid;
  subprojectTempId?: Subprojecttempid;
  tempId: Tempid;
  unitIds: Unitids;
  value: Value;
}
export interface TextValue {
  text: Text;
}
export interface TechnologyValue {
  canonicalId: Canonicalid;
  display: Display;
  scope: Scope;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface MetricValue {
  attribution: Attribution;
  baseline: Baseline;
  comparator: Comparator;
  number: Number;
  period: Period;
  qualifiers: Qualifiers;
  result: Result;
  scope: Scope1;
  unit: Unit;
  upperNumber: Uppernumber;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface ProposedJob {
  employer: Employer;
  periods: Periods;
  role: Role;
  sourceId: Sourceid1;
  subprojects?: Subprojects;
  tempId: Tempid2;
  unitIds: Unitids2;
}
export interface Period1 {
  end: PartialDate | null;
  start: PartialDate;
}
export interface ProposedSubproject {
  name: Name;
  period?: Period1 | null;
  tempId: Tempid1;
  unitIds: Unitids1;
}
export interface UnitProposal {
  disposition: Disposition;
  duplicateOf?: Duplicateof;
  factTempIds: Facttempids;
  sourceId: Sourceid2;
  unitId: Unitid;
}
