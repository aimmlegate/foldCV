export type Sourceid = string;
export type Sourcerevision = number;
export type Text = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Id = string;
export type Kind = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext = string;
export type Revision = number;
export type Status = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected = boolean;
export type Value = string | null;
export type Origin = "source" | "user";
export type Revision1 = number;
export type Usercorrected1 = boolean;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence1 = EvidenceSpan[];
export type Id1 = string;
export type Kind1 = "detail";
export type Label = string;
export type Origin1 = "source" | "user";
export type Revision2 = number;
export type Usercorrected2 = boolean;
export type Evidence2 = EvidenceSpan[];
export type Id2 = string;
export type Kind2 = "employment";
export type Origin2 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext1 = string;
export type Revision3 = number;
export type Status1 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected3 = boolean;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Evidence3 = EvidenceSpan[];
export type Id3 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext2 = string;
export type Revision4 = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected4 = boolean;
export type Value1 = boolean | null;
export type Revision5 = number;
export type Periods = WorkingPeriod[];
export type Revision6 = number;
export type Usercorrected5 = boolean;
export type Evidence4 = EvidenceSpan[];
export type Id4 = string;
export type Jobid = string;
export type Kind3 = "subproject";
export type Origin3 = "source" | "user";
export type Periods1 = WorkingPeriod[];
export type Revision7 = number;
export type Usercorrected6 = boolean;
export type Evidence5 = EvidenceSpan[];
export type Id5 = string;
export type Jobid1 = string | null;
export type Kind4 = "technology";
export type Origin4 = "source" | "user";
export type Revision8 = number;
export type Subprojectid = string | null;
export type Usercorrected7 = boolean;
export type Evidence6 = EvidenceSpan[];
export type Id6 = string;
export type Kind5 = "education";
export type Origin5 = "source" | "user";
export type Revision9 = number;
export type Usercorrected8 = boolean;
export type Evidence7 = EvidenceSpan[];
export type Id7 = string;
export type Kind6 = "language";
export type Origin6 = "source" | "user";
export type Revision10 = number;
export type Usercorrected9 = boolean;
export type Evidence8 = EvidenceSpan[];
export type Id8 = string;
export type Kind7 = "certification";
export type Origin7 = "source" | "user";
export type Revision11 = number;
export type Usercorrected10 = boolean;
export type Evidence9 = EvidenceSpan[];
export type Id9 = string;
export type Jobid2 = string | null;
export type Kind8 = "claim";
export type Origin8 = "source" | "user";
export type Revision12 = number;
export type Subprojectid1 = string | null;
export type Usercorrected11 = boolean;
export type Evidence10 = EvidenceSpan[];
export type Id10 = string;
export type Jobid3 = string | null;
export type Kind9 = "metric";
export type Origin9 = "source" | "user";
export type Revision13 = number;
export type Subprojectid2 = string | null;
export type Usercorrected12 = boolean;
export type Pendingrawtext3 = string | null;
export type Rawtext3 = string;
export type Revision14 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected13 = boolean;
export type Attribution = "personal" | "team" | "organization" | "unknown";
export type Baseline = string | null;
export type Comparator = "exact" | "at_least" | "at_most" | "approximately" | "range";
export type Number = number;
export type Period = string | null;
export type Qualifiers = string[];
export type Result = string | null;
export type Scope = string | null;
export type Unit = string;
export type Uppernumber = number | null;
export type Evidence11 = EvidenceSpan[];
export type Id11 = string;
export type Jobid4 = string | null;
export type Kind10 = "leadership";
export type Origin10 = "source" | "user";
export type Revision15 = number;
export type Subprojectid3 = string | null;
export type Usercorrected14 = boolean;
export type Pendingrawtext4 = string | null;
export type Rawtext4 = string;
export type Revision16 = number;
export type Status4 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected15 = boolean;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Category = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence12 = EvidenceSpan[];
export type Id12 = string;
export type Kind11 = "unresolved";
export type Origin11 = "source" | "user";
export type Revision17 = number;
export type Status5 = "unresolved" | "pending" | "conflict";
export type Usercorrected16 = boolean;
export type Records = (
  | CandidateRecord
  | DetailRecord
  | EmploymentRecord
  | SubprojectRecord
  | TechnologyRecord
  | EducationRecord
  | LanguageRecord
  | CertificationRecord
  | ClaimRecord
  | MetricRecord
  | LeadershipRecord
  | UnresolvedRecord
)[];
export type Revision18 = number;
export type Actionid = string;
export type Orderindex = number;
export type Recordid = string;
export type Revision19 = number;
export type Tombstones = RecordTombstone[];

