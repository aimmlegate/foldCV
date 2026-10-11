export type Mutation =
  EditMutation | RestoreMutation | AddMutation | DeleteMutation | ReorderMutation | HideMutation | RelatedMutation;
export type Baserevision = number;
export type Clientmutationid = string;
export type Kind = "edit-field";
export type Completion = "none" | "paragraph" | "field" | "slot";
export type Fieldid = string;
export type Focus = FocusEntry[] | null;
export type Catalogid = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = Evidence1[];
export type Factids = string[];
export type Fieldid1 = string;
export type Origin = "source" | "generated" | "user" | "migration";
export type Text = string;
export type Factids1 = string[];
export type Id = string;
export type Periods = DocumentPeriod[] | null;
export type Id1 = string;
export type Present = boolean;
export type Sessionid = string;
export type Text1 = string | null;
export type Projectid = string;
export type Baserevision1 = number;
export type Clientmutationid1 = string;
export type Kind1 = "restore-previous-block";
export type Sessionid1 = string | null;
export type Slotid = string;
export type Projectid1 = string;
export type Baserevision2 = number;
export type Clientmutationid2 = string;
export type Kind2 = "add";
export type Afterrecordid = string | null;
export type Record = JobRecord | EducationRecord | LanguageRecord;
export type Id2 = string;
export type Kind3 = "job";
export type Periods1 = DocumentPeriod[];
export type Periodsfieldid = string;
export type Revision = number;
export type Subprojectids = string[];
export type Visible = boolean;
export type Id3 = string;
export type Kind4 = "education";
export type Revision1 = number;
export type Visible1 = boolean;
export type Id4 = string;
export type Kind5 = "language";
export type Revision2 = number;
export type Visible2 = boolean;
export type Sectionid = "jobs" | "education" | "languages";
export type Projectid2 = string;
export type Baserevision3 = number;
export type Clientmutationid3 = string;
export type Kind6 = "delete";
export type Recordid = string;
export type Sectionid1 = "jobs" | "education" | "languages";
export type Projectid3 = string;
export type Baserevision4 = number;
export type Clientmutationid4 = string;
export type Kind7 = "reorder";
export type Orderedids = string[];
export type Sectionid2 = "jobs" | "education" | "languages";
export type Projectid4 = string;
export type Baserevision5 = number;
export type Clientmutationid5 = string;
export type Kind8 = "hide";
export type Slotid1 = string;
export type Visible3 = boolean;
export type Projectid5 = string;
export type Baserevision6 = number;
export type Clientmutationid6 = string;
export type Kind9 = "apply-related-update";
export type Dependencyfingerprint = string;
export type Documentrevision = number;
export type Projectrevision = number;
export type Rulessha256 = string | null;
export type Sourcefingerprint = string;
export type Suggestionid = string;
export type Projectid6 = string;

export interface EditMutation {
  baseRevision: Baserevision;
  clientMutationId: Clientmutationid;
  kind: Kind;
  payload: EditFieldPayload;
  projectId: Projectid;
}
export interface EditFieldPayload {
  completion: Completion;
  fieldId: Fieldid;
  focus: Focus;
  periods: Periods;
  sessionId: Sessionid;
  text: Text1;
}
export interface FocusEntry {
  catalogId: Catalogid;
  display: AuthoredField;
  factIds: Factids1;
  id: Id;
}
export interface AuthoredField {
  evidence: Evidence;
  factIds: Factids;
  fieldId: Fieldid1;
  origin: Origin;
  text: Text;
}
export interface Evidence1 {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface DocumentPeriod {
  endText: AuthoredField;
  id: Id1;
  present: Present;
  startText: AuthoredField;
}
export interface RestoreMutation {
  baseRevision: Baserevision1;
  clientMutationId: Clientmutationid1;
  kind: Kind1;
  payload: RestorePayload;
  projectId: Projectid1;
}
export interface RestorePayload {
  sessionId: Sessionid1;
  slotId: Slotid;
}
export interface AddMutation {
  baseRevision: Baserevision2;
  clientMutationId: Clientmutationid2;
  kind: Kind2;
  payload: AddPayload;
  projectId: Projectid2;
}
export interface AddPayload {
  afterRecordId: Afterrecordid;
  record: Record;
  sectionId: Sectionid;
}
export interface JobRecord {
  context: AuthoredField;
  employer: AuthoredField;
  id: Id2;
  kind: Kind3;
  periods: Periods1;
  periodsFieldId: Periodsfieldid;
  results: AuthoredField;
  revision: Revision;
  role: AuthoredField;
  stack: AuthoredField;
  subprojectIds: Subprojectids;
  tasks: AuthoredField;
  visible: Visible;
}
export interface EducationRecord {
  dateText: AuthoredField;
  id: Id3;
  institution: AuthoredField;
  kind: Kind4;
  legacyText: AuthoredField | null;
  qualification: AuthoredField;
  revision: Revision1;
  specialty: AuthoredField;
  visible: Visible1;
}
export interface LanguageRecord {
  id: Id4;
  kind: Kind5;
  legacyText: AuthoredField | null;
  name: AuthoredField;
  proficiency: AuthoredField;
  revision: Revision2;
  visible: Visible2;
}
export interface DeleteMutation {
  baseRevision: Baserevision3;
  clientMutationId: Clientmutationid3;
  kind: Kind6;
  payload: DeletePayload;
  projectId: Projectid3;
}
export interface DeletePayload {
  recordId: Recordid;
  sectionId: Sectionid1;
}
export interface ReorderMutation {
  baseRevision: Baserevision4;
  clientMutationId: Clientmutationid4;
  kind: Kind7;
  payload: ReorderPayload;
  projectId: Projectid4;
}
export interface ReorderPayload {
  orderedIds: Orderedids;
  sectionId: Sectionid2;
}
export interface HideMutation {
  baseRevision: Baserevision5;
  clientMutationId: Clientmutationid5;
  kind: Kind8;
  payload: HidePayload;
  projectId: Projectid5;
}
export interface HidePayload {
  slotId: Slotid1;
  visible: Visible3;
}
export interface RelatedMutation {
  baseRevision: Baserevision6;
  clientMutationId: Clientmutationid6;
  kind: Kind9;
  payload: ApplyRelatedPayload;
  projectId: Projectid6;
}
export interface ApplyRelatedPayload {
  dependencies: Dependencies;
  suggestionId: Suggestionid;
}
export interface Dependencies {
  dependencyFingerprint: Dependencyfingerprint;
  documentRevision: Documentrevision;
  projectRevision: Projectrevision;
  rulesSha256: Rulessha256;
  sourceFingerprint: Sourcefingerprint;
}
