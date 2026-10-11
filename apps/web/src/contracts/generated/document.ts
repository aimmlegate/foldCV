export type Id = "candidate";
export type Kind = "candidate";
export type Sourceid = string;
export type Sourcerevision = number;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = Evidence1[];
export type Factids = string[];
export type Fieldid = string;
export type Origin = "source" | "generated" | "user" | "migration";
export type Text = string;
export type Revision = number;
export type Visible = true;
export type Id1 = string;
export type Kind1 = "certification";
export type Revision1 = number;
export type Visible1 = boolean;
export type Certifications = CertificationRecord[];
export type Id2 = "early-career";
export type Kind2 = "early-career";
export type Representedjobids = string[];
export type Revision2 = number;
export type Visible2 = boolean;
export type Id3 = string;
export type Kind3 = "education";
export type Revision3 = number;
export type Visible3 = boolean;
export type Education = EducationRecord[];
export type Id4 = string;
export type Kind4 = "job";
export type Id5 = string;
export type Present = boolean;
export type Periods = DocumentPeriod[];
export type Periodsfieldid = string;
export type Revision4 = number;
export type Subprojectids = string[];
export type Visible4 = boolean;
export type Jobs = JobRecord[];
export type Id6 = string;
export type Kind5 = "language";
export type Revision5 = number;
export type Visible5 = boolean;
export type Languages = LanguageRecord[];
export type Id7 = "profile";
export type Kind6 = "profile";
export type Revision6 = number;
export type Visible6 = boolean;
/**
 * @maxItems 8
 */
export type Focus =
  | []
  | [FocusEntry]
  | [FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry];
export type Catalogid = string;
export type Factids1 = string[];
export type Id8 = string;
export type Focusfieldid = string;
export type Id9 = "skills-focus";
export type Kind7 = "skills-focus";
export type Revision7 = number;
export type Visible7 = boolean;

export interface Document {
  candidate: CandidateRecord;
  certifications: Certifications;
  earlyCareer: EarlyCareerRecord;
  education: Education;
  jobs: Jobs;
  languages: Languages;
  profile: ProfileRecord;
  skillsFocus: SkillsFocusRecord;
}
export interface CandidateRecord {
  id: Id;
  kind: Kind;
  location: AuthoredField;
  name: AuthoredField;
  revision: Revision;
  title: AuthoredField;
  visible: Visible;
}
export interface AuthoredField {
  evidence: Evidence;
  factIds: Factids;
  fieldId: Fieldid;
  origin: Origin;
  text: Text;
}
export interface Evidence1 {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface CertificationRecord {
  dateText: AuthoredField;
  id: Id1;
  issuer: AuthoredField;
  kind: Kind1;
  legacyText: AuthoredField | null;
  name: AuthoredField;
  revision: Revision1;
  visible: Visible1;
}
export interface EarlyCareerRecord {
  id: Id2;
  kind: Kind2;
  representedJobIds: Representedjobids;
  revision: Revision2;
  text: AuthoredField;
  visible: Visible2;
}
export interface EducationRecord {
  dateText: AuthoredField;
  id: Id3;
  institution: AuthoredField;
  kind: Kind3;
  legacyText: AuthoredField | null;
  qualification: AuthoredField;
  revision: Revision3;
  specialty: AuthoredField;
  visible: Visible3;
}
export interface JobRecord {
  context: AuthoredField;
  employer: AuthoredField;
  id: Id4;
  kind: Kind4;
  periods: Periods;
  periodsFieldId: Periodsfieldid;
  results: AuthoredField;
  revision: Revision4;
  role: AuthoredField;
  stack: AuthoredField;
  subprojectIds: Subprojectids;
  tasks: AuthoredField;
  visible: Visible4;
}
export interface DocumentPeriod {
  endText: AuthoredField;
  id: Id5;
  present: Present;
  startText: AuthoredField;
}
export interface LanguageRecord {
  id: Id6;
  kind: Kind5;
  legacyText: AuthoredField | null;
  name: AuthoredField;
  proficiency: AuthoredField;
  revision: Revision5;
  visible: Visible5;
}
export interface ProfileRecord {
  id: Id7;
  kind: Kind6;
  revision: Revision6;
  text: AuthoredField;
  visible: Visible6;
}
export interface SkillsFocusRecord {
  focus: Focus;
  focusFieldId: Focusfieldid;
  id: Id9;
  kind: Kind7;
  revision: Revision7;
  skillsText: AuthoredField;
  visible: Visible7;
}
export interface FocusEntry {
  catalogId: Catalogid;
  display: AuthoredField;
  factIds: Factids1;
  id: Id8;
}
