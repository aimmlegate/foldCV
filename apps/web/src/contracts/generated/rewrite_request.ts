export type Baserevision = number;
export type Blockid = string;
export type Blockkind = "profile" | "job_prose";
export type Blockrevision = number;
export type Contentpolicyversion = string;
export type Currenttext = string;
export type Dependencyhash = string;
export type Factid = string;
export type Text = string;
/**
 * @maxItems 200
 */
export type Excerpts = RewriteExcerpt[];
/**
 * @minItems 1
 * @maxItems 200
 */
export type Facts = [
  TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact,
  ...(TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact)[]
];
export type Sourceid = string;
export type Sourcerevision = number;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = Evidence1[];
export type Id = string;
export type Importance = "essential" | "normal" | "minor";
export type Jobid = string | null;
export type Kind = "text";
export type Origin = "source" | "user";
export type Revision = number;
export type Subprojectid = string | null;
export type Text1 = string;
export type Evidence2 = Evidence1[];
export type Id1 = string;
export type Importance1 = "essential" | "normal" | "minor";
export type Jobid1 = string | null;
export type Kind1 = "technology";
export type Origin1 = "source" | "user";
export type Revision1 = number;
export type Subprojectid1 = string | null;
export type Canonicalid = string;
export type Display = string;
export type Scope = "global" | "job" | "subproject";
export type Evidence3 = Evidence1[];
export type Id2 = string;
export type Importance2 = "essential" | "normal" | "minor";
export type Jobid2 = string | null;
export type Kind2 = "metric";
export type Origin2 = "source" | "user";
export type Revision2 = number;
export type Subprojectid2 = string | null;
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
export type Evidence4 = Evidence1[];
export type Id3 = string;
export type Importance3 = "essential" | "normal" | "minor";
export type Jobid3 = string | null;
export type Kind3 = "leadership";
export type Origin3 = "source" | "user";
export type Revision3 = number;
export type Subprojectid3 = string | null;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Evidence5 = Evidence1[];
export type Id4 = string;
export type Importance4 = "essential" | "normal" | "minor";
export type Jobid4 = string | null;
export type Kind4 = "date";
export type Origin4 = "source" | "user";
export type Revision4 = number;
export type Subprojectid4 = string | null;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Instruction = string;
/**
 * @maxItems 200
 */
export type Requiredfactids = string[];
export type Sourcelanguage = "ru" | "en" | "mixed";
export type Transportversion = 1;

export interface RewriteRequest {
  baseRevision: Baserevision;
  blockId: Blockid;
  blockKind: Blockkind;
  blockRevision: Blockrevision;
  contentPolicyVersion: Contentpolicyversion;
  currentText: Currenttext;
  dependencyHash: Dependencyhash;
  excerpts: Excerpts;
  facts: Facts;
  instruction: Instruction;
  requiredFactIds: Requiredfactids;
  sourceLanguage: Sourcelanguage;
  transportVersion?: Transportversion;
}
export interface RewriteExcerpt {
  factId: Factid;
  text: Text;
}
export interface TextFact {
  evidence: Evidence;
  id: Id;
  importance: Importance;
  jobId: Jobid;
  kind: Kind;
  origin: Origin;
  revision: Revision;
  subprojectId: Subprojectid;
  value: TextValue;
}
export interface Evidence1 {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface TextValue {
  text: Text1;
}
export interface TechnologyFact {
  evidence: Evidence2;
  id: Id1;
  importance: Importance1;
  jobId: Jobid1;
  kind: Kind1;
  origin: Origin1;
  revision: Revision1;
  subprojectId: Subprojectid1;
  value: TechnologyValue;
}
export interface TechnologyValue {
  canonicalId: Canonicalid;
  display: Display;
  scope: Scope;
}
export interface MetricFact {
  evidence: Evidence3;
  id: Id2;
  importance: Importance2;
  jobId: Jobid2;
  kind: Kind2;
  origin: Origin2;
  revision: Revision2;
  subprojectId: Subprojectid2;
  value: MetricValue;
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
export interface LeadershipFact {
  evidence: Evidence4;
  id: Id3;
  importance: Importance3;
  jobId: Jobid3;
  kind: Kind3;
  origin: Origin3;
  revision: Revision3;
  subprojectId: Subprojectid3;
  value: LeadershipValue;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface DateFact {
  evidence: Evidence5;
  id: Id4;
  importance: Importance4;
  jobId: Jobid4;
  kind: Kind4;
  origin: Origin4;
  revision: Revision4;
  subprojectId: Subprojectid4;
  value: PartialDate;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
