export type Anchor = FieldAnchor | SectionAnchor | DocumentAnchor;
export type Fieldid = string;
export type Kind = "field";
export type End = number;
export type Start = number;
export type Kind1 = "section";
export type Sectionid = string;
export type Kind2 = "document";
export type Code = string;
export type Dependencyfingerprint = string;
export type Documentrevision = number;
export type Projectrevision = number;
export type Rulessha256 = string | null;
export type Sourcefingerprint = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Text = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Factids = string[];
export type Id = string;
export type Reason = string;
export type Catalogid = string;
export type Reason1 = "duplicate" | "unknown-ID" | "missing-logo" | "capacity";
export type Removedfocus = FocusRemoval[];
export type Resolved = boolean;
export type Type = "missing" | "conflicting" | "stale" | "warning";
export type Updatesuggestionid = string | null;
export type Annotations = Annotation[];
export type Documentrevision1 = number;
export type Page = number | null;
export type Relation = "exact" | "field" | "block";
export type Excerpts = SourceExcerpt[];
export type Sourceid1 = string;
export type Sourcerevision1 = number;
export type Unitid1 = string;
export type Unitrevision1 = number;
export type Evidence1 = Evidence2[];
export type Factids1 = string[];
export type Id1 = string;
export type Label = string;
export type Originalkind = string;
export type Text1 = string;
export type Visible = boolean;
export type Legacytext = LegacyText[];
export type Projectid = string;
export type Status = "evidence" | "user-origin" | "no-evidence" | "stale";

export interface SourceContext {
  annotations: Annotations;
  documentRevision: Documentrevision1;
  excerpts: Excerpts;
  legacyText: Legacytext;
  projectId: Projectid;
  status: Status;
}
export interface Annotation {
  anchor: Anchor;
  code: Code;
  dependencies: Dependencies;
  evidence: Evidence;
  factIds: Factids;
  id: Id;
  reason: Reason;
  removedFocus: Removedfocus;
  resolved: Resolved;
  type: Type;
  updateSuggestionId: Updatesuggestionid;
}
export interface FieldAnchor {
  fieldId: Fieldid;
  kind: Kind;
  range: Range | null;
}
export interface Range {
  end: End;
  start: Start;
}
export interface SectionAnchor {
  kind: Kind1;
  sectionId: Sectionid;
}
export interface DocumentAnchor {
  kind: Kind2;
}
export interface Dependencies {
  dependencyFingerprint: Dependencyfingerprint;
  documentRevision: Documentrevision;
  projectRevision: Projectrevision;
  rulesSha256: Rulessha256;
  sourceFingerprint: Sourcefingerprint;
}
export interface EvidenceSpan {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  text: Text;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface FocusRemoval {
  catalogId: Catalogid;
  reason: Reason1;
}
export interface SourceExcerpt {
  evidence: EvidenceSpan;
  page: Page;
  relation: Relation;
}
export interface LegacyText {
  evidence: Evidence1;
  factIds: Factids1;
  id: Id1;
  label: Label;
  originalKind: Originalkind;
  text: Text1;
  visible: Visible;
}
export interface Evidence2 {
  sourceId: Sourceid1;
  sourceRevision: Sourcerevision1;
  unitId: Unitid1;
  unitRevision: Unitrevision1;
}