export interface WorkingFacts {
  records: Records;
  revision: Revision18;
  tombstones: Tombstones;
}
export interface CandidateRecord {
  evidence: Evidence;
  id: Id;
  kind: Kind;
  location: WorkingFieldStr;
  name: WorkingFieldStr;
  origin: Origin;
  revision: Revision1;
  title: WorkingFieldStr;
  userCorrected?: Usercorrected1;
}
export interface EvidenceSpan {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  text: Text;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface WorkingFieldStr {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext;
  revision: Revision;
  status: Status;
  userCorrected?: Usercorrected;
  value: Value;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence1;
  id: Id1;
  kind: Kind1;
  label: Label;
  origin: Origin1;
  revision: Revision2;
  userCorrected?: Usercorrected2;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence2;
  id: Id2;
  kind: Kind2;
  origin: Origin2;
  periods: Periods;
  revision: Revision6;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected5;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence3;
  id: Id3;
  present: WorkingFieldBool;
  revision: Revision5;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext1;
  revision: Revision3;
  status: Status1;
  userCorrected?: Usercorrected3;
  value: PartialDate | null;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface WorkingFieldBool {
  pendingRawText: Pendingrawtext2;
  rawText: Rawtext2;
  revision: Revision4;
  status: Status2;
  userCorrected?: Usercorrected4;
  value: Value1;
}
export interface SubprojectRecord {
  evidence: Evidence4;
  id: Id4;
  jobId: Jobid;
  kind: Kind3;
  name: WorkingFieldStr;
  origin: Origin3;
  periods: Periods1;
  revision: Revision7;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected6;
}
export interface TechnologyRecord {
  canonicalId: WorkingFieldStr;
  display: WorkingFieldStr;
  evidence: Evidence5;
  id: Id5;
  jobId: Jobid1;
  kind: Kind4;
  origin: Origin4;
  revision: Revision8;
  subprojectId: Subprojectid;
  userCorrected?: Usercorrected7;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence6;
  id: Id6;
  institution: WorkingFieldStr;
  kind: Kind5;
  origin: Origin5;
  qualification: WorkingFieldStr;
  revision: Revision9;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected8;
}
export interface LanguageRecord {
  evidence: Evidence7;
  id: Id7;
  kind: Kind6;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin6;
  revision: Revision10;
  userCorrected?: Usercorrected9;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence8;
  id: Id8;
  issuer: WorkingFieldStr;
  kind: Kind7;
  name: WorkingFieldStr;
  origin: Origin7;
  revision: Revision11;
  userCorrected?: Usercorrected10;
}
export interface ClaimRecord {
  evidence: Evidence9;
  id: Id9;
  jobId: Jobid2;
  kind: Kind8;
  origin: Origin8;
  revision: Revision12;
  subprojectId: Subprojectid1;
  userCorrected?: Usercorrected11;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence10;
  id: Id10;
  jobId: Jobid3;
  kind: Kind9;
  origin: Origin9;
  revision: Revision13;
  subprojectId: Subprojectid2;
  userCorrected?: Usercorrected12;
  value: WorkingFieldMetricValue;
}
export interface WorkingFieldMetricValue {
  pendingRawText: Pendingrawtext3;
  rawText: Rawtext3;
  revision: Revision14;
  status: Status3;
  userCorrected?: Usercorrected13;
  value: MetricValue | null;
}
export interface MetricValue {
  attribution: Attribution;
  baseline: Baseline;
  comparator: Comparator;
  number: Number;
  period: Period;
  qualifiers: Qualifiers;
  result: Result;
  scope: Scope;
  unit: Unit;
  upperNumber: Uppernumber;
}
export interface LeadershipRecord {
  evidence: Evidence11;
  id: Id11;
  jobId: Jobid4;
  kind: Kind10;
  origin: Origin10;
  revision: Revision15;
  subprojectId: Subprojectid3;
  userCorrected?: Usercorrected14;
  value: WorkingFieldLeadershipValue;
}
export interface WorkingFieldLeadershipValue {
  pendingRawText: Pendingrawtext4;
  rawText: Rawtext4;
  revision: Revision16;
  status: Status4;
  userCorrected?: Usercorrected15;
  value: LeadershipValue | null;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface UnresolvedRecord {
  category: Category;
  evidence: Evidence12;
  id: Id12;
  kind: Kind11;
  origin: Origin11;
  revision: Revision17;
  status: Status5;
  userCorrected?: Usercorrected16;
}
export interface RecordTombstone {
  actionId: Actionid;
  orderIndex: Orderindex;
  recordId: Recordid;
  revision: Revision19;
}
